"""The source south_tyrol (sources/catalogue/italy.py): chosen in IT-BZ only, its tiles on the
coverage's own pixels (centres on multiples of 2.5 m). Offline: the recorded reverse answers of
tests/data/recorded/nominatim/reverse.json."""

import json
import math
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "nominatim", "reverse.json")
ORTLER = (46.509, 10.545)          # IT-32 and IT-BZ
TRENTO = (46.07, 11.12)            # IT-32 and IT-TN
# The 2.5 m coverages' lower-left corner (DescribeCoverage, 2026-11-01)
COVERAGE_CORNER = (604998.75, 5119998.75)


@pytest.fixture
def recorded(monkeypatch):
    with open(RECORDED, encoding="utf-8") as f:
        answers = {(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"] for r in json.load(f)}
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params:
                        answers[(round(lat, 5), round(lon, 5), params["zoom"])])


def test_chosen_in_its_province(tmp_path, recorded):
    assert src.choose_source("auto", *ORTLER, str(tmp_path)) == (src.SOURCES["south_tyrol"],
                                                                 "the centre is in IT-BZ")
    assert src.choose_source("auto", *TRENTO, str(tmp_path)) == (src.SOURCES["trento"],
                                                                 "the centre is in IT-TN")


def test_tiles_on_the_coverage_pixels():
    """Tile edges, the working grid's edges and the coverage's lie on the same 2.5 m lattice."""
    import grid as gd
    from rasterio.warp import transform
    source = src.SOURCES["south_tyrol"]
    lat, lon = source.sample
    (x,), (y,) = transform("EPSG:4326", source.crs, [lon], [lat])
    grid = gd.make_grid((x - 400, y - 400, x + 400, y + 400), source.default_resolution, source.crs,
                        source.grid_origin)
    for layer in (source.nmt, source.nmpt):
        tiles = layer.tiles(grid)
        assert tiles
        for tile in tiles:
            for edge, corner in zip(layer.index.edges(tile), COVERAGE_CORNER * 2):
                assert math.isclose((edge - corner) / 2.5, round((edge - corner) / 2.5), abs_tol=1e-9)
    for edge, corner in zip((grid.left, grid.top), COVERAGE_CORNER):
        assert math.isclose((edge - corner) / 2.5, round((edge - corner) / 2.5), abs_tol=1e-9)
