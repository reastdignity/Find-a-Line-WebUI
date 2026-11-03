"""tools/study_landcover.py: OSM land cover rasterized onto a captured call's working grid, from a
theme tile written into a scratch cache (no extracts, no Overpass)."""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
import cache  # noqa: E402
import osm  # noqa: E402
import study_landcover as sl  # noqa: E402

# The Żabi Koń clip's box (tests/data/zabi_kon_nmt.tif) at 10 m
GRID = {"crs": "EPSG:2180", "left": 553665.5, "top": 254908.5, "res": 10.0, "height": 60, "width": 60,
        "core": None}


def _cells(col0, row0, col1, row1):
    """A ring on the grid's pixel edges, in WGS84 (as a theme tile holds it)."""
    from pyproj import Transformer
    to = Transformer.from_crs(GRID["crs"], "EPSG:4326", always_xy=True)
    x0, x1 = GRID["left"] + col0 * GRID["res"], GRID["left"] + col1 * GRID["res"]
    y0, y1 = GRID["top"] - row0 * GRID["res"], GRID["top"] - row1 * GRID["res"]
    return [list(to.transform(x, y)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]


def _theme_tiles(cache_dir: str, features):
    """The landcover tiles over the grid's box, the features in each, recorded so that osm.theme
    finds them cached."""
    for lat, lon in osm.tiles(*sl._bbox_wgs84(GRID)):
        path = osm.theme_path(cache_dir, "landcover", lat, lon)
        osm.write_tile(path, features)
        cache.record(cache_dir, path, url="test")


def test_landcover_on_grid(tmp_path, monkeypatch):
    """A wood relation with a hole and a scree way overlapping it: forest where the wood is but not in
    its hole, rock where the scree is, also where both are mapped; the rest none."""
    import osmextract
    monkeypatch.setattr(osmextract, "build_tile", lambda *args: (_ for _ in ()).throw(AssertionError("built")))
    cache_dir = str(tmp_path / "cache")
    wood = {"type": "Feature", "properties": {"id": "relation/1", "tags": {"natural": "wood"},
                                              "roles": ["outer", "inner"]},
            "geometry": {"type": "MultiLineString", "coordinates": [_cells(5, 5, 30, 30), _cells(10, 10, 15, 15)]}}
    scree = {"type": "Feature", "properties": {"id": "way/2", "tags": {"natural": "scree"}},
             "geometry": {"type": "LineString", "coordinates": _cells(25, 25, 40, 40)}}
    track = {"type": "Feature", "properties": {"id": "way/3", "tags": {"landuse": "meadow"}},
             "geometry": {"type": "LineString", "coordinates": _cells(45, 45, 50, 50)}}
    _theme_tiles(cache_dir, [wood, scree, track])
    classes = sl.landcover_on_grid(GRID, cache_dir)
    assert classes.shape == (60, 60) and classes.dtype == np.uint8
    expected = np.zeros((60, 60), np.uint8)
    expected[5:30, 5:30] = sl.FOREST
    expected[10:15, 10:15] = sl.NONE
    expected[25:40, 25:40] = sl.ROCK
    assert np.array_equal(classes, expected)
    assert (classes == sl.FOREST).sum() == 625 - 25 - 25 and (classes == sl.ROCK).sum() == 225

    call = tmp_path / "call-0"
    call.mkdir()
    (call / "grid.json").write_text(json.dumps(GRID))
    assert sl.main([str(call), "--data-dir", str(tmp_path)]) == 0
    assert np.array_equal(np.load(call / sl.FILE), expected)


def test_landcover_without_tiles(tmp_path, monkeypatch, capsys):
    """The theme's tiles cannot be had (Overpass's daily cap): landcover.npy is an empty array and the
    reason is printed, nothing raised; an area without land cover gives none everywhere."""
    def refused(*args, **kwargs):
        raise osm.OverpassDayMax("the 75 Overpass queries of today (UTC) are used up", "overpass_day_max", max=75)
    monkeypatch.setattr(osm, "theme", refused)
    classes = sl.write_landcover(str(tmp_path), GRID, str(tmp_path / "cache"))
    saved = np.load(tmp_path / sl.FILE)
    assert classes.size == 0 and saved.size == 0 and saved.dtype == np.uint8
    assert "no OSM land cover" in capsys.readouterr().out
    monkeypatch.setattr(osm, "theme", lambda *args, **kwargs: [])
    assert not sl.landcover_on_grid(GRID, str(tmp_path / "cache")).any()
