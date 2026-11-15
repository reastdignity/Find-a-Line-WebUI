"""The access mark through the search (--access; docs/line-volume/spec-search.md 3, step 1d-2): access.py's grid
computed once per search on step 1's grid, at once or in blocks (the same answers), each line's two anchors' answers
(access1, access2: 0 hard access, 1 cannot tell, 2 easy access; the measure's own, as the study's), the inputs the
search gives the measure (its water, its filled pixels, the alpine variant), the memory check and the blocks' size,
the four text files, the store and the favourites with them, a search without the option as before, tiles that give
one grid's answers, the store's coded note, the warm-up of the access kernels, the web process that never imports
access.py, and today's page reading a run made with the option as one made without it."""

import dataclasses
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import access  # noqa: E402
import helpers as sh  # noqa: E402
import linestore  # noqa: E402
import messages  # noqa: E402
import runs as rn  # noqa: E402
import search  # noqa: E402
from params import SearchParams  # noqa: E402
from test_offline import DATA, OFFLINE_ENV, _square, _water_and_fallback, write_raster  # noqa: E402

VIEWER = os.path.join(REPO, "viewer")
LEFT, TOP, SIZE = 500000.0, 300000.0, 300  # the made-up scene: EPSG:2180, 1 m pixels
TOWER = (slice(140, 148), slice(146, 154))  # rows, columns of the tower's top
WEST_RIM, EAST_RIM = 129, 170  # the columns of the canyon's rims


def scene(whole: bool = False, no_data: bool = False) -> np.ndarray:
    """A canyon 40 m wide and 50 m deep with a tower of 8 x 8 m in it, standing as high as its rims. West of it a
    meadow of 3.9 ha (open ground: its rim reads easy access), east of it a shelf of 0.9 ha (not open ground) whose
    only way down is a slope of 45 degrees to a meadow (cannot tell: only the loose walk reaches it); the tower's
    top no walk reaches (hard access). The heights tilt 6 m from north to south, so no flat region reads as a lake
    held as data. whole: the heights in whole metres (their smoothed copy decides too); no_data: the west meadow
    beyond 20 m of its rim without data (an end of the data: its rim reads cannot tell)."""
    z = np.full((SIZE, SIZE), 150.0)
    z[:, 130:170] = 100.0  # the canyon floor (its rims: columns 129 and 170)
    z[TOWER] = 150.0
    z[:, 200:250] = 150.0 - (np.arange(200, 250) - 199)  # 45 degrees down to the east meadow
    z[:, 250:] = 100.0
    z += 0.02 * np.arange(SIZE)[:, None] + (0.0 if whole else 0.25)
    if whole:
        z = np.round(z)
    if no_data:
        z[:, :110] = np.nan
    return z.astype(np.float32)


