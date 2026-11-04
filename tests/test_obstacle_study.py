"""tools/obstacle_study.py on a synthetic canyon: the capture of a find_valid_lines call, the
rules' counts checked against the production kernel, the outside layers' classes, the shift of
CHMv2, the names of the WorldCover tiles, the report, and a cache link removed without its target.
The surface model's own pixels (fine_grid) come from GeoTIFFs of 0.5 m (the surface, two files)
and 1 m (the terrain) written from a fine model as the services make theirs: the terrain at each
pixel's centre, the surface the highest point of the pixel."""

import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import helpers as sh  # noqa: E402
import linesearch as ls  # noqa: E402
import obstacle_study as study  # noqa: E402
import obstacles  # noqa: E402

ROWS, COLS, FINE = 60, 100, 10
TREE_ROWS, TREE_COLS = slice(20, 26), slice(48, 52)
LEFT, TOP, CRS = 500000.0, 300000.0, "EPSG:2180"
MARGIN = 4  # metres the files reach beyond the grid (the terrain is interpolated bilinearly near its edge)


def write_tif(path, values, left, top, res):
    import rasterio as rio
    from rasterio.transform import from_origin
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1,
                  dtype="float32", crs=CRS, transform=from_origin(left, top, res, res), nodata=np.nan) as dst:
        dst.write(values.astype(np.float32), 1)
    return str(path)


def pixel_maxima(f, start, pixels, res, samples):
    """The highest of `samples` points of f (a function of x in metres) in each of `pixels` pixels of
    res metres from start."""
    x = start + (np.arange(pixels * samples) + 0.5) * res / samples
    return f(x).reshape(pixels, samples).max(axis=1)


