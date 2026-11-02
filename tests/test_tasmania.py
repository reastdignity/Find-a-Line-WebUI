"""The source tasmania (sources/catalogue/australia.py): chosen in AU-TAS only (europe elsewhere in Australia),
its blocks and the working grid on the file's own pixel edges (off whole metres). Offline: Nominatim's reverse
answers recorded on 2026-11-02 (tests/data/recorded/nominatim/reverse-tasmania.json)."""

import json
import math
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "nominatim", "reverse-tasmania.json")
CAPE_HAUY = (-43.14, 148.0)        # AU-TAS (R52)
ORGAN_PIPES = (-42.893, 147.237)   # AU-TAS, Mount Wellington
SEA = (-43.2, 148.05)              # off Cape Hauy: AU-TAS at zoom 8 too
KING_ISLAND = (-39.85, 144.0)      # AU-TAS, west of zone 55
ARAPILES = (-36.75, 141.83)        # AU-VIC
# The file's upper-left corner (rasterio, 2026-11-02)
FILE_CORNER = (-30597.398268200195, 5687852.900000001)


@pytest.fixture
def recorded(monkeypatch):
    with open(RECORDED, encoding="utf-8") as f:
        answers = {(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"] for r in json.load(f)}
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params:
                        answers[(round(lat, 5), round(lon, 5), params["zoom"])])


def test_chosen_in_tasmania_only(tmp_path, recorded):
    for point in (CAPE_HAUY, ORGAN_PIPES, SEA, KING_ISLAND):
        assert src.choose_source("auto", *point, str(tmp_path)) == (src.SOURCES["tasmania"],
                                                                    "the centre is in AU-TAS"), point
    assert src.choose_source("auto", *ARAPILES, str(tmp_path)) == (src.SOURCES["europe"],
                                                                   "no national source for AU")


def test_offline_box(monkeypatch, tmp_path):
    """Offline, the region's box gives Australia and Tasmania; elsewhere in Australia no country."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    assert src.choose_source("auto", *CAPE_HAUY, str(tmp_path)) == (src.SOURCES["tasmania"],
                                                                    "the centre is in AU-TAS")
    assert src.choose_source("auto", *ARAPILES, str(tmp_path))[0].id == "europe"


def test_blocks_on_the_file_pixels():
    """Block edges, the working grid's edges and the file's lie on the same 2 m lattice, off whole metres."""
    import grid as gd
    from rasterio.warp import transform
    source = src.SOURCES["tasmania"]
    for lat, lon in (source.sample, CAPE_HAUY, KING_ISLAND):
        (x,), (y,) = transform("EPSG:4326", source.crs, [lon], [lat])
        grid = gd.make_grid((x - 1500, y - 1500, x + 1500, y + 1500), source.default_resolution, source.crs,
                            source.grid_origin)
        tiles = source.nmt.tiles(grid)
        assert len(tiles) >= 4
        for tile in tiles:
            for edge, corner in zip(source.nmt.index._edges(*tile), FILE_CORNER * 2):
                assert math.isclose((edge - corner) / 2, round((edge - corner) / 2), abs_tol=1e-6)
        for edge, corner in zip((grid.left, grid.top), FILE_CORNER):
            assert math.isclose((edge - corner) / 2, round((edge - corner) / 2), abs_tol=1e-6)
            assert not math.isclose(edge, round(edge), abs_tol=0.05)


def test_blocks_outside_the_file_make_no_request():
    """Blocks wholly outside the file's bounds are never read (missing without a request)."""
    index = src.SOURCES["tasmania"].nmt.index
    assert index._within_extent(259, 2625)
    assert not index._within_extent(-20, 2625) and not index._within_extent(259, 2900)


def test_no_surface_model_and_contour_note():
    source = src.SOURCES["tasmania"]
    assert source.nmpt is None
    assert "contours" in source.note and "LiDAR Coverage Index" in source.note
    assert "Source Cooperative" in source.credits[0].notice
    source.note.encode("cp1250")  # printed to a Windows console