def _plan(tmp_path, z: np.ndarray, name: str, events=None, **values) -> search.Plan:
    """The plan of a circle over the scene (its grid a window of the scene's pixels), offline."""
    write_raster(tmp_path / f"{name}.tif", z, LEFT, TOP)
    params = SearchParams(**{**dict(
        elevation_file=str(tmp_path / f"{name}.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2, radius=135,
        resolution=1, nmpt="off", water="off", fill_gaps="off", min_length=10, max_length=80, slope_threshold=60,
        prominence_span=10, drop_radius=10, ortho="never", name=name, access=True), **values})
    paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
    os.makedirs(paths.work, exist_ok=True)
    emit = (lambda kind, text: events.append((kind, text))) if events is not None else (lambda kind, text: None)
    plan = dataclasses.replace(search.plan_search(params, paths, emit), index_runs=False)
    grid = plan.grid
    r0, c0 = TOP - grid.top, grid.left - LEFT
    assert r0 == int(r0) >= 0 and c0 == int(c0) >= 0 and r0 + grid.height <= SIZE and c0 + grid.width <= SIZE
    return plan


def _grid_answers(plan: search.Plan, z: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """access.access_grid (the alpine variant on) of the search's grid, a window of the scene z, at scene pixels."""
    grid = plan.grid
    r0, c0 = int(TOP - grid.top), int(grid.left - LEFT)
    answers = access.access_grid(z[r0:r0 + grid.height, c0:c0 + grid.width], None, 1.0, alpine=True)
    return answers[rows - r0, cols - c0]


def _pixels(xy: np.ndarray) -> tuple:
    """Rows and columns of the scene of [easting, northing] pixel centres."""
    return (np.round(TOP - xy[:, 1] - 0.5).astype(int), np.round(xy[:, 0] - LEFT - 0.5).astype(int))


def _ends(lines: sh.LineTable) -> tuple:
    """(rows, columns, answers) of every line end."""
    c = lines.columns
    r1, c1 = _pixels(c["a1_xy"])
    r2, c2 = _pixels(c["a2_xy"])
    return np.concatenate([r1, r2]), np.concatenate([c1, c2]), np.concatenate([c["access1"], c["access2"]])


def _search(tmp_path, z, name, events=None, **values):
    plan = _plan(tmp_path, z, name, events, **values)
    lines, run = search.search_lines(plan)
    return plan, lines, run


@pytest.fixture(scope="module")
def offline():
    with pytest.MonkeyPatch.context() as patch:
        for key, value in OFFLINE_ENV.items():
            patch.setenv(key, value)
        yield


def test_marks_through_the_search(tmp_path, offline):
    """Each line end's answer is the access grid's at its pixel (access.access_grid of the search's terrain, the
    alpine variant on), uint8: the west rim by the meadow easy access (2), the east rim above the slope of 45
    degrees cannot tell (1), the tower's top hard access (0); the search prints no note of filled anchors."""
    z = scene()
    events = []
    plan, lines, _ = _search(tmp_path, z, "float", events)
    rows, cols, answers = _ends(lines.results)
    assert lines.results.columns["access1"].dtype == lines.results.columns["access2"].dtype == np.uint8
    assert len(rows) > 50 and np.array_equal(answers, _grid_answers(plan, z, rows, cols))
    tower = (rows >= 140) & (rows < 148) & (cols >= 146) & (cols < 154)
    assert tower.any() and set(answers[tower].tolist()) == {access.CANNOT}
    assert (cols == WEST_RIM).any() and set(answers[cols == WEST_RIM].tolist()) == {access.CAN}
    assert (cols == EAST_RIM).any() and set(answers[cols == EAST_RIM].tolist()) == {access.UNSURE}
    assert not [text for _, text in events if "on filled data" in str(text)]


def test_whole_metres_and_the_end_of_the_data(tmp_path, offline):
    """On whole-metre heights the smoothed copy decides too (access.access_grid's whole_metres: the rim by the
    meadow cannot tell where the float heights say easy access), and beside the end of the data a rim no walk
    reaches cannot tell (never hard access): through the search as the grid says."""
    whole = scene(whole=True)
    assert access.whole_metres(whole.ravel()) and not access.whole_metres(scene().ravel())
    plan, lines, _ = _search(tmp_path, whole, "whole")
    rows, cols, answers = _ends(lines.results)
    assert np.array_equal(answers, _grid_answers(plan, whole, rows, cols))
    assert (cols == WEST_RIM).any() and access.UNSURE in answers[cols == WEST_RIM].tolist()
    ended = scene(no_data=True)
    plan, lines, _ = _search(tmp_path, ended, "ended")
    rows, cols, answers = _ends(lines.results)
    assert np.array_equal(answers, _grid_answers(plan, ended, rows, cols))
    assert (cols == WEST_RIM).any() and set(answers[cols == WEST_RIM].tolist()) == {access.UNSURE}


def test_anchors_take_the_measures_own_answer():
    """search._access_columns: each anchor's answer is the access grid's at its pixel, also on a filled pixel or a
    shore face (the answer of the data around it, as the study's); an anchor on a pixel without heights is refused."""
    grid = np.array([[2, 0, 1, 0], [1, 2, 0, 1], [0, 1, 2, 0], [2, 2, 1, 0]], np.uint8)
    filled = np.zeros((4, 4), bool)
    filled[1, 1] = filled[2, 2] = filled[0, 0] = True
    data = search.Data(np.full((4, 4), 5.0, np.float32), None, None, filled, None, access=grid)
    a1, a2 = np.array([[1, 1], [2, 2], [3, 3], [0, 0]]), np.array([[3, 3], [1, 1], [0, 0], [0, 2]])
    lines = sh.LineTable({"a1": a1, "a2": a2})
    search._access_columns(None, lines, data)
    assert lines.columns["access1"].tolist() == grid[a1[:, 0], a1[:, 1]].tolist() == [2, 2, 0, 2]
    assert lines.columns["access2"].tolist() == grid[a2[:, 0], a2[:, 1]].tolist() == [0, 2, 2, 1]
    assert lines.columns["access1"].dtype == np.uint8
    data.elevation[3, 3] = np.nan
    with pytest.raises(AssertionError):
        search._access_columns(None, sh.LineTable({"a1": a1, "a2": a2}), data)


def _canyon(tilt: float = 0.02) -> np.ndarray:
    """A canyon 40 m wide and 50 m deep between two meadows (open ground), the heights tilting so no flat region
    reads as a lake held as data."""
    z = np.full((SIZE, SIZE), 150.0)
    z[:, 130:170] = 100.0
    return z + tilt * np.arange(SIZE)[:, None] + 0.25


def test_water_and_filled_reach_the_measure(tmp_path, monkeypatch):
    """Through the search with the water filled and gaps filled from a fallback: the measure is given the search's
    water and its filled pixels. Along each rim a band of meadow 3 m wide (the rim's standing ground) is cut off from
    the meadow behind it by a strip 6 m wide closed at both ends: a lake (700 m2, too small to read as a flat lake
    held as data) on the west, a gap filled from the fallback on the east. The west rim beside it is hard access (no
    walk crosses the water), where without the water mask the lake's level would be walked on (easy access); the
    east rim cannot tell (the filled gap is no data for the walk and an end of the data), where filled pixels taken
    as data would be walked on (easy access). Elsewhere both rims are easy access."""
    import sources as src
    z = _canyon()
    terrain = z.copy()
    water = np.zeros((SIZE, SIZE), np.uint8)
    for cols in (slice(120, 126), slice(174, 180)):  # the strips behind the bands (cols 126-128, 171-173)
        terrain[100:200, cols] = np.nan
    for cols in (slice(120, 129), slice(171, 180)):  # closed at both ends
        terrain[100:104, cols] = terrain[196:200, cols] = np.nan
    water[100:200, 120:129] = src.LAKE
    water[104:196, 126:129] = 0  # the band is land with data
    write_raster(tmp_path / "nmt.tif", terrain.astype(np.float32), LEFT, TOP)
    _water_and_fallback(tmp_path, monkeypatch, water, z.astype(np.float32), LEFT, TOP)
    params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2,
                          radius=135, resolution=1, nmpt="off", water="fill", fill_gaps="on", coastline="copernicus",
                          min_length=10, max_length=80, slope_threshold=60, prominence_span=10, drop_radius=10,
                          ortho="never", name="inputs", access=True)
    paths = search.Paths(str(tmp_path / "inputs"), str(tmp_path / "inputs" / "work"))
    os.makedirs(paths.work)
    plan = search.plan_search(params, paths, lambda kind, text: None)
    lines, _ = search.search_lines(plan)
    rows, cols, answers = _ends(lines.results)
    beside = (rows >= 106) & (rows < 194)
    away = (rows < 96) | (rows >= 204)
    for rim, state in ((WEST_RIM, access.CANNOT), (EAST_RIM, access.UNSURE)):
        assert (beside & (cols == rim)).sum() > 10 and set(answers[beside & (cols == rim)].tolist()) == {state}, rim
        assert (away & (cols == rim)).any() and set(answers[away & (cols == rim)].tolist()) == {access.CAN}, rim


def test_the_alpine_variant_through_the_search(tmp_path, offline):
    """The search uses the alpine variant (the user's choice): two towers on a slope of 35 degrees with no open ground
    within 250 m, whose tops no walk reaches: cannot tell (the share of open ground around them is under 5 %), where
    the study's main measure says hard access."""
    rows = width = SIZE
    z = 100 + np.tan(np.radians(35)) * np.arange(rows)[:, None] + np.zeros((rows, width))
    top = 100 + np.tan(np.radians(35)) * 150 + 50
    z[146:154, 120:128] = top
    z[146:154, 170:178] = top
    z = (z + 0.25).astype(np.float32)
    write_raster(tmp_path / "alpine.tif", z, LEFT, TOP)
    params = SearchParams(elevation_file=str(tmp_path / "alpine.tif"), northing=TOP - rows / 2,
                          easting=LEFT + width / 2, radius=135, resolution=1, nmpt="off", water="off",
                          fill_gaps="off", min_length=10, max_length=80, slope_threshold=60, prominence_span=10,
                          drop_radius=10, ortho="never", name="alpine", access=True)
    paths = search.Paths(str(tmp_path / "alpine"), str(tmp_path / "alpine" / "work"))
    os.makedirs(paths.work)
    plan = search.plan_search(params, paths, lambda kind, text: None)
    lines, _ = search.search_lines(plan)
    c = lines.results.columns
    ends = np.concatenate([c["a1_xy"], c["a2_xy"]])
    answers = np.concatenate([c["access1"], c["access2"]])
    on_top = np.isclose(np.concatenate([c["elev_a1"], c["elev_a2"]]), top + 0.25, atol=0.05)
    assert on_top.sum() > 10 and set(answers[on_top].tolist()) == {access.UNSURE}
    g = plan.grid
    r = np.round((g.top - ends[on_top, 1]) / g.res - 0.5).astype(int)
    k = np.round((ends[on_top, 0] - g.left) / g.res - 0.5).astype(int)
    window = z[int(TOP - g.top):int(TOP - g.top) + g.height, int(g.left - LEFT):int(g.left - LEFT) + g.width]
    assert set(access.access_grid(window, None, 1.0, alpine=False)[r, k].tolist()) == {access.CANNOT}


def test_a_mid_face_ledge_is_hard_access(tmp_path, offline):
    """Spec 3.7: a ledge halfway down both walls of a canyon (8 m wide, 200 m long, 25 m below the meadows' rims and
    25 m above the floor): lines between the two ledges' edges read hard access at both ends, lines between the
    rims easy access."""
    z = np.full((SIZE, SIZE), 150.0)
    z[:, 130:170] = 100.0
    z[50:250, 122:130] = 125.0  # the west ledge
    z[50:250, 170:178] = 125.0  # the east ledge
    z = (z + 0.02 * np.arange(SIZE)[:, None] + 0.25).astype(np.float32)
    _, lines, _ = _search(tmp_path, z, "ledge")
    c = lines.results.columns
    elev = np.concatenate([c["elev_a1"], c["elev_a2"]])
    answers = np.concatenate([c["access1"], c["access2"]])
    rows, cols, _ = _ends(lines.results)
    ledge = (np.abs(elev - (125.25 + 0.02 * rows)) < 0.5) & ((cols == 129) | (cols == 170))
    rim = (np.abs(elev - (150.25 + 0.02 * rows)) < 0.5) & ((rows < 46) | (rows >= 254))
    assert ledge.sum() > 10 and set(answers[ledge].tolist()) == {access.CANNOT}
    assert rim.sum() > 10 and set(answers[rim].tolist()) == {access.CAN}


def _rough(whole: bool) -> np.ndarray:
    """A made-up grid of 600 x 600 pixels at 5 m (3 km, over 2 x access.MARGIN_M): hills, two canyons, a few
    meadows and a hole without data."""
    from scipy import ndimage
    if whole is None:
        return _path()
    rng = np.random.default_rng(11)
    z = ndimage.gaussian_filter(rng.normal(0, 1, (600, 600)), 25) * 4000 + 400
    z[:, 200:216] -= 80  # a canyon
    z[380:396, :] -= 60  # another
    z[40:120, 400:520] = 450.0 + 0.3 * np.arange(80)[:, None]  # a meadow
    z[450:470, 60:90] = np.nan
    z = z + 0.37
    return (np.round(z) if whole else z).astype(np.float32)


def _path() -> np.ndarray:
    """600 x 600 pixels at 5 m: a slope of 35 degrees (walkable, no open ground) with a level path along it, the only
    open ground (the middle row of three flat ones: 3 km x 5 m, 1.5 ha), from which the walk reaches the slope, and
    a canyon (the lines). A window of a block holds less than 1 ha of the path: judged alone it has no open ground."""
    z = 100 + np.tan(np.radians(35)) * 5 * np.arange(600)[:, None] + np.zeros((600, 600))
    z[300:303] = z[301] + 0.1 * np.arange(600)  # rising 1 in 50 along it: no flat lake held as data
    z[:250, 280:296] -= 40  # the canyon, ending 250 m before the path
    return (z + 0.37).astype(np.float32)


@pytest.mark.parametrize("whole", [False, True, None], ids=["float", "whole-metres", "path"])
def test_blocks_give_one_grids_answers(tmp_path, offline, monkeypatch, whole):
    """The access grid in blocks (access.block_grid: the grid-wide judgements once, every block from its window of
    access.margin_px) equals the grid at once at every pixel, on made-up grids of 3 km at 5 m in blocks of 300 m
    (many windows, most inside the grid), on float and on whole-metre heights, and where the only open ground is a
    path whose part in any window is under 1 ha (a window judged alone would find none); and through the search the
    lines' marks are the same."""
    import rasterio as rio
    from rasterio.transform import from_origin
    z = _rough(whole)
    path = tmp_path / "rough.tif"
    with rio.open(path, "w", driver="GTiff", width=600, height=600, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(LEFT, TOP, 5, 5), nodata=np.nan) as dst:
        dst.write(z, 1)
    params = SearchParams(elevation_file=str(path), northing=TOP - 1500, easting=LEFT + 1500, radius=1400,
                          resolution=5, nmpt="off", water="off", fill_gaps="off", min_length=50, max_length=300,
                          slope_threshold=55, prominence_span=10, drop_radius=10, ortho="never", name="rough",
                          access=True)
    runs = {}
    for name, block in (("one", None), ("blocks", 60)):
        events = []
        monkeypatch.setattr(search, "_access_block_px", lambda plan, block=block: block)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = search.plan_search(params, paths, lambda kind, text: events.append(str(text)))
        data = search.prepare_data(plan)
        runs[name] = np.array(search._access_grid(plan, data))
        lines = search.find_lines(plan, data)
        runs[name + "-lines"] = {k: lines.results.columns[k] for k in ("a1_xy", "a2_xy", "access1", "access2")}
        if block:
            blocks = [e for e in events if e.startswith("Access to anchors in ")]
            assert blocks and int(blocks[0].split()[4]) > 50, blocks
        del data
    assert runs["one"].shape == (plan.grid.height, plan.grid.width) and len(set(runs["one"].ravel().tolist())) >= 2
    assert np.array_equal(runs["one"], runs["blocks"])
    for k, v in runs["one-lines"].items():
        assert len(v) > 20 and np.array_equal(v, runs["blocks-lines"][k]), k
    assert access.whole_metres(z[np.isfinite(z)]) == bool(whole)
    if whole is None:  # the walk from the path (open ground of the whole grid only) reaches the slope around it
        assert (runs["one"] == access.CAN).sum() > 10000


# --- The grid-wide judgements of the blocks, each on a grid where it decides answers (code review 2 of 1d-2) ---

def _hills(n: int, m: int, res: float, seed: int, relief: float = 60.0) -> np.ndarray:
    """Made-up hills with two canyons and a block of rock (walls), n x m pixels at res."""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    z = ndimage.gaussian_filter(rng.normal(0, 1, (n, m)), 30 / res * 5) * relief * 400 / res + 300
    z[:, m // 3:m // 3 + max(3, int(40 / res))] -= 70
    z[n // 2:n // 2 + max(3, int(30 / res)), :] -= 50
    z[n // 5:n // 5 + 40, m // 2:m // 2 + 40] += 60
    return z


def _lakes(z: np.ndarray) -> np.ndarray:
    """Flat lakes held as data on float heights: a long thin one crossing the blocks (spread 0.1 m: kept by the
    lowest/highest), one with a cone of 0.8 m on 3 % of it (p95 - p5 under 0.3 m: kept by the exact percentiles)
    across a strip's edge, and a large flat region rising 0.5 m (refused by them)."""
    n, m = z.shape
    rng = np.random.default_rng(1)
    z[40:46, 20:m - 20] = 250.0 + rng.uniform(0, 0.1, (6, m - 40))
    k = n - 140
    z[k:k + 40, 30:200] = 240.0 + rng.uniform(0, 0.2, (40, 170))
    rr, cc = np.mgrid[0:40, 0:170]
    z[k:k + 40, 30:200] += np.maximum(0.0, 0.8 * (1 - np.hypot(rr - 20, cc - 60) / 8.0))
    z[100:300, m - 260:m - 60] = 260.0 + np.linspace(0, 0.5, 200)[:, None]
    return z


def _mixed() -> np.ndarray:
    """Heights whole metres over 90 % of the grid but not in its west part: whole metres only as a whole."""
    z = _hills(640, 700, 5.0, 4)
    mixed = np.round(z)
    mixed[:, :60] = z[:, :60] + 0.37
    return mixed.astype(np.float32)


def _smoothed_path() -> np.ndarray:
    """Whole metres on a slope of 35 degrees with a level path 5 pixels wide (its middle open ground on the smoothed
    heights too, 1.5 ha only as a whole: a window holds less than 1 ha of it), at 5 m."""
    z = 100 + np.tan(np.radians(35)) * 5 * np.arange(600)[:, None] + np.zeros((600, 600))
    z[298:303] = z[300] + 0.1 * np.arange(600)
    return np.round(z).astype(np.float32)


GRID_CASES = {
    "lakes": lambda: _lakes(_hills(760, 820, 5.0, 2)).astype(np.float32),
    "mixed": _mixed,
    "smoothed-path": _smoothed_path,
    "path": lambda: _path(),
}


@pytest.mark.parametrize("case", list(GRID_CASES))
def test_block_grid_equals_one_grid_where_the_whole_grid_decides(tmp_path, monkeypatch, case):
    """access.block_grid = access.access_grid at every pixel on grids where a grid-wide judgement decides answers
    that a window alone would get wrong: flat lakes held as data crossing blocks and strips (kept by the lowest and
    highest, by the exact percentiles, one refused), heights whole metres only as a whole, open ground on the smoothed
    heights only the whole grid sees, open ground only the whole grid sees; the grid-wide pass in strips of 64 rows
    (their halos), blocks of 60 pixels (300 m at 5 m) and few flat heights gathered at a time
    (access.GATHER_PX). The work folder holds only the grid afterwards (no scratch file left)."""
    z = GRID_CASES[case]()
    res = 5.0
    one = access.access_grid(z, None, res, alpine=True)
    monkeypatch.setattr(access, "STRIP_PX", 1)  # 64 rows a strip
    monkeypatch.setattr(access, "GATHER_PX", 5_000)
    work = tmp_path / "work"
    done = access.block_grid(z, None, res, None, str(work / "access.npy"), str(work), 60, alpine=True)
    blocks = np.array(np.load(work / "access.npy", mmap_mode="r"))
    assert done["blocks"] > 50 and np.array_equal(blocks, one), int((blocks != one).sum())
    assert os.listdir(work) == ["access.npy"]
    if case == "lakes":  # the lakes decide answers: without them the grid differs
        s = access.slope_deg(z, res)
        assert access.flat_water(z, s, res).sum() > 3000
        assert not access.whole_metres(z[np.isfinite(z)])
    if case == "mixed":  # whole metres only as a whole
        assert access.whole_metres(z[np.isfinite(z)]) and not access.whole_metres(z[:, :300].ravel())
    if case in ("smoothed-path", "path"):
        assert (one == access.CAN).sum() > 10000


@pytest.mark.parametrize("whole", [False, True], ids=["float", "whole-metres"])
def test_block_grid_leaves_no_scratch_file(tmp_path, whole):
    """After access.block_grid the work folder holds the grid only (the grid-wide masks and labels removed: no view of
    a map left at its removal), on float and on whole-metre heights, with lakes held as data on float."""
    z = _lakes(_hills(400, 420, 5.0, 8))
    z = (np.round(z) if whole else z).astype(np.float32)
    work = tmp_path / "work"
    access.block_grid(z, None, 5.0, None, str(work / "access.npy"), str(work), 100, alpine=True)
    assert os.listdir(work) == ["access.npy"]


def test_a_walk_too_large_is_refused(tmp_path, monkeypatch):
    """A grid at once, or a block's window, of access.WALK_PX_MAX pixels or more is refused (the walk's int32
    indices); the search's block rule keeps every window under it."""
    monkeypatch.setattr(access, "WALK_PX_MAX", 400)
    z = _hills(30, 30, 5.0, 3).astype(np.float32)
    with pytest.raises(ValueError):
        access.access_grid(z, None, 5.0)
    with pytest.raises(ValueError):
        access.block_grid(z, None, 5.0, None, str(tmp_path / "a.npy"), str(tmp_path), 10)
    small = z[:19, :20]
    assert access.access_grid(small, None, 5.0).shape == small.shape


def test_blocks_from_the_free_memory(tmp_path, offline, monkeypatch):
    """Without Plan.memory (the command line) the access grid's budget is the memory free (search.available_memory):
    a small one gives blocks, the same answers as at once."""
    z = _rough(False)
    path = tmp_path / "rough.tif"
    _write_5m(path, z)
    params = SearchParams(elevation_file=str(path), northing=TOP - 1500, easting=LEFT + 1500, radius=1400,
                          resolution=5, nmpt="off", water="off", fill_gaps="off", min_length=50, max_length=300,
                          slope_threshold=55, prominence_span=10, drop_radius=10, ortho="never", name="free",
                          access=True)
    grids = {}
    for name, free in (("at-once", 10 ** 12), ("blocks", 8_000_000)):
        monkeypatch.setattr(search, "available_memory", lambda free=free: free)
        events = []
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = search.plan_search(params, paths, lambda kind, text: events.append(str(text)))
        assert plan.memory is None
        grids[name] = np.array(search._access_grid(plan, search.prepare_data(plan)))
        made = [e for e in events if e.startswith("Access to anchors in ")]
        assert bool(made) == (name == "blocks"), made
    assert np.array_equal(grids["at-once"], grids["blocks"])


def _write_5m(path, z):
    import rasterio as rio
    from rasterio.transform import from_origin
    with rio.open(path, "w", driver="GTiff", width=z.shape[1], height=z.shape[0], count=1, dtype="float32",
                  crs="EPSG:2180", transform=from_origin(LEFT, TOP, 5, 5), nodata=np.nan) as dst:
        dst.write(z, 1)


def test_a_tiled_search_in_blocks(tmp_path, offline, monkeypatch):
    """A tiled search whose access grid is made in blocks (a small budget of free memory) gives the lines and marks of
    the same tiled search with the grid at once; no grid of the work folder is left after the tiles."""
    z = _rough(False)
    path = tmp_path / "rough.tif"
    _write_5m(path, z)
    area = _square(tmp_path / "square.geojson", LEFT + 300, TOP - 2700, LEFT + 2700, TOP - 300)
    params = SearchParams(elevation_file=str(path), area=area, resolution=5, nmpt="off", water="off",
                          fill_gaps="off", min_length=50, max_length=300, slope_threshold=55, prominence_span=10,
                          drop_radius=10, ortho="never", tile_size=800, name="tiled", access=True)
    tables = {}
    for name, free in (("at-once", 10 ** 12), ("blocks", 6_000_000)):
        monkeypatch.setattr(search, "available_memory", lambda free=free: free)
        events = []
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = dataclasses.replace(search.plan_search(params, paths, lambda kind, text: events.append(str(text))),
                                   index_runs=False)
        assert plan.tiles and len(plan.tiles) > 1
        lines, run = search.search_lines(plan)
        made = [e for e in events if e.startswith("Access to anchors in ")]
        assert bool(made) == (name == "blocks"), made
        assert not glob.glob(os.path.join(paths.work, "*.npy"))
        c = lines.results.columns
        tables[name] = {k: c[k] for k in ("a1_xy", "a2_xy", "access1", "access2")}
    for k, v in tables["at-once"].items():
        assert len(v) > 20 and np.array_equal(v, tables["blocks"][k]), k


@pytest.mark.parametrize("tiled", [False, True], ids=["one-grid", "tiles"])
def test_the_access_stage_after_the_estimate(tmp_path, offline, monkeypatch, tiled):
    """The access grid is made after the cheap refusals: a search the 2 % estimate refuses (the line limit) never
    computes it, as one grid and as tiles."""
    import settings
    calls = []
    real = search._access_grid
    monkeypatch.setattr(search, "_access_grid", lambda *a, **k: calls.append(1) or real(*a, **k))
    z = scene()
    write_raster(tmp_path / "est.tif", z, LEFT, TOP)
    values = dict(elevation_file=str(tmp_path / "est.tif"), resolution=1, nmpt="off", water="off", fill_gaps="off",
                  min_length=10, max_length=80, slope_threshold=60, prominence_span=10, drop_radius=10,
                  ortho="never", name="est", access=True)
    if tiled:
        values.update(area=_square(tmp_path / "sq.geojson", LEFT + 20, TOP - SIZE + 20, LEFT + SIZE - 20, TOP - 20),
                      tile_size=100)
    else:
        values.update(northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2, radius=135)
    paths = search.Paths(str(tmp_path / "est"), str(tmp_path / "est" / "work"))
    os.makedirs(paths.work)
    plan = search.plan_search(SearchParams(**values), paths, lambda kind, text: None,
                              limits=settings.Limits(lines_max=1))
    assert bool(plan.tiles) == tiled
    with pytest.raises(search.SearchError) as refused:
        search.search_lines(plan)
    assert refused.value.code == "too_many_lines_estimate" and calls == []


def test_access_memory_refused_and_blocks_sized(tmp_path, offline):
    """With --access a search whose access grid cannot fit Plan.memory even in its smallest blocks is refused before
    step 1 (the coded error access_memory, its page text without option names); a search that fits keeps one block
    or gets the largest blocks the memory leaves (search._access_block_px); without the option nothing changes."""
    z = scene()
    write_raster(tmp_path / "mem.tif", z, LEFT, TOP)
    values = dict(elevation_file=str(tmp_path / "mem.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2,
                  radius=135, resolution=1, nmpt="off", water="off", fill_gaps="off", ortho="never", name="m")
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    plan = search.plan_search(SearchParams(**values, access=True), paths, lambda k, t: None, memory=10 ** 9)
    h, w = plan.grid.height, plan.grid.width
    pixels, block = h * w, 500 + 2 * access.margin_px(1.0)
    need = min(pixels * search.ACCESS_WINDOW_BYTES,
               pixels * search.ACCESS_AREA_BYTES + min(h, block) * min(w, block) * search.ACCESS_WINDOW_BYTES)
    assert search.access_memory(plan) == need
    assert search._access_block_px(plan) is None  # the grid at once
    with pytest.raises(search.SearchError) as refused:
        search.plan_search(SearchParams(**values, access=True), paths, lambda k, t: None, memory=need - 1)
    assert refused.value.code == "access_memory" and "--" not in refused.value.web_text()
    search.plan_search(SearchParams(**values), paths, lambda k, t: None, memory=1000)  # the option off: no check
    big = dataclasses.replace(plan, memory=pixels * search.ACCESS_WINDOW_BYTES - 1)
    side = int(np.sqrt((big.memory - pixels * search.ACCESS_AREA_BYTES) / search.ACCESS_WINDOW_BYTES))
    assert search._access_block_px(big) == max(500, side - 2 * access.margin_px(1.0))


def test_disk_estimate_counts_the_access_grid(tmp_path, offline):
    """With --access the disk estimate counts the access grid's files of the whole grid (search.ACCESS_DISK_BYTES:
    blocks at most) and a tile's copy of its window (search.tile_bytes, 1 B per pixel); off, nothing."""
    write_raster(tmp_path / "disk.tif", scene(), LEFT, TOP)
    area = _square(tmp_path / "square.geojson", LEFT + 20, TOP - SIZE + 20, LEFT + SIZE - 20, TOP - 20)
    plans = {}
    for on in (False, True):
        params = SearchParams(elevation_file=str(tmp_path / "disk.tif"), area=area, max_length=80, nmpt="off",
                              water="off", fill_gaps="off", ortho="never", tile_size=100, name="d", access=on,
                              prominence_span=10, drop_radius=10)
        plans[on] = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")),
                                       lambda k, t: None)
    assert plans[True].tiles and search.tile_bytes(plans[True]) == search.tile_bytes(plans[False]) + 1
    pixels = plans[True].grid.width * plans[True].grid.height
    largest = max(t.width * t.height for _, t in plans[True].tiles)
    off, on = (search.estimate_search(plans[k]).work_gb for k in (False, True))
    assert on - off == pytest.approx((pixels * search.ACCESS_DISK_BYTES + largest) / 1e9)


@pytest.fixture(scope="module")
def scene_runs(tmp_path_factory, offline):
    """The float scene searched without and with --access, each saved by search.save_run: {name: run folder}."""
    folder = tmp_path_factory.mktemp("scene-runs")
    runs = {}
    for name, on in (("off", False), ("on", True)):
        plan = _plan(folder, scene(), name, access=on)
        lines, _ = search.search_lines(plan)
        path = folder / name / "runs" / name
        path.mkdir(parents=True)
        search.save_run(plan, lines, {"id": name, "path": str(path), "created": datetime(2026, 11, 15, 12),
                                      "name": name})
        runs[name] = path
    return runs


def _script(path) -> dict:
    text = open(path, encoding="utf-8").read()
    return json.loads(text[text.index(" = {") + 3:].rstrip().rstrip(";"))


def test_files_with_the_option_and_without(scene_runs):
    """Off: no column, no "ends", run.json's params and the search's key without "access". On: lines.csv and
    lines.geojson hold access1, access2 after the anchors' columns (the rest byte for byte the run without the
    option), data.js and lines.js two values before the profile named by "ends", run.json's params "access": true,
    the store two uint8 columns read back as the search's and exported as lines.csv byte for byte."""
    off, on = scene_runs["off"], scene_runs["on"]
    meta = {name: json.loads((folder / "run.json").read_text(encoding="utf-8")) for name, folder in scene_runs.items()}
    assert "access" not in meta["off"]["params"] and meta["on"]["params"]["access"] is True
    assert meta["on"]["summary"]["lines"] == meta["off"]["summary"]["lines"] > 50
    # lines.csv: the on run's less its two columns is the off run's, byte for byte
    table = (on / "lines.csv").read_bytes().decode("utf-8-sig").split("\r\n")
    header = table[0].split(",")
    assert header[-2:] == rn.ACCESS and header[:-2] == rn.FIELDS
    cut = "\r\n".join(",".join(row.split(",")[:-2]) for row in table[:-1]) + "\r\n"
    assert cut.encode("utf-8-sig") == (off / "lines.csv").read_bytes()
    assert {row.split(",")[-1] for row in table[1:-1]} <= {"0", "1", "2"}
    # lines.geojson: the same features with two properties more, the same "findaline" but its params
    geo = {name: json.loads((folder / "lines.geojson").read_text(encoding="utf-8"))
           for name, folder in scene_runs.items()}
    for feature in geo["on"]["features"]:
        assert list(feature["properties"])[-2:] == rn.ACCESS
        for name in rn.ACCESS:
            assert feature["properties"].pop(name) in (0, 1, 2)
    assert geo["on"]["features"] == geo["off"]["features"]
    # data.js and lines.js: two values before the profile, "ends" names them; nothing else differs
    for file, profiles in (("data.js", True), ("lines.js", False)):
        heads = {name: _script(folder / file) for name, folder in scene_runs.items()}
        assert "ends" not in heads["off"] and heads["on"]["ends"] == rn.ACCESS
        rows = heads["on"].pop("lines")
        cut = [row[:-3] + row[-1:] if profiles else row[:-2] for row in rows]
        assert cut == heads["off"].pop("lines")
        assert {v for row in rows for v in (row[-3:-1] if profiles else row[-2:])} <= {0, 1, 2}
        heads["on"].pop("ends")
        for head in heads.values():
            head.pop("run", None)
        assert heads["on"] == heads["off"], file
    # the store: two uint8 columns, read back as the search wrote them, exported as the run's lines.csv
    import pyarrow as pa
    with pa.OSFile(str(on / linestore.LINES_FILE), "rb") as source:
        schema = pa.ipc.open_file(source).schema
    assert [schema.field(name).type for name in rn.ACCESS] == [pa.uint8(), pa.uint8()]
    with pa.OSFile(str(off / linestore.LINES_FILE), "rb") as source:
        assert not set(rn.ACCESS) & set(pa.ipc.open_file(source).schema.names)
    lines, _ = linestore.read(str(on), profiles=False)
    assert lines.columns["access1"].dtype == np.uint8
    linestore.export(str(on), "csv", str(on / "export.csv"))
    assert (on / "export.csv").read_bytes() == (on / "lines.csv").read_bytes()
    linestore.export(str(on), "geojson", str(on / "export.geojson"))
    assert (on / "export.geojson").read_bytes() == (on / "lines.geojson").read_bytes()


def test_search_key_without_the_option(tmp_path, offline):
    """The search's key (the hash a tiled search resumes by, and the 2 % sample's seed) has no "access" when the
    option is off, so unfinished searches of before resume; with it on the key holds it and the hash differs."""
    z = scene()
    on = _plan(tmp_path, z, "key-on")
    off = _plan(tmp_path, z, "key-off", access=False, elevation_file=str(tmp_path / "key-on.tif"))  # one file
    assert "access" not in search._search_key(off)["params"] and search._search_key(on)["params"]["access"] is True
    assert search._search_hash(off) != search._search_hash(on)
    key = search._search_key(on)
    key["params"].pop("access")
    assert search._hash_of(key) == search._search_hash(off)


def test_tiles_give_one_grids_answers(tmp_path, monkeypatch):
    """With --access an area computed in tiles gives exactly the lines of one grid, their access too, with the sea
    and a lake filled and gaps on land filled from a fallback (the clip of
    test_offline.py::test_area_in_tiles_with_water_and_gaps): the access grid is computed once on the whole grid
    (access.npy in the work folder, removed after the last tile) and each tile reads its window."""
    import rasterio as rio
    import sources as src
    from scipy import ndimage
    with rio.open(os.path.join(DATA, "zabi_kon_nmt.tif")) as s:
        terrain, left, top = s.read(1), s.bounds.left, s.bounds.top
    with rio.open(os.path.join(DATA, "zabi_kon_nmpt.tif")) as s:
        surface = s.read(1)
    fallback = (ndimage.uniform_filter(terrain, 5) + 1.5).astype(np.float32)
    size = terrain.shape[0]
    terrain[:, :80] = surface[:, :80] = np.nan  # the sea in the west, without data
    terrain[200:260, 300:360] = surface[200:260, 300:360] = np.nan  # a lake
    terrain[400:430, 150:190] = surface[400:430, 150:190] = np.nan  # gaps on land
    terrain[290:310, 240:260] = surface[290:310, 240:260] = np.nan
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)
    water = np.zeros((size, size), np.uint8)
    water[:, :85] = src.OCEAN
    water[195:265, 295:365] = src.LAKE
    _water_and_fallback(tmp_path, monkeypatch, water, fallback, left, top)
    area = _square(tmp_path / "square.geojson", left + 40, top - size + 60, left + size - 60, top - 40)
    computed = []
    grid_of = search._access_grid
    monkeypatch.setattr(search, "_access_grid", lambda *a, **k: computed.append(a[2] if len(a) > 2 else None)
                        or grid_of(*a, **k))
    runs = {}
    for name, tile_size in (("one", None), ("tiled", 150)):
        params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                              area=area, max_length=150, water="fill", fill_gaps="on", coastline="copernicus",
                              ortho="never", tile_size=tile_size, access=True, name=name)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = dataclasses.replace(search.plan_search(params, paths, lambda kind, text: None), index_runs=False)
        assert bool(plan.tiles) == (tile_size is not None)
        lines, run = search.search_lines(plan)
        c = lines.results.columns
        assert (c["water_m"] > 0).any() and (c["filled_m"] > 0).any()
        assert len(set(c["access1"].tolist()) | set(c["access2"].tolist())) >= 2
        result = search.save_run(plan, lines, run)
        runs[name] = result.run["path"]
        if plan.tiles:
            assert not glob.glob(os.path.join(paths.work, "*.npy"))  # access.npy too, after the tiles
    assert computed == [None, os.path.join(str(tmp_path / "tiled" / "work"), search.ACCESS_FILE)]  # once each
    read = lambda name, file: open(os.path.join(runs[name], file), "rb").read()  # noqa: E731
    assert read("one", "lines.csv") == read("tiled", "lines.csv") and b",access1,access2" in read("one", "lines.csv")
    for file in ("data.js", "lines.js"):
        rows = {name: _script(os.path.join(runs[name], file))["lines"] for name in ("one", "tiled")}
        assert sorted(map(json.dumps, rows["one"])) == sorted(map(json.dumps, rows["tiled"])), file
    assert len(glob.glob(os.path.join(runs["tiled"], "tiles", "*.table.pkl.gz"))) > 1
    # with the square rule too: the access columns pass the reducer and the join of the tiles' kept lines
    kept = {}
    for name, tile_size in (("one-square", None), ("tiled-square", 150)):
        params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                              area=area, max_length=150, water="fill", fill_gaps="on", coastline="copernicus",
                              ortho="never", tile_size=tile_size, access=True, same_line_square=5, name=name)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = dataclasses.replace(search.plan_search(params, paths, lambda kind, text: None), index_runs=False)
        lines, run = search.search_lines(plan)
        kept[name] = search.save_run(plan, lines, run).run["path"]
    table = open(os.path.join(kept["one-square"], "lines.csv"), "rb").read()
    assert table == open(os.path.join(kept["tiled-square"], "lines.csv"), "rb").read()
    assert b",access1,access2,stands_for\r\n" in table[:2000]


def test_the_store_note_is_coded(tmp_path, offline, monkeypatch):
    """A store that cannot be written: the warning is a coded note (error.store_failed) whose page text holds no
    exception text (it may hold paths); the command line's text names the error as before."""
    events = []
    plan = _plan(tmp_path, scene(), "note", events, access=False)
    lines, _ = search.search_lines(plan)

    def failing(run_path, lines, head):
        raise MemoryError(r"no memory at C:\secret\path")
    monkeypatch.setattr(linestore, "write", failing)
    folder = tmp_path / "note" / "runs" / "note"
    folder.mkdir(parents=True)
    search.save_run(plan, lines, {"id": "note", "path": str(folder), "created": datetime(2026, 11, 15), "name": "n"})
    notes = [text for kind, text in events if kind == "warning" and "store" in str(text)]
    assert len(notes) == 1 and isinstance(notes[0], messages.Note) and notes[0].code == "store_failed"
    assert str(notes[0]) == r"The run is saved without its store (lines.arrow): MemoryError: no memory at C:\secret\path"
    assert notes[0].web_text() == messages.text("error.store_failed") and "secret" not in notes[0].web_text()
    assert "store" not in json.loads((folder / "run.json").read_text(encoding="utf-8"))


def test_favourite_keeps_the_access_mark():
    """web.FavouriteLine: access1 and access2 optional (0, 1 or 2; kept only when given, as the A-frame heights);
    anything else refused."""
    import web
    values = {"len": 50.0, "clr": 2.0, "clrN": None, "e1": 10.0, "e2": 11.0, "over": False, "water": 0.0,
              "filled": 0.0, "hmax": 5.0, "hmean": 3.0, "highPct": 40.0, "angle1": 10.0, "angle2": 12.0,
              "prom1": None, "prom2": None, "drop1": None, "drop2": None}
    request = lambda data: {"line": "50.1,19.1,50.2,19.2", "favourite": True, "data": data}  # noqa: E731
    _, stored = web.checked_favourite(request(values))
    assert "access1" not in stored and "access2" not in stored
    _, stored = web.checked_favourite(request({**values, "access1": 2, "access2": 0}))
    assert (stored["access1"], stored["access2"]) == (2, 0)
    _, stored = web.checked_favourite(request({**values, "access1": None, "access2": 1}))
    assert "access1" not in stored and stored["access2"] == 1
    for wrong in (3, -1, 1.5, True, "2"):
        with pytest.raises(ValueError):
            web.checked_favourite(request({**values, "access1": wrong}))


def test_web_process_never_imports_access(tmp_path):
    """The web app (create_app) imports neither access.py nor numba nor search (heavy work only in the worker)."""
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            f"web.create_app({str(tmp_path)!r}, token='t', start_scheduler=False)\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in ('access', 'numba', 'search'))))")
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                            timeout=300, env={**os.environ, **OFFLINE_ENV})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_warm_up_compiles_the_access_kernels(tmp_path):
    """warmup.warm_up compiles access.py's kernels too (on the read-only memory-mapped terrain and on the smoothed
    heights of whole metres): afterwards a search with --access compiles nothing (no new file in numba's cache)."""
    numba_dir = tmp_path / "numba"
    env = {**os.environ, **OFFLINE_ENV, "NUMBA_CACHE_DIR": str(numba_dir)}
    result = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {REPO!r}); import warmup; "
                                                   f"warmup.warm_up({str(tmp_path / 'data')!r})"],
                            capture_output=True, text=True, encoding="utf-8", timeout=900, env=env)
    assert result.returncode == 0 and "warm-up failed" not in result.stderr, result.stdout + result.stderr
    files = lambda pattern: {os.path.basename(p) for p in glob.glob(str(numba_dir / "**" / pattern),  # noqa: E731
                                                                  recursive=True)}
    kernels = {name.split("-")[0] for name in files("*.nbi")}
    assert {"access._walk", "access._stands_near"} <= kernels, kernels
    compiled = files("*.nbc")
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"), "--northing", "254608", "--easting", "553966",
         "--radius", "290", "--water", "off", "--fill-gaps", "off", "--ortho", "never", "--no-plot", "--yes",
         "--access", "--data-dir", str(tmp_path / "clip")],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert files("*.nbc") == compiled


