"""
Run by hand (and by tools/obstacle_study.py): OpenStreetMap's land cover on a captured call's
working grid, one of the judges of what a pixel of the surface model is (docs/roadmap.md,
priority 1: trees and buildings, or the terrain's own rock).

    uv run tools/study_landcover.py <out>/<place>/capture/call-0 [...] --data-dir <data folder>

reads each call folder's grid.json (the georeference obstacle_study.py's capture writes) and writes
landcover.npy beside it: uint8 on the working grid, NONE (0), FOREST (1: natural=wood,
landuse=forest) or ROCK (2: natural=bare_rock, natural=scree), rock painted after forest so it
wins where both are mapped; a pixel is the class of the area holding its centre. The features are
the OSM theme "landcover" (osm.THEME_TAGS), its 0.25° tiles from the data folder's cache or else
asked from Overpass, never built from the Geofabrik extracts (osmextract.EXTRACT_THEMES: a country's
land cover is about 100 times the other themes). Each new tile is one query of the data folder's
daily cap (osm.OVERPASS_DAY_MAX, 75): the limit of a study run, whose places take 1-4 tiles each,
so a study of many places fills its tiles over a day or two (cached tiles are kept a year). When the
tiles cannot be had (the service down, the cap reached) the file is an empty array and the reason is
printed: the study goes on without this judge.

OSM maps land cover unevenly: a wood without a polygon is NONE, not rock, so only FOREST and ROCK
say something. Ways and relations are made areas by osm.polygons (outer rings less inner ones).
OSM data: (c) OpenStreetMap contributors, ODbL.
"""

import argparse
import json
import os
import sys
from typing import Dict, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import requests  # noqa: E402

import osm  # noqa: E402

NONE, FOREST, ROCK = 0, 1, 2
FOREST_TAGS = (("natural", "wood"), ("landuse", "forest"))
ROCK_TAGS = (("natural", "bare_rock"), ("natural", "scree"))
FILE = "landcover.npy"


def _bbox_wgs84(grid: Dict):
    """The WGS84 box of a grid.json's grid (its edges densified, so the box holds the whole grid)."""
    from rasterio.warp import transform_bounds
    right = grid["left"] + grid["width"] * grid["res"]
    bottom = grid["top"] - grid["height"] * grid["res"]
    return transform_bounds(grid["crs"], "EPSG:4326", grid["left"], bottom, right, grid["top"])


def _classes(tags: Dict) -> list:
    """The classes an area's tags give (both when a wood is mapped on scree)."""
    found = []
    if any(tags.get(key) == value for key, value in FOREST_TAGS):
        found.append(FOREST)
    if any(tags.get(key) == value for key, value in ROCK_TAGS):
        found.append(ROCK)
    return found


def landcover_on_grid(grid: Dict, cache_dir: str, update: Optional[str] = None) -> np.ndarray:
    """The land cover classes (NONE, FOREST, ROCK) of a grid.json's grid, uint8 of its shape.

    Errors of the theme's tiles (requests errors, osm.OverpassDayMax) are passed on."""
    from affine import Affine
    import shapely
    from rasterio import features
    from shapely.geometry import box, mapping

    import area as ar
    shape = (grid["height"], grid["width"])
    found = osm.theme("landcover", *_bbox_wgs84(grid), cache_dir, update)
    frame = box(grid["left"], grid["top"] - grid["height"] * grid["res"],
                grid["left"] + grid["width"] * grid["res"], grid["top"])
    shapes = {FOREST: [], ROCK: []}
    for polygon, tags in osm.polygons(found):
        classes = _classes(tags)
        if not classes:
            continue
        local = ar.project(polygon, "EPSG:4326", grid["crs"])
        local = (local if local.is_valid else shapely.make_valid(local)).intersection(frame)
        if local.is_empty:
            continue
        for value in classes:
            shapes[value].append((mapping(local), value))
    ordered = shapes[FOREST] + shapes[ROCK]  # later shapes replace earlier ones: rock wins
    if not ordered:
        return np.zeros(shape, np.uint8)
    transform = Affine(grid["res"], 0, grid["left"], 0, -grid["res"], grid["top"])
    return features.rasterize(ordered, out_shape=shape, transform=transform, fill=NONE, dtype="uint8")


def write_landcover(call: str, grid: Dict, cache_dir: str):
    """Write <call>/landcover.npy: landcover_on_grid, or an empty array when the theme's tiles could
    not be had (printed, never raised)."""
    try:
        classes = landcover_on_grid(grid, cache_dir)
    except requests.RequestException as e:  # osm.OverpassDayMax and Overpass's timeouts too
        import cache
        print(f"{call}: no OSM land cover ({cache.clean_error(e)})")
        classes = np.zeros(0, np.uint8)
    np.save(os.path.join(call, FILE), classes)
    return classes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("calls", nargs="+", help="call folders holding a grid.json")
    parser.add_argument("--data-dir", help="data folder whose cache/ holds the theme tiles (default: "
                                           "FINDALINE_DATA or the repository)")
    args = parser.parse_args(argv)
    import cache
    cache_dir = os.path.join(cache.data_dir(args.data_dir), "cache")
    for call in args.calls:
        with open(os.path.join(call, "grid.json")) as f:
            grid = json.load(f)
        classes = write_landcover(call, grid, cache_dir)
        if classes.size:
            print(f"{call}: forest {np.mean(classes == FOREST):.1%}, rock {np.mean(classes == ROCK):.1%} "
                  f"of {classes.size} pixels")
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
