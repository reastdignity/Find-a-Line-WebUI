"""tools/studylib.py: the data folder with its cache linked (the link removed afterwards, never the
cache behind it), the namespace of a capture's grid that end_zone_study's diagnosis reads, and the
helpers moved from tools/end_zone_study.py still importable from there."""

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import studylib  # noqa: E402

MOVED = ("_unlink", "to_pixel", "pixels_wgs84", "disc", "slope_degrees", "margins", "profile_chip")
GRID = {"crs": "EPSG:2180", "left": 553700.0, "top": 254900.0, "res": 1.0, "shape": [110, 130],
        "slope_threshold": 40.0, "nmpt": "mark", "fall": 6.0}


def _is_link(path) -> bool:
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


@pytest.fixture
def cache(tmp_path):
    folder = tmp_path / "cache"
    (folder / "layer").mkdir(parents=True)
    (folder / "layer" / "tile.txt").write_text("tile", encoding="utf-8")
    return folder


def test_linked_data_folder(tmp_path, cache):
    """The link inside the data folder shows the cache; afterwards only the link is gone."""
    place = tmp_path / "place"
    with studylib.linked_data_folder(str(place), str(cache)) as data:
        assert data == os.path.join(str(place), "data") and os.path.isabs(data)
        link = os.path.join(data, "cache")
        assert _is_link(link)
        assert open(os.path.join(link, "layer", "tile.txt"), encoding="utf-8").read() == "tile"
        with open(os.path.join(link, "new.txt"), "w", encoding="utf-8") as f:  # a search writing to the cache
            f.write("new")
    assert os.path.isdir(data) and not os.path.lexists(link)
    assert sorted(os.listdir(cache)) == ["layer", "new.txt"]
    assert (cache / "layer" / "tile.txt").read_text(encoding="utf-8") == "tile"


def test_linked_data_folder_after_an_error_and_a_stale_link(tmp_path, cache):
    """An error inside the block removes the link too; a link a killed run left is replaced."""
    import regression
    place = tmp_path / "place"
    with pytest.raises(RuntimeError):
        with studylib.linked_data_folder(str(place), str(cache)) as data:
            raise RuntimeError("the search failed")
    assert not os.path.lexists(os.path.join(data, "cache"))
    regression.link(str(cache), os.path.join(data, "cache"))  # left by a run that was killed
    with studylib.linked_data_folder(str(place), str(cache)) as again:
        assert again == data and os.path.exists(os.path.join(again, "cache", "layer", "tile.txt"))
    assert not os.path.lexists(os.path.join(data, "cache"))
    assert (cache / "layer" / "tile.txt").exists()


def test_linked_data_folder_without_a_cache(tmp_path):
    """cache_dir None: a plain empty data folder, nothing linked, nothing removed afterwards."""
    with studylib.linked_data_folder(str(tmp_path / "place"), None) as data:
        assert os.listdir(data) == []
        os.makedirs(os.path.join(data, "cache"))  # the search's fresh cache
    assert os.path.isdir(os.path.join(data, "cache")) and not _is_link(os.path.join(data, "cache"))


def test_grid_namespace(tmp_path):
    """The attributes end_zone_study's diagnosis reads; pixels to WGS84 and back."""
    rng = np.random.default_rng(3)
    z = rng.random((110, 130)).astype(np.float32) * 5 + 300
    anchors = [[5, 7], [60, 90]]
    a = studylib.grid_namespace(GRID, z, z + 1, None, anchors, 6.0)
    assert a.z is z and a.res == 1.0 and a.sag_table is None and a.fall == 6.0 and a.grid is GRID
    assert a.anchors.dtype == np.int64 and a.anchors.shape == (2, 2) and a.anchors.flags.c_contiguous
    assert a.surface.shape == z.shape and a.slope_threshold == 40.0 and a.nmpt_mode == "mark"
    empty = studylib.grid_namespace({**GRID, "res": 2}, z, None, None, np.zeros((0, 2)), 4.5)
    assert empty.anchors.shape == (0, 2) and empty.surface is None and empty.res == 2.0
    assert empty.slope_threshold == 40.0
    pixels = [(0, 0), (5, 7), (109, 129), (57, 3)]
    for pixel, (lat, lon) in zip(pixels, studylib.pixels_wgs84(GRID, pixels)):
        assert studylib.to_pixel(GRID, lat, lon) == pixel


def test_grid_namespace_feeds_the_diagnosis():
    """end_zone_study.diagnose_line and line_detail on grid_namespace's object: a wall-to-wall line
    across the canyon of test_end_zone_study (2.1 m of clearance between these two pixels of 83 and
    85 degrees) is accepted, its staircase needs no lift."""
    import end_zone_study as ezs
    from test_end_zone_study import canyon
    z = canyon(np.random.default_rng(5))
    z[np.isnan(z)] = 100.0
    slope = studylib.slope_degrees(z, 1.0)
    anchors = np.argwhere(slope >= 40)
    a = studylib.grid_namespace(GRID, z, None, None, anchors, 6.0)
    assert np.min(studylib.margins(z, (55, 32), (55, 95), 1.0, None)[0]) > 2
    ends = studylib.pixels_wgs84(GRID, [(55, 32), (55, 95)])
    line = {"name": "across", "a": ends[0], "b": ends[1]}
    result = ezs.diagnose_line(a, slope, set(map(tuple, a.anchors.tolist())), line, 2.0, [0, 5], 0.25, 0.0,
                               [45, 30])
    assert result["pixels"] == [[55, 32], [55, 95]]
    assert result["ends"][0]["anchor_within"] == 0.0 and result["ends"][1]["45"] == 0.0
    assert result["best"]["accepted"] and result["best"]["clearance"] > 2
    assert result["staircase"][0]["lift"] == 0.0
    detail = ezs.line_detail(a, result["best"]["a1"], result["best"]["a2"], [0, 5], 0.25, a.fall)
    assert detail["clearance"] == result["best"]["clearance"]


def test_moved_names_still_in_end_zone_study():
    """The helpers moved to studylib are importable from end_zone_study under the same names."""
    import end_zone_study as ezs
    for name in MOVED:
        assert getattr(ezs, name) is getattr(studylib, name), name