PAGE_SCRIPT = r"""
const fs = require("fs");
const read = (path) => { const t = fs.readFileSync(path, "utf-8"); return JSON.parse(t.slice(t.indexOf(" = {") + 3).trim().replace(/;$/, "")); };
const off = read(process.argv[2]), on = read(process.argv[3]);
const lines = (d) => d.lines.map((r) => m.toLine(r, undefined, d.terrain, d.ends));
const columns = (d) => { const c = m.lineColumns(d.lines, d.terrain, d.ends); return d.lines.map((_, i) => m.lineAt(c, i)); };
const text = (ls) => JSON.stringify(ls);
console.log(JSON.stringify({n: on.lines.length, rows: text(lines(on)) === text(lines(off)),
                            cols: text(columns(on)) === text(columns(off)), same: text(columns(on)) === text(lines(on))}));
"""


@pytest.mark.skipif(shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                    reason="needs Node and `npm install` in viewer/")
def test_todays_page_reads_the_run_as_without_the_option(tmp_path, scene_runs):
    """Today's page (viewer/src/types.ts toLine and lineColumns/lineAt, what the result's page reads a run with)
    gives every line of a run made with --access the very values of the run made without it: the access values,
    named by the head's "ends", are values it does not read (the page that shows them is step 1d-P's)."""
    bundle = tmp_path / "types.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: ['src/types.ts'], bundle: true, "
                                  f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    for file in ("data.js", "lines.js"):
        script = tmp_path / "page-test.cjs"
        script.write_text(f"const m = require({json.dumps(str(bundle))});\n{PAGE_SCRIPT}", encoding="utf-8")
        result = subprocess.run(["node", str(script), str(scene_runs["off"] / file), str(scene_runs["on"] / file)],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        out = json.loads(result.stdout)
        assert out == {"n": out["n"], "rows": True, "cols": True, "same": True} and out["n"] > 50, (file, out)
        assert re.search(r'"ends":\["access1","access2"\]', (scene_runs["on"] / file).read_text(encoding="utf-8"))
