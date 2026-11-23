"""
Offline boxes of a region's source (`Source.offline`: the country of a point when it cannot be looked up), made from
the coverage map's outline of the region (viewer/src/coverage/shapes.json, Natural Earth): read only, prints the boxes.

The region is cut in bands of --band degrees of latitude; in each band, the runs of cells of --cell degrees of
longitude that lie inside the region's outline shrunk by --margin degrees and keep --off degrees off every other
country's outline of the file (not the region's own country) make one box each, (south, north, west, east). The
boxes keep off the neighbours' land (offline the first box holding a point wins), so a point near a border gets no
box: it takes the region's fallback offline. The outlines are simplified (the coverage map's 0.01 degree for regions,
0.03 for countries), hence the margins; `--check FILE` measures the boxes against another outline file (a Natural
Earth admin-1 ZIP of the unsimplified units: tools/coverage_shapes.py keeps one in the system's temporary folder) and
prints every box that holds land of another unit, with its km².

    uv run python tools/offline_boxes.py be-wal [--band 0.05] [--cell 0.01] [--margin 0.01] [--off 0.015]
                                         [--check ADMIN1.zip]

Wallonia's (`sources/catalogue/belgium.py` WALLONIA_OFFLINE) are this tool's output with its defaults
(tests/test_offline_boxes.py): with --off 0.01 a box held 0.18 km² of France's Ardennes (FR-08) by Natural Earth's
unsimplified units, with 0.015 none (2026-11-23).
"""

import argparse
import json
import os
import sys
from typing import List, Sequence, Tuple

from shapely.geometry import box, shape
from shapely.ops import unary_union

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHAPES = os.path.join(REPO, "viewer", "src", "coverage", "shapes.json")
BAND, CELL, MARGIN, OFF = 0.05, 0.01, 0.01, 0.015

Box = Tuple[float, float, float, float]


def outlines(area: str, shapes_path: str = SHAPES):
    """(the area's outline, the union of every other country's outline but the area's own country)."""
    with open(shapes_path, encoding="utf-8") as f:
        features = json.load(f)["features"]
    own = [shape(x["geometry"]) for x in features if x["properties"]["id"] == area]
    if not own:
        raise ValueError(f"{area}: no outline in {shapes_path}")
    country = area.split("-")[0]
    others = [shape(x["geometry"]).buffer(0) for x in features if x["properties"]["kind"] == "country"
              and x["properties"]["id"] != country]
    return unary_union(own), unary_union(others)


def offline_boxes(area: str, band: float = BAND, cell: float = CELL, margin: float = MARGIN, off: float = OFF,
                  shapes_path: str = SHAPES) -> List[Box]:
    """The boxes, south to north, west to east in a band, rounded to 4 decimals."""
    region, others = outlines(area, shapes_path)
    inner, keep_off = region.buffer(-margin), others.buffer(off)
    west, south, east, north = region.bounds
    boxes: List[Box] = []
    s = round(round(south / band) * band, 4)
    while s < north:
        n = round(s + band, 4)
        run = None
        c = round(round(west / cell) * cell, 4)
        while c < east + cell:
            e = round(c + cell, 4)
            piece = box(c, s, e, n)
            inside = inner.contains(piece) and not keep_off.intersects(piece)
            if inside and run is None:
                run = c
            if not inside and run is not None:
                boxes.append((s, n, round(run, 4), c))
                run = None
            c = e
        if run is not None:
            boxes.append((s, n, round(run, 4), c))
        s = n
    return boxes


def share(area: str, boxes: Sequence[Box], shapes_path: str = SHAPES) -> float:
    """The share of the area's outline the boxes cover."""
    region, _ = outlines(area, shapes_path)
    return unary_union([box(w, s, e, n) for s, n, w, e in boxes]).intersection(region).area / region.area


def foreign_land(area: str, boxes: Sequence[Box], admin1_zip: str) -> List[Tuple[Box, str, float]]:
    """Every box holding land of another admin-1 unit of the ZIP than the area's (its ISO 3166-2 code, or the units
    the coverage map merges for it), with that unit's code and the km² inside the box."""
    import geopandas as gpd
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from coverage_shapes import MERGED
    own = set(MERGED.get(area, (area.upper(),)))
    units = gpd.read_file(f"zip://{admin1_zip}", columns=["iso_3166_2"])
    found = []
    for s, n, w, e in boxes:
        piece = box(w, s, e, n)
        near = units[units.intersects(piece) & ~units["iso_3166_2"].isin(own)]
        for code, geom in zip(near["iso_3166_2"], near.geometry):
            km2 = float(gpd.GeoSeries([geom.intersection(piece)], crs="EPSG:4326").to_crs("EPSG:6933").area.iloc[0])
            if km2 > 0:
                found.append(((s, n, w, e), code, km2 / 1e6))
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("area", help="the coverage map's id of the region (be-wal)")
    parser.add_argument("--band", type=float, default=BAND, help="degrees of latitude of a band (default 0.05)")
    parser.add_argument("--cell", type=float, default=CELL, help="degrees of longitude of a cell (default 0.01)")
    parser.add_argument("--margin", type=float, default=MARGIN, help="degrees kept inside the region's outline "
                                                                     "(default 0.01)")
    parser.add_argument("--off", type=float, default=OFF, help="degrees kept off the other countries' outlines "
                                                               "(default 0.015)")
    parser.add_argument("--check", help="a Natural Earth admin-1 ZIP to measure the boxes against")
    args = parser.parse_args(argv)
    boxes = offline_boxes(args.area, args.band, args.cell, args.margin, args.off)
    print(f"{len(boxes)} boxes, {100 * share(args.area, boxes):.1f} % of the outline")
    for s, n, w, e in boxes:
        print(f"    ({s:.2f}, {n:.2f}, {w:.2f}, {e:.2f}),")
    if args.check:
        found = foreign_land(args.area, boxes, args.check)
        print(f"boxes holding other units' land: {len(found)}")
        for b, code, km2 in found:
            print(f"    {b}: {code} {km2:.3f} km²")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page ("km²")
    sys.exit(main())
