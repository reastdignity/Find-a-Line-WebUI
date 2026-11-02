"""tools/obstacle_study.py on a synthetic canyon: the capture of a find_valid_lines call, the
rules' counts checked against the production kernel, the outside layers' classes, the shift of
CHMv2, the names of the WorldCover tiles, the report, and a cache link removed without its target."""

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


def canyon_grids():
    """A canyon whose walls stand inside pixels 20 and 79 (terrain at the pixels' centres, the
    surface their highest point) with a tree of 45 m on its floor in rows 20-25."""
    x = (np.arange(COLS * FINE) + 0.5) / FINE
    ground = lambda x: np.where((x >= 20.35) & (x < 79.65), 50.0, 100.0)  # noqa: E731
    dtm = np.tile(ground(np.arange(COLS) + 0.5).astype(np.float32), (ROWS, 1))
    dsm = np.tile(ground(x).reshape(COLS, FINE).max(axis=1).astype(np.float32), (ROWS, 1))
    dsm[TREE_ROWS, TREE_COLS] += 45
    return dtm, dsm


def capture_call(tmp_path):
    """One find_valid_lines call captured as obstacle_study.capture captures it."""
    dtm, dsm = canyon_grids()
    anchors = sh.find_significant_slopes(dtm, 1.0, 45, np.ones(dtm.shape, dtype=bool))
    wrapper = study.Capture(str(tmp_path / "capture"))
    wrapper.grid = SimpleNamespace(crs="EPSG:2180", left=500000.0, top=300000.0, res=1.0, height=ROWS,
                                   width=COLS), None
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
                       "chm_shift": [None]}, f)
    text = study.report(str(tmp_path))
    assert "| R1 | test | 1.0 | 10 | 4 | 5 |" in text and "| A1 | 10 (56 %) | 2 (25 %), 2 | 2 (20 %) | 6 (100 %) | 0, 0 | 8 |" in text
    assert "Places where a check failed: none" in text


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
