"""tools/offline_boxes.py: a region's offline boxes made from the coverage map's outline, keeping off its neighbours'
land; Wallonia's are its output."""

import json
import os
import sys

from shapely.geometry import box, mapping

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import offline_boxes as ob  # noqa: E402
from sources.catalogue.belgium import WALLONIA_OFFLINE  # noqa: E402


def test_wallonia_is_the_tools_output():
    """WALLONIA_OFFLINE is the tool's output with its defaults from the committed outline (so the boxes can be made
    again), and it covers about 84 % of the outline."""
    assert ob.offline_boxes("be-wal") == list(WALLONIA_OFFLINE)
    assert 0.83 < ob.share("be-wal", WALLONIA_OFFLINE) < 0.85


def test_boxes_inside_and_off_the_neighbours(tmp_path):
    """A square region of 1 x 1 degree beside a country whose outline reaches 0.2 degrees into the region's box: the
    bands' runs lie inside the region shrunk by the margin and keep the keep-off margin from the other country; the
    region's own country is no neighbour."""
    features = [
        {"type": "Feature", "properties": {"id": "xx-aa", "kind": "region"}, "geometry": mapping(box(10, 50, 11, 51))},
        {"type": "Feature", "properties": {"id": "xx", "kind": "country"}, "geometry": mapping(box(9, 49, 12, 52))},
        {"type": "Feature", "properties": {"id": "yy", "kind": "country"},
         "geometry": mapping(box(10.8, 50.0, 12.0, 50.5))}]
    path = tmp_path / "shapes.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    boxes = ob.offline_boxes("xx-aa", band=0.1, cell=0.05, margin=0.05, off=0.05, shapes_path=str(path))
    assert boxes and all(50.05 - 1e-9 <= s and n <= 50.95 + 1e-9 for s, n, _, _ in boxes)
    for s, n, w, e in boxes:
        assert w >= 10.05 - 1e-9 and e <= 10.95 + 1e-9, (s, n, w, e)
        if s < 50.55:  # beside yy (to 50.5 N, from 10.8 E): kept 0.05 off it
            assert e <= 10.75 + 1e-9, (s, n, w, e)
    assert any(e > 10.85 for s, n, w, e in boxes if s >= 50.6)  # north of yy the region's width