def write_model(folder, ground, surface, rows, cols, offset=0.0, fine=20, tree=None):
    """The model as the files of a cache: the surface in pixels of 0.5 m whose edges lie offset metres
    after the grid's (two files, split at a column), the terrain in pixels of 1 m on the grid's.
    ground, surface: functions of x (metres from the grid's left edge); tree: (rows, cols, metres) of
    the grid's 1 m pixels added to the surface. Returns (nmt_files, nmpt_files)."""
    start = offset - MARGIN
    n = 2 * (cols + 2 * MARGIN)
    nmpt = np.tile(pixel_maxima(surface, start, n, 0.5, fine // 2), (2 * (rows + 2 * MARGIN), 1))
    if tree is not None:
        t_rows, t_cols, height = tree
        top_px = lambda r: 2 * (r + MARGIN)  # noqa: E731
        nmpt[top_px(t_rows.start):top_px(t_rows.stop),
             2 * (t_cols.start + MARGIN) - round(2 * offset):2 * (t_cols.stop + MARGIN) - round(2 * offset)] += height
    split = n // 2
    top = TOP + MARGIN
    nmpt_files = [write_tif(os.path.join(folder, "nmpt", "w.tif"), nmpt[:, :split], LEFT + start, top, 0.5),
                  write_tif(os.path.join(folder, "nmpt", "e.tif"), nmpt[:, split:], LEFT + start + split * 0.5,
                            top, 0.5)]
    nmt = np.tile(ground(np.arange(-MARGIN, cols + MARGIN) + 0.5), (rows + 2 * MARGIN, 1))
    return [write_tif(os.path.join(folder, "nmt", "t.tif"), nmt, LEFT - MARGIN, top, 1.0)], nmpt_files


def canyon_grids():
    """A canyon whose walls stand inside pixels 20 and 79 (terrain at the pixels' centres, the
    surface their highest point) with a tree of 45 m on its floor in rows 20-25."""
    x = (np.arange(COLS * FINE) + 0.5) / FINE
    ground = lambda x: np.where((x >= 20.35) & (x < 79.65), 50.0, 100.0)  # noqa: E731
    dtm = np.tile(ground(np.arange(COLS) + 0.5).astype(np.float32), (ROWS, 1))
    dsm = np.tile(ground(x).reshape(COLS, FINE).max(axis=1).astype(np.float32), (ROWS, 1))
    dsm[TREE_ROWS, TREE_COLS] += 45
    return dtm, dsm


def canyon_ground(x):
    return np.where((x >= 20.35) & (x < 79.65), 50.0, 100.0)


def capture_call(tmp_path, fine=False):
    """One find_valid_lines call captured as obstacle_study.capture captures it; fine: with the
    canyon's surface model in pixels of 0.5 m (and the tree) in a cache that grid.json names."""
    dtm, dsm = canyon_grids()
    anchors = sh.find_significant_slopes(dtm, 1.0, 45, np.ones(dtm.shape, dtype=bool))
    wrapper = study.Capture(str(tmp_path / "capture"))
    wrapper.grid = SimpleNamespace(crs=CRS, left=LEFT, top=TOP, res=1.0, height=ROWS, width=COLS), None
    if fine:
        nmt, nmpt = write_model(str(tmp_path / "cache"), canyon_ground, canyon_ground, ROWS, COLS, fine=FINE,
                                tree=(TREE_ROWS, TREE_COLS, 45.0))
        wrapper.meta = {"source": "test", "grid_origin": [0.0, 0.0], "nmt_files": nmt, "nmpt_files": nmpt}
    lines = wrapper(dtm, dsm, anchors, 1.0, 50, 70, "mark", threads=2)
    return str(tmp_path / "capture" / "call-0"), dtm, dsm, lines


def layers_of(dtm):
    """CHMv2 with the tree, WorldCover bare (60) but tree cover (10) under the tree."""
    def layers(call, grid):
        chm = np.zeros(dtm.shape, dtype=np.float32)
        chm[TREE_ROWS, TREE_COLS] = 44
        wc = np.full(dtm.shape, 60, dtype=np.float32)
        wc[TREE_ROWS, TREE_COLS] = 10
        return chm, wc
    return layers


def test_rules_on_a_canyon(tmp_path):
    call, dtm, dsm, lines = capture_call(tmp_path)
    assert len(lines) and (lines.columns["clearance_nmpt"] <= 0).all()  # the rim marks every line
    s1 = obstacles.obstacle_surface(dtm, dsm, 1.0)
    over_tree = np.array([sh.evaluate_line(a, b, dtm, 1.0, s1)[4] <= 0
                          for a, b in zip(lines.columns["a1"], lines.columns["a2"])])
    assert 0 < over_tree.sum() < len(lines)

    chips = {}
    result = study.analyse_call(call, layers_of(dtm), chips)
    assert result["checks"]["raw_equal"] and result["checks"]["a1_equal"]
    assert result["marked"] == result["lines"] == len(lines)
    assert result["classes"] == {"real": int(over_tree.sum()), "real_chm": int(over_tree.sum()),
                                 "rock_only": int((~over_tree).sum()), "other": 0,
                                 "real_objects": 1, "rock_objects": 2}  # the tree; the two rims
    a1 = result["rules"]["A1"]
    assert a1 == {"marked": int(over_tree.sum()), "lost": 0, "lost_objects": 0, "lost_chm": 0,
                  "removed_rock": int((~over_tree).sum()), "residual_rock": 0, "residual_objects": 0,
                  "kept_real": int(over_tree.sum())}
    assert result["rules"]["raw"]["marked"] == len(lines)
    assert result["rules"]["D3"]["marked"] == int(over_tree.sum())  # the rim is the first pixel
    assert result["rules"]["F-trees"]["marked"] == int(over_tree.sum())
    assert result["r_needed"]["rock_only"][0] == (~over_tree).sum()  # every rock line clear at r = 1
    assert result["r_needed"]["real"][10] == over_tree.sum()  # a tree stays at every r
    assert set(chips) == {"removed_rock", "kept_real"}

    folder = tmp_path  # the place's folder: <place>/capture/call-0
    picked = study.pictures(str(folder), chips, 2)
    assert {g: len(v) for g, v in picked.items()} == {"removed_rock": 2, "kept_real": 2}
    assert all(os.path.getsize(folder / "chips-A1" / e["png"]) > 1000 for v in picked.values() for e in v)


def test_variants_on_a_canyon(tmp_path):
    """The canyon's surface model of 0.5 m: its maxima are the working grid's surface (max marks
    what avg marks); the terrain plus the highest height above it (h) stands below the rim's
    limits at the walls (37.5 m above the floor, the terrain interpolated a quarter metre from the
    wall) and the tree's full 45 m: h marks only the lines over the tree, under every rule."""
    call, dtm, dsm, lines = capture_call(tmp_path, fine=True)
    s1 = obstacles.obstacle_surface(dtm, dsm, 1.0)
    over_tree = np.array([sh.evaluate_line(a, b, dtm, 1.0, s1)[4] <= 0
                          for a, b in zip(lines.columns["a1"], lines.columns["a2"])])
    result = study.analyse_call(call, layers_of(dtm))
    assert set(result["fine"].pop("seconds")) == {"s-max", "h-max", "s-med", "h-med"}
    assert result["fine"] == {"res": 0.5, "k": 2, "files": {"nmt": 1, "nmpt": 2}, "offset": [0.0, 0.0],
                              "left": LEFT, "top": TOP}
    np.testing.assert_array_equal(np.load(os.path.join(call, "s-max.npy")), dsm)
    h_max = np.load(os.path.join(call, "h-max.npy"))
    assert (h_max[:, [20, 79]] == 37.5).all() and (h_max[TREE_ROWS, TREE_COLS] == 45).all()
    assert result["checks"]["variants"] == {name: {"raw_equal": True, "a2_equal": True} for name in study.VARIANTS[1:]}
    assert result["checks"]["a1_equal"] and result["checks"]["a2_equal"]

    variants = result["variants"]
    assert list(variants) == list(study.VARIANTS)
    assert {k: v for k, v in variants["max"].items() if k != "over_avg"} == variants["avg"]
    assert variants["avg"]["rules"] == {name: result["rules"][name] for name in study.VARIANT_RULES}
    real, rock = int(over_tree.sum()), int((~over_tree).sum())
    # h, med and hmed: the rims' fine pixels hold the wall's top in one of two (med: the lower middle of the
    # 2 x 2, the floor), so only the tree (45 m: more than A2+H40 allows) stays marked
    for variant in ("h", "med", "hmed"):
        assert variants[variant]["marked"] == real and variants[variant]["classes"] == {
            "real": real, "real_chm": real, "rock_only": 0}, variant
        for name in study.VARIANT_RULES:
            kept = 0 if name == "A2+H40" else real
            assert variants[variant]["rules"][name] == {"marked": kept, "lost": real - kept, "lost_objects": 1 if kept == 0 else 0,
                                                        "lost_chm": real - kept, "removed_rock": 0, "residual_rock": 0,
                                                        "residual_objects": 0, "kept_real": kept}, (variant, name)
    for variant in study.VARIANTS[1:]:  # A2 marks the tree's lines on every surface
        assert variants[variant]["over_avg"] == {"added": 0, "dropped": 0}, variant
    np.testing.assert_array_equal(np.load(os.path.join(call, "s-med.npy"))[:, [20, 79]], 50.0)
    assert result["rules"]["A2+H40"]["marked"] == 0 and result["rules"]["A2+H40"]["lost"] == real
    assert result["rules"]["A2+H60"]["marked"] == result["rules"]["A2+H80"]["marked"] == real
    assert variants["avg"]["rules"]["raw"]["removed_rock"] == 0 and variants["avg"]["rules"]["A2"]["removed_rock"] == rock
    assert variants["avg"]["rules"]["A2+T"] == variants["avg"]["rules"]["A2"]  # the tree is A2's already

    # Without the files the variants are avg alone, its counts the same
    plain = study.analyse_call(capture_call(tmp_path / "plain")[0], layers_of(dtm))
    assert plain["fine"] == {"res": None, "k": None, "files": {"nmt": 0, "nmpt": 0}}
    assert plain["variants"] == {"avg": variants["avg"]} and plain["rules"] == result["rules"]


def face_ground(x):
    """Flat ground at 50 m, a face of 75 degrees from x = 30 m to 40 m, a plateau above it."""
    return 50.0 + np.tan(np.radians(75)) * np.clip(x - 30.0, 0.0, 10.0)


def face_surface(x):
    """The ground and a tree of 20 m on the flat ground from x = 10 m to 13 m."""
    return face_ground(x) + np.where((x >= 10) & (x < 13), 20.0, 0.0)


@pytest.mark.parametrize("offset", [0.0, 0.25])
def test_fine_grid(tmp_path, offset):
    """s-max, the fine surface warped with GDAL's max: with the files' edges on the grid's the
    highest of the k x k fine pixels inside a grid pixel, exactly; with them a quarter metre off (as
    geoportal's sheets of 0.5 m under its grid of 1 m) between the highest of the one fine pixel
    wholly inside each way and that of the k + 1 overlapping it (GDAL 3.12 takes the latter: the
    half-overlapping pixels count); h-max of the tree is its height, of the face about half a fine
    pixel times the tangent of its slope."""
    rows, cols = 8, 60
    nmt, nmpt = write_model(str(tmp_path / "cache"), face_ground, face_surface, rows, cols, offset)
    call = tmp_path / "call-0"
    call.mkdir()
    with open(call / "grid.json", "w") as f:
        json.dump({"crs": CRS, "left": LEFT, "top": TOP, "res": 1.0, "height": rows, "width": cols, "core": None,
                   "nmt_files": nmt, "nmpt_files": nmpt}, f)
    fine = study.fine_grid(str(call))
    extra = 1 if offset else 0
    assert set(fine) == {"res", "k", "files", "offset", "left", "top", "seconds"}
    assert {k: fine[k] for k in ("res", "k", "files", "offset", "left", "top")} == {
        "res": 0.5, "k": 2, "files": {"nmt": 1, "nmpt": 2}, "offset": [offset, 0.0],
        "left": LEFT + (offset - 0.5 if offset else 0.0), "top": TOP}
    assert np.load(call / "fine-nmpt.npy").shape == (2 * rows, 2 * cols + extra)
    assert np.load(call / "fine-nmt.npy").shape == (2 * rows, 2 * cols + extra)

    fine_row = np.float32(pixel_maxima(face_surface, offset - MARGIN, 2 * (cols + 2 * MARGIN), 0.5, 10))
    first = 2 * MARGIN - extra  # the first fine pixel overlapping pixel 0
    overlapping = np.array([fine_row[first + 2 * j:first + 2 * j + 2 + extra].max() for j in range(cols)])
    s_max = np.load(call / "s-max.npy")
    assert (s_max == s_max[0]).all()  # the rows are all alike
    if not offset:  # the highest point of each pixel of 1 m
        np.testing.assert_array_equal(s_max[0], overlapping)
        np.testing.assert_array_equal(s_max[0], pixel_maxima(face_surface, 0.0, cols, 1.0, 20).astype(np.float32))
    else:
        inside = fine_row[first + 1:first + 1 + 2 * cols:2]  # the one fine pixel wholly inside each way
        assert (inside <= s_max[0]).all() and (s_max[0] <= overlapping).all()
        np.testing.assert_array_equal(s_max[0], overlapping)  # what GDAL 3.12 does
    # s-med: GDAL's med over the same fine pixels, of an even number the lower middle one (the rows of the
    # model alike: each fine column twice)
    columns = np.array([np.sort(fine_row[first + 2 * j:first + 2 * j + 2 + extra]) for j in range(cols)])
    s_med = np.load(call / "s-med.npy")
    np.testing.assert_array_equal(s_med[0], columns[:, 0] if not offset else columns[:, 1])
    assert np.isfinite(np.load(call / "h-med.npy")).all()
    h_max = np.load(call / "h-max.npy")
    np.testing.assert_allclose(h_max[:, 10:13], 20.0, atol=1e-4)
    face = h_max[:, 32:38]
    assert (face > 0.4 * np.tan(np.radians(75)) / 2).all() and (face < 0.25 * np.tan(np.radians(75)) + 1e-3).all()
    assert study.fine_grid(str(call)) == fine  # read from fine.json the second time
    # A warp missing (a variant added after the fine grids were built): made from the fine grids kept
    built = os.path.getmtime(call / "fine-nmpt.npy")
    os.remove(call / "s-med.npy")
    again = study.fine_grid(str(call))
    np.testing.assert_array_equal(np.load(call / "s-med.npy"), s_med)
    assert os.path.getmtime(call / "fine-nmpt.npy") == built and set(again["seconds"]) == set(fine["seconds"])


def test_fine_grid_none(tmp_path):
    """No surface files, or none finer than three quarters of the grid's pixels: nothing to measure."""
    nmt, nmpt = write_model(str(tmp_path / "cache"), face_ground, face_surface, 4, 10)
    call = tmp_path / "call-0"
    call.mkdir()
    for files, grid_res in (([], 1.0), (nmpt, 0.6)):
        with open(call / "grid.json", "w") as f:
            json.dump({"crs": CRS, "left": LEFT, "top": TOP, "res": grid_res, "height": 4, "width": 10, "core": None,
                       "nmt_files": nmt, "nmpt_files": files}, f)
        if os.path.exists(call / "fine.json"):
            os.remove(call / "fine.json")
        assert study.fine_grid(str(call)) is None
        with open(call / "fine.json") as f:
            assert json.load(f)["res"] is None
        assert not os.path.exists(call / "s-max.npy")


@pytest.mark.parametrize("offset", [0.0, 0.25])
def test_warp_max_in_blocks(offset):
    """Blocks of rows give what one warp gives; NaN only where no fine pixel has data."""
    from grid import Grid
    rng = np.random.default_rng(5)
    extra = 1 if offset else 0
    fine = rng.normal(100, 10, (2 * 13 + extra, 2 * 11 + extra)).astype(np.float32)
    fine[:4, :4] = np.nan  # the fine pixels of grid pixels 0-1 of rows 0-1 (half of pixel 1 with the offset)
    minus = rng.normal(50, 5, fine.shape).astype(np.float32)
    fine_on = Grid(left=LEFT + (offset - 0.5 if offset else 0.0), top=TOP, res=0.5, height=fine.shape[0],
                   width=fine.shape[1], crs=CRS)
    grid = Grid(left=LEFT, top=TOP, res=1.0, height=13, width=11, crs=CRS)
    for kind in ("max", "med"):
        whole = study.warp_max(fine, fine_on, grid, np.empty((13, 11), np.float32), minus, block_rows=100,
                               resampling=kind)
        for rows in (1, 2, 5):
            np.testing.assert_array_equal(study.warp_max(fine, fine_on, grid, np.empty((13, 11), np.float32), minus,
                                                         block_rows=rows, resampling=kind), whole)
    whole = study.warp_max(fine, fine_on, grid, np.empty((13, 11), np.float32), minus, block_rows=100)
    for rows in (1, 2, 5):
        np.testing.assert_array_equal(study.warp_max(fine, fine_on, grid, np.empty((13, 11), np.float32), minus,
                                                     block_rows=rows), whole)
    none = np.zeros(whole.shape, dtype=bool)
    none[:2, :2 - extra] = True  # the offset along x: there column 1 overlaps a fine pixel with data
    np.testing.assert_array_equal(np.isnan(whole), none)


def test_without_outside_layers(tmp_path):
    call, dtm, dsm, lines = capture_call(tmp_path)
    result = study.analyse_call(call)
    assert result["classes"] == {"real": 0, "real_chm": 0, "rock_only": 0, "other": len(lines),
                                 "real_objects": 0, "rock_objects": 0}
    assert "F" not in result["rules"] and "chm_shift" not in result


def test_chm_shift():
    rng = np.random.default_rng(3)
    from scipy import ndimage
    canopy = np.clip(ndimage.gaussian_filter(rng.normal(0, 1, (240, 240)), 4) * 60, 0, 25).astype(np.float32)
    z = np.full(canopy.shape, 300.0, dtype=np.float32)
    chm = np.full(canopy.shape, np.nan, dtype=np.float32)
    chm[:-3, 2:] = canopy[3:, :-2]  # CHMv2 2 px too far east and 3 px too far north
    found = study.chm_shift(z, z + canopy, chm, 1.0, np.zeros(canopy.shape))
    assert (found["east_m"], found["north_m"]) == (-2.0, -3.0)
    assert found["r_best"] > 0.99 > found["r_zero"]


def test_worldcover_tiles():
    grid = {"crs": "EPSG:2193", "left": 1500000.0, "top": 5210000.0, "res": 1.0, "height": 1000, "width": 1000}
    assert [u.rsplit("/", 1)[1] for u in study.worldcover_urls(grid)] == ["ESA_WorldCover_10m_2021_v200_S45E171_Map.tif"]
    grid = {"crs": "EPSG:4326", "left": -4.3, "top": 53.1, "res": 0.001, "height": 100, "width": 100}
    assert [u.rsplit("/", 1)[1] for u in study.worldcover_urls(grid)] == ["ESA_WorldCover_10m_2021_v200_N51W006_Map.tif"]


def test_in_core():
    grid = {"left": 0.0, "top": 100.0, "res": 1.0, "core": [0.0, 0.0, 50.0, 100.0]}
    a1 = np.array([[10, 10], [10, 60], [10, 70]])
    a2 = np.array([[10, 60], [10, 49], [10, 80]])  # the first anchor is the one with the smaller x
    assert study.in_core(a1, a2, grid).tolist() == [True, True, False]


def test_report(tmp_path):
    rules = {name: {"marked": 5, "lost": 1, "lost_objects": 1, "lost_chm": 1, "removed_rock": 3, "residual_rock": 0,
                    "residual_objects": 0, "kept_real": 4}
             for name in study.rule_names()}
    for place in ("R1", "R2"):
        os.makedirs(tmp_path / place)
        with open(tmp_path / place / "study.json", "w") as f:
            json.dump({"place": place, "source": "test", "res": 1.0, "lines": 10, "marked": 9, "rules": rules,
                       "classes": {"real": 4, "real_chm": 5, "rock_only": 3, "other": 2},
                       "checks": [{"raw_equal": True}],
                       "chm_shift": [None],
                       **({"fine": {"res": 0.5, "k": 2, "offset": [0.25, 0.25]},
                           "variants": {"avg": {"marked": 9, "classes": {"real": 4}, "rules": rules},
                                        "h": {"marked": 6, "classes": {"real": 4},
                                              "rules": {**rules, "A2+T": {**rules["A2"], "marked": 4}}}}}
                          if place == "R2" else {})}, f)
    text = study.report(str(tmp_path))
    assert "| R1 | test | 1.0 | 10 | 4 | 5 |" in text and "| A1 | 10 (56 %) | 2 (25 %), 2 | 2 (20 %) | 6 (100 %) | 0, 0 | 8 |" in text
    assert "Places where a check failed: none" in text
    assert "## Judges" not in text and "Near an anchor" not in text  # without the judges: as before them
    assert text.index("| R1 | test |") < text.index("## Surface variants") < text.index("## Over all places")
    assert "| R2 | 0.5 | avg | 9 | 4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | - |" in text  # A2+T not in the rules given
    assert "| R2 | 0.5 | h | 6 | 4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 |" in text and "| R1 | None |" not in text
    with open(tmp_path / "R2" / "study.json") as f:
        place = study.place_markdown(json.load(f))
    assert "| h | A2+T | 4 (67 %) | 1, 1 | 1 | 3 | 0, 0 | 4 |" in place


@pytest.mark.skipif(not hasattr(os.path, "isjunction"), reason="Python before 3.12")
def test_unlink_keeps_the_target(tmp_path):
    import regression
    target = tmp_path / "real-cache"
    target.mkdir()
    (target / "tile.tif").write_bytes(b"data")
    regression.link(str(target), str(tmp_path / "cache"))
    study._unlink(str(tmp_path / "cache"))
    assert not os.path.exists(tmp_path / "cache") and (target / "tile.tif").read_bytes() == b"data"


def test_kernel_sees_the_obstacle_surface():
    """evaluate_lines with the obstacle surface marks only the lines over the tree."""
    dtm, dsm = canyon_grids()
    anchors = np.array([[22, 19], [22, 80], [40, 19], [40, 80]])
    table = ls.evaluate_lines(np.array([[0, 1], [2, 3]]), anchors, dtm, 1.0, obstacles.obstacle_surface(dtm, dsm, 1.0),
                              None, "mark")
    assert (table.columns["clearance_nmpt"] <= 0).tolist() == [True, False]


# ---------------------------------------------------------------------------------------------
# the judges (OSM's land cover, the orthophoto) on the canyon: their files written by hand

RIMS, ROCK_REF = [20, 79], [19, 80]  # the tall pixels of the walls (surface 50 m above), the rock reference


def write_judges(call, shape, rim_cover=None, rim_lum=200.0, ortho=True, rim_gli=0.0):
    """landcover.npy (forest under the tree, rim_cover at the rims) and, with ortho, the orthophoto:
    the tree green (GLI 0.3) and darker (100), everything else grey (GLI 0; the rims rim_gli), the
    walls bright (200, the rims rim_lum), the floor between (150)."""
    import study_landcover as sl
    cover = np.zeros(shape, np.uint8)
    cover[TREE_ROWS, TREE_COLS] = sl.FOREST
    if rim_cover is not None:
        cover[:, RIMS] = rim_cover
    np.save(os.path.join(call, "landcover.npy"), cover)
    for name in ("ortho-gli.npy", "ortho-lum.npy", "ortho.json"):
        if os.path.exists(os.path.join(call, name)):
            os.remove(os.path.join(call, name))
    if not ortho:
        return
    gli = np.zeros(shape, np.float32)
    gli[TREE_ROWS, TREE_COLS] = 0.3
    gli[:, RIMS] = rim_gli
    lum = np.full(shape, 150.0, np.float32)
    lum[:, ROCK_REF] = 200
    lum[:, RIMS] = rim_lum
    lum[TREE_ROWS, TREE_COLS] = 100
    np.save(os.path.join(call, "ortho-gli.npy"), gli)
    np.save(os.path.join(call, "ortho-lum.npy"), lum)
    with open(os.path.join(call, "ortho.json"), "w") as f:
        json.dump({"zoom": 19, "tiles": 3, "tau": None, "dark": None, "forest_median": None, "rock_median": None,
                   "overlap": None}, f)


def no_writing(call, grid, a1, a2):
    """The judges as judge_layers calls them, their files already in the call's folder."""


def without_judges(result):
    """A result less what the judges add."""
    out = {k: v for k, v in result.items() if k not in ("judges", "agreement", "near_anchor")}
    out["variants"] = {name: {k: v for k, v in variant.items() if k != "verdicts"}
                       for name, variant in result["variants"].items()}
    return out


@pytest.fixture
def judged_canyon(tmp_path, monkeypatch):
    """The canyon's call and its lines over the tree; the tree's 24 pixels are enough of a forest."""
    import study_ortho
    monkeypatch.setattr(study_ortho, "MIN_PIXELS", 20)
    call, dtm, dsm, lines = capture_call(tmp_path)
    s1 = obstacles.obstacle_surface(dtm, dsm, 1.0)
    over_tree = np.array([sh.evaluate_line(a, b, dtm, 1.0, s1)[4] <= 0
                          for a, b in zip(lines.columns["a1"], lines.columns["a2"])])
    return call, dtm, int(over_tree.sum()), int((~over_tree).sum())


def tally(tree=0, rock=0, unknown=0, none=0):
    return {"tree": tree, "rock": rock, "unknown": unknown, "none": none}


def test_verdicts_on_a_canyon(judged_canyon):
    """The tree green over OSM forest: tree; the rims bright and not green: rock; the rims dark:
    OSM's land cover decides (rock, unknown, tree); without the orthophoto OSM alone; the thresholds
    set on the references go into ortho.json; the counts of before stay as they were."""
    import study_landcover as sl
    call, dtm, real, rock = judged_canyon
    plain = study.analyse_call(call, layers_of(dtm))
    write_judges(call, dtm.shape)
    result = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    assert without_judges(result) == plain

    with open(os.path.join(call, "ortho.json")) as f:
        ortho = json.load(f)
    assert result["judges"] == {"landcover": True, "ortho": ortho}
    assert ortho["tau"] == pytest.approx(0.15) and ortho["bright"] == 150 and ortho["dark"] == 100
    assert ortho["overlap"] == 0 and ortho["bright_overlap"] == 0
    agreement = result["agreement"]
    assert {k: agreement[k] for k in ("forest", "forest_ortho", "forest_green", "rock", "rock_ortho", "rock_bright",
                                      "forest_chm", "forest_chm_tree", "rock_chm", "rock_chm_low")} == {
        "forest": 24, "forest_ortho": 24, "forest_green": 24, "rock": 120, "rock_ortho": 120, "rock_bright": 120,
        "forest_chm": 24, "forest_chm_tree": 24, "rock_chm": 120, "rock_chm_low": 120}
    assert agreement["osm_forest"] == 24 and agreement["osm_rock"] == 0 and agreement["pixels"] == dtm.size

    verdicts = result["variants"]["avg"]["verdicts"]
    assert verdicts["lines"] == tally(tree=real, rock=rock)
    assert set(verdicts["rules"]) == set(study.VARIANT_RULES)
    assert verdicts["rules"]["raw"] == {"unmarked": tally(), "kept": tally(tree=real, rock=rock)}
    for name in ("A1", "A2", "A3", "A2+T"):  # the rims' lines lose their marks, the tree's keep theirs
        assert verdicts["rules"][name] == {"unmarked": tally(rock=rock), "kept": tally(tree=real)}, name
    # The rims stand at the first step from an anchor, the tree in the middle
    assert result["near_anchor"]["lines"] == tally(rock=rock)
    assert result["near_anchor"]["rules"]["A2"]["unmarked"] == tally(rock=rock)

    for cover, expected in ((sl.ROCK, "rock"), (sl.NONE, "unknown"), (sl.FOREST, "tree")):
        write_judges(call, dtm.shape, rim_cover=cover, rim_lum=10)  # in the walls' shadow
        dark = study.analyse_call(call, layers_of(dtm), judges=no_writing)
        lines = dark["variants"]["avg"]["verdicts"]["lines"]
        assert lines == {**tally(tree=real), expected: lines[expected]} and sum(lines.values()) == real + rock
        assert lines[expected] == (rock + real if expected == "tree" else rock), cover

    write_judges(call, dtm.shape, rim_cover=sl.ROCK, ortho=False)  # OSM alone
    alone = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    assert alone["judges"] == {"landcover": True, "ortho": None}
    assert alone["variants"]["avg"]["verdicts"]["lines"] == tally(tree=real, rock=rock)
    os.remove(os.path.join(call, "landcover.npy"))
    np.save(os.path.join(call, "landcover.npy"), np.zeros(0, np.uint8))  # OSM could not be had either
    neither = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    assert neither["variants"]["avg"]["verdicts"]["lines"] == tally(unknown=real + rock)
    # A judge asked for but never written (a capture from before grid.json named its source)
    os.remove(os.path.join(call, "landcover.npy"))
    assert study.analyse_call(call, layers_of(dtm), judges=no_writing) == plain


def test_green_on_a_rim(judged_canyon):
    """A green rim pixel on the wall's face (the terrain's slope there about 87 degrees): vegetation of
    unknown height without a tree of CHMv2 at the pixel (OSM's land cover decides, none here: unknown,
    also with CHMv2's 5 m in the neighbouring pixel), a tree where CHMv2 sees one of 5 m at the pixel;
    the tree on the canyon's floor stays a tree."""
    call, dtm, real, rock = judged_canyon
    assert (obstacles.slope_degrees(dtm, 1.0)[:, RIMS] >= study.TREE_SLOPE).all()
    write_judges(call, dtm.shape, rim_gli=0.3)
    result = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    assert result["variants"]["avg"]["verdicts"]["lines"] == tally(tree=real, unknown=rock)

    def layers(columns):
        def read(call_, grid):
            chm, wc = layers_of(dtm)(call_, grid)
            chm[:, columns] = 5
            return chm, wc
        return read
    result = study.analyse_call(call, layers(RIMS), judges=no_writing)
    assert result["variants"]["avg"]["verdicts"]["lines"] == tally(tree=real + rock)
    result = study.analyse_call(call, layers([21, 78]), judges=no_writing)  # beside the rims (on the floor)
    assert not result.get("chm_shift", {}).get("applied")  # CHMv2 is read where it is
    assert result["variants"]["avg"]["verdicts"]["lines"] == tally(tree=real, unknown=rock)

    write_judges(call, dtm.shape, rim_cover=2, rim_gli=0.3)  # OSM: rock (study_landcover.ROCK)
    result = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    assert result["variants"]["avg"]["verdicts"]["lines"] == tally(tree=real, rock=rock)


def test_pixel_classes_and_judge_failure():
    """Green on terrain under TREE_SLOPE or on a tree of CHMv2: PX_TREE, else PX_STEEP; bright and dark
    as before; a place's judge fails on overlapping splits or on too few forest pixels in the orthophoto."""
    gli = np.array([0.3, 0.3, 0.3, 0.0, 0.0, 0.0, np.nan], np.float32)
    lum = np.array([100, 100, 100, 200, 10, 80, np.nan], np.float32)
    slope = np.array([10, 80, 80, 80, 80, 80, 80], np.float32)
    chm3 = np.array([-1, 0, 5, 0, 0, 0, 0], np.float32)
    ortho = {"tau": 0.15, "bright": 150, "dark": 50}
    assert study.pixel_classes(gli, lum, ortho, slope, chm3).tolist() == [
        study.PX_TREE, study.PX_STEEP, study.PX_TREE, study.PX_ROCK, study.PX_DARK, study.PX_UNKNOWN, study.PX_UNKNOWN]
    assert study.pixel_classes(gli, lum, ortho)[1] == study.PX_TREE  # without the slope: green alone

    def place(forest_ortho, overlaps=(0.1, 0.1), tiles=10, tau=0.05):
        return {"judges": [{"landcover": True, "ortho": {"tiles": tiles, "tau": tau, "overlap": overlaps[0],
                                                          "bright_overlap": overlaps[1]}}],
                "agreement": {"forest_ortho": forest_ortho}}
    assert study.judge_failure(place(study.REFERENCE_MIN)) is None
    assert study.judge_failure(place(study.REFERENCE_MIN - 1)) == "few forest px"
    assert study.judge_failure(place(10 ** 6, (0.5, 0.45))) == "overlap"
    assert study.judge_failure(place(358, (0.47, 0.56))) == "overlap, few forest px"  # Zamarla Turnia
    assert not study.judge_works(place(358)) and study.judge_group(place(358)) == "failed"
    # No split of the orthophoto: no tiles (no service), or tau null (too few references): OSM alone
    for osm_only in (place(0, tiles=0), place(10 ** 6, tau=None), place(0, (None, None), tau=None),
                     {"judges": [{"landcover": True, "ortho": None}], "agreement": {}}):
        assert study.judge_failure(osm_only) == study.OSM_ONLY and study.judge_group(osm_only) == "OSM"
        assert not study.judge_works(osm_only)
    assert study.judge_group(place(study.REFERENCE_MIN)) == "orthophoto"


def test_verdicts_of_the_variants(tmp_path, monkeypatch):
    """h marks only the lines over the tree, all judged tree; max what avg marks, as avg judges them."""
    import study_ortho
    monkeypatch.setattr(study_ortho, "MIN_PIXELS", 20)
    call, dtm, dsm, lines = capture_call(tmp_path, fine=True)
    write_judges(call, dtm.shape)
    result = study.analyse_call(call, layers_of(dtm), judges=no_writing)
    v = result["variants"]
    real = v["h"]["marked"]
    assert v["max"]["verdicts"] == v["avg"]["verdicts"]
    assert v["h"]["verdicts"]["lines"] == tally(tree=real)
    assert v["h"]["verdicts"]["rules"]["A2"] == {"unmarked": tally(), "kept": tally(tree=real)}


def test_judge_layers_of_an_old_capture(tmp_path):
    """A grid.json without its source (a capture from before the judges): nothing written, nothing judged."""
    call = tmp_path / "call-0"
    call.mkdir()
    study.judge_layers(str(tmp_path / "cache"))(str(call), {"crs": CRS}, np.zeros((0, 2)), np.zeros((0, 2)))
    assert os.listdir(call) == [] and study.load_judges(str(call)) is None


def test_chips_and_contact_sheets(judged_canyon, tmp_path):
    """The verdict's groups of A2 and a contact sheet of each, two pictures a row, five panels each."""
    from PIL import Image
    call, dtm, real, rock = judged_canyon
    write_judges(call, dtm.shape)
    chips = {}
    study.analyse_call(call, layers_of(dtm), chips, "A2", judges=no_writing)
    assert {g: len(v) for g, v in chips.items()} == {"unmarked-rock": rock, "kept-tree": real}
    assert {e[2]["verdict"] for e in chips["unmarked-rock"]} == {"rock"}
    assert {(e[2]["landcover"], e[2]["ortho"]) for e in chips["kept-tree"]} == {("forest", "green")}
    assert {e[2]["ortho"] for e in chips["unmarked-rock"]} == {"bright"}
    picked = study.pictures(str(tmp_path), chips, 3, "A2")
    assert {g: len(v) for g, v in picked.items()} == {"unmarked-rock": 3, "kept-tree": 3}
    chip = Image.open(tmp_path / "chips-A2" / picked["kept-tree"][0]["png"])
    for group in picked:
        with Image.open(tmp_path / "sheets" / f"A2-{group}.png") as sheet:
            assert sheet.size == (2 * chip.width, 2 * chip.height)  # three pictures: two rows of two
    assert chip.width > 1200  # five panels


def test_ortho_patch(tmp_path):
    """The cached tiles composed on the panel's pixels: a tile's colour where it is cached, grey where
    not, None without any."""
    from PIL import Image
    import orthophoto
    lat, lon = 50.1559508, 19.7562722
    z = 19
    x, y = orthophoto._to_mercator.transform(lon, lat)
    size = orthophoto._tile_size(z)
    tx, ty = int((x + orthophoto._EARTH) // size), int((orthophoto._EARTH - y) // size)
    left, _, _, top = orthophoto.mercator_box(z, tx, ty)
    grid = {"crs": "EPSG:3857", "left": left, "top": top, "res": size / 16, "height": 16, "width": 32}
    folder = str(tmp_path / "wm256")
    assert study.ortho_patch(grid, (0, 16), (0, 32), folder, z) is None
    path = orthophoto.tile_path(folder, z, tx, ty)
    os.makedirs(os.path.dirname(path))
    Image.new("RGB", (256, 256), (20, 200, 30)).save(path, "JPEG", quality=95)
    patch = study.ortho_patch(grid, (0, 16), (0, 32), folder, z, per_pixel=2)
    assert patch.shape == (32, 64, 3)
    assert np.abs(patch[:, :32].astype(int) - (20, 200, 30)).max() < 8  # the tile
    assert (patch[:, 32:] == 128).all()  # the tile east of it: not cached


def _times(counts, k):
    """Counts (nested dicts of ints) times k."""
    return {key: _times(v, k) if isinstance(v, dict) else v * k for key, v in counts.items()}


def test_report_with_judges(tmp_path):
    """The judges' sections: their agreement per place (a place whose two splits both overlap more
    than WORKS_OVERLAP marked NO), the verdicts per place, their sums over the places where the judge
    works, the lines near an anchor; and in a place's study.md the judges' line, the verdict columns
    and the near-anchor table."""
    rules = {name: {"marked": 5, "lost": 1, "lost_objects": 1, "lost_chm": 1, "removed_rock": 3, "residual_rock": 0,
                    "residual_objects": 0, "kept_real": 4}
             for name in study.rule_names() + ["A2+T"]}
    verdicts = {"lines": tally(tree=4, rock=3, unknown=1, none=1),
                "rules": {name: {"unmarked": tally(tree=1, rock=2, none=1), "kept": tally(tree=3, rock=1, unknown=1)}
                          for name in study.VARIANT_RULES}}
    near = {"lines": tally(tree=1, rock=2), "rules": {name: {"unmarked": tally(rock=2), "kept": tally(tree=1)}
                                                      for name in study.VARIANT_RULES}}
    agreement = {"forest": 1000, "rock": 50, "forest_ortho": 800, "forest_green": 600, "rock_ortho": 40, "rock_bright": 30,
                 "forest_chm": 100, "forest_chm_tree": 90, "rock_chm": 50, "rock_chm_low": 45, "pixels": 1000,
                 "osm_forest": 200, "osm_rock": 100}
    for place, overlaps in (("R1", (0.1, 0.2)), ("R2", (0.5, 0.45)), ("R3", None)):  # R3: no split, OSM alone
        os.makedirs(tmp_path / place)
        with open(tmp_path / place / "study.json", "w") as f:
            json.dump({"place": place, "source": "test", "res": 1.0, "lines": 10, "marked": 9, "rules": rules,
                       "classes": {"real": 4, "real_chm": 5, "rock_only": 3, "other": 2},
                       "checks": [{"raw_equal": True}], "chm_shift": [None],
                       "judges": [{"landcover": True, "ortho": None if overlaps is None else {
                           "zoom": 19, "tiles": 12, "tau": 0.05, "dark": 40.0, "overlap": overlaps[0], "bright": 120.0,
                           "bright_overlap": overlaps[1]}}],
                       "agreement": agreement, "near_anchor": near if overlaps else _times(near, 10),
                       "variants": {"avg": {"marked": 9, "classes": {"real": 4}, "rules": rules,
                                            "verdicts": verdicts if overlaps else _times(verdicts, 10)}}}, f)
    text = study.report(str(tmp_path))
    orthophoto, osm = (f"places {study.JUDGE_GROUPS[g]}" for g in ("orthophoto", "OSM"))
    assert text.index("## Over all places") < text.index("## Judges") < text.index("## Verdicts per place") \
        < text.index(f"## Verdicts over all {orthophoto} (R1)") < text.index("## Near an anchor") \
        < text.index(f"## Verdicts over all {osm} (R3)") \
        < text.index("## Places where the judge failed (listed above, not summed): R2") < text.index("## CHMv2 against")
    assert "| R3 | OSM | OSM only |" in text and "| R3 | OSM | avg | A2 | 40/30/10/10 | 10/20/0/10 | 30/10/10/0 |" in text
    assert "| R1 | yes | - | 20 %, 10 % | 12 | 0.050 (0.10) | 120 (0.20) | 40 | 75 % of 800 | 75 % of 40 | 90 % of 100 | " \
           "90 % of 50 |" in text
    assert "| R2 | NO | overlap |" in text
    assert "| R2 | NO | avg | A2 | 4/3/1/1 | 1/2/0/1 | 3/1/1/0 |" in text
    assert text.count("\n| avg | A2 | 4/3/1/1 | 1/2/0/1 | 3/1/1/0 |") == 1  # R1's alone: R2 is not summed
    assert "| avg | A2 | 40/30/10/10 | 10/20/0/10 | 30/10/10/0 |" in text  # R3's, apart
    assert f"{orthophoto}: 1/2/0/0 lines tree/rock/unknown/none" in text and "| A2 | 0 | 2 | 0 | 0 |" in text
    assert f"{osm}: 10/20/0/0 lines tree/rock/unknown/none" in text and "| A2 | 0 | 20 | 0 | 0 |" in text
    with open(tmp_path / "R3" / "study.json") as f:
        assert "verdicts come from OSM's land cover alone" in study.place_markdown(json.load(f))

    assert "## What A2+H<m> un-marks beyond A2 (avg)" in text and "| R1 | yes | 5 | 0 | 0/0/0/0 | 0 |" in text
    assert "## CHMv2 against the surface model" not in text and "## Lines each variant adds over avg" not in text

    with open(tmp_path / "R2" / "study.json") as f:
        place = study.place_markdown(json.load(f))
    assert "Judges: OSM land cover forest on 20 %, rock on 10 % of the grid; the orthophoto zoom 19, 12 tiles: tau " \
           "0.050 (overlap 0.50), bright 120 (overlap 0.45), dark 40." in place
    assert "WARNING: the orthophoto's two splits both overlap more than 0.4" in place
    assert "Surface variants: avg alone" in place
    assert "| avg | A2 | 5 (56 %) | 1, 1 | 1 | 3 | 0, 0 | 4 | 1/2/0/1 | 3/1/1/0 |" in place
    assert "Near an anchor: 3 lines" in place and "| A2+T | 0 | 2 | 0 | 0 |" in place
    assert place.index("Judges:") < place.index("Surface variants") < place.index("Near an anchor")


def test_height_caps_on_a_wall():
    """A2+H<m> on a wall of 100 m whose lip the surface model draws 4 pixels out over its foot (an
    overhang): A2 keeps the lip (no terrain within two pixels reaches it), every cap un-marks it; a tree
    of 30 m on the floor stays under every cap, one of 70 m only under A2+H80."""
    z = np.zeros((20, 60), np.float32)
    z[:, 40:] = 100
    s = z.copy()
    s[:, 36:40] = 100  # the lip
    s[5, 10], s[5, 20] = 30, 70
    pix = {"row": np.array([10, 10, 5, 5]), "col": np.array([36, 37, 10, 20]), "step": np.ones(4, np.int64),
           "steps": np.full(4, 9, np.int64)}
    names = ["A2"] + [f"A2+H{h}" for h in study.HEIGHT_CAPS]
    flags = study.rule_flags(z, s, 1.0, pix, None, obstacles.slope_degrees(z, 1.0), None, names)
    assert flags["A2"].tolist() == [True, True, True, True]
    assert flags["A2+H40"].tolist() == flags["A2+H60"].tolist() == [False, False, True, False]
    assert flags["A2+H80"].tolist() == [False, False, True, True]


def test_chm_against_the_surface(judged_canyon):
    """The canyon's CHMv2 (44 m on the tree, 0 elsewhere) against its surface model: on the gentle floor
    the tree by both (the surface 1 m higher), nothing by one alone; on the walls the rims tall in the
    surface model with CHMv2 low, the walls' tops bare without a tree of CHMv2."""
    call, dtm, real, rock = judged_canyon
    result = study.analyse_call(call, layers_of(dtm))
    assert not result.get("chm_shift", {}).get("applied")
    c = result["chm_surface"]
    gentle = int((obstacles.slope_degrees(dtm, 1.0) < study.CHM_GENTLE).sum())
    assert {k: v for k, v in c.items() if k != "diff"} == {
        "gentle": gentle, "both": 24, "dsm_only": 0, "chm_only": 0, "neither": gentle - 24,
        "steep_bare": 120, "steep_bare_chm_tree": 0, "steep_tall": 120, "steep_tall_chm_low": 120}
    assert sum(c["diff"]) == 24
    assert study.histogram_quantile(c["diff"], 0.5) == study.histogram_quantile(c["diff"], 0.9, True) == 1.125
    assert study.histogram_quantile([0] * len(c["diff"]), 0.5) is None
    text = "\n".join(study.chm_surface_report([{"place": "canyon", "chm_surface": c}] * 2))
    assert f"| canyon | {gentle} | 24 (0.4 %) | 0 (0.0 %) | 0 (0.0 %) | {gentle - 24} (99.6 %) | 1.12 | 1.12 | 1.12 | "            "0 % of 120 | 100 % of 120 |" in text
    assert f"| all | {2 * gentle} | 48 (0.4 %) |" in text
