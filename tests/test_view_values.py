"""The rule of a square's value at the result view's Area level (viewer/src/result/SpotMap.ts valueAt; the design
review's list of step 3c, item 3), run under Node: in its square's middle where its box there keeps PAD px clear of
every box (the controls over the map, the picks' numbers), whatever its width; else at the first clear place of
eight nearer the square's sides and corners with the whole box inside the square; else left out. SpotMap.ts is
bundled with a stand-in for Leaflet (the rule needs none; the module makes its renderer's class when it loads).
The map's own check is tests/test_shell_c_view_map.py::test_area_values_clear."""
import json
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

PAD = 2  # SpotMap.ts PAD: px a number's shape, and a square's value, keeps clear of a control


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """SpotMap.ts bundled for Node, Leaflet replaced by a stand-in with the one call the module makes when it loads."""
    folder = tmp_path_factory.mktemp("values-bundle")
    stub = folder / "leaflet_stub.js"
    stub.write_text("module.exports = {Renderer: {extend: () => function Draw() {}}};\n", encoding="utf-8")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export {{ valueAt, markSize }} from "{src}/result/SpotMap";\n', encoding="utf-8")
    out = folder / "values.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], "
                                  "bundle: true, format: 'cjs', platform: 'node', "
                                  f"alias: {{leaflet: {json.dumps(str(stub))}}}, "
                                  "loader: {'.css': 'empty', '.png': 'empty', '.svg': 'text'}, "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


def value_at(tmp_path, bundle, cases: list) -> list:
    """valueAt of each case [corners, hw, hh, boxes] in Node."""
    script = tmp_path / "values.cjs"
    script.write_text("const v = require(process.argv[2]), cases = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));\n"
                      "process.stdout.write(JSON.stringify(cases.map(([c, hw, hh, boxes]) => v.valueAt(c, hw, hh, boxes))));\n",
                      encoding="utf-8")
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    result = subprocess.run(["node", str(script), str(bundle), str(data)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def square(x0, y0, side):
    """A square's corners in order round it (as SpotMap gives them: the grid's south-west, south-east, north-east,
    north-west, on the screen bottom left, bottom right, top right, top left)."""
    return [[x0, y0 + side], [x0 + side, y0 + side], [x0 + side, y0], [x0, y0]]


def inside(at, hw, hh, corners) -> bool:
    """The value's box inside a convex square (each corner of the box on the inner side of each edge)."""
    box = [(at[0] + sx * hw, at[1] + sy * hh) for sx in (-1, 1) for sy in (-1, 1)]
    sides = []
    for k in range(4):
        (ax, ay), (bx, by) = corners[k], corners[(k + 1) % 4]
        sides.append([(bx - ax) * (py - ay) - (by - ay) * (px - ax) for px, py in box])
    return all(all(s >= -1e-9 for s in side) for side in sides) or all(all(s <= 1e-9 for s in side) for side in sides)


def clear(at, hw, hh, boxes) -> bool:
    return all(at[0] + hw <= r[0] - PAD or at[0] - hw >= r[2] + PAD or at[1] + hh <= r[1] - PAD or at[1] - hh >= r[3] + PAD
               for r in boxes)


def test_the_middle_where_it_is_clear(tmp_path, bundle):
    """Nothing near: the square's middle, as the values always stood; a box exactly PAD px from it is clear; a value
    wider than its square stays in the middle too (today's picture: a value of four digits in a square of 26 px)."""
    sq = square(100, 200, 40)
    cases = [[sq, 8, 7.25, []],
             [sq, 8, 7.25, [[128 + PAD, 0, 400, 400]]],  # its right edge at 128: a box from 130 on is clear
             [square(100, 200, 26), 15.5, 7.25, []],
             [square(100, 200, 26), 15.5, 7.25, [[0, 0, 50, 50]]]]  # a box far away
    got = value_at(tmp_path, bundle, cases)
    assert got == [[120, 220], [120, 220], [113, 213], [113, 213]], got


def test_moved_inside_its_square(tmp_path, bundle):
    """The middle under a box: the first clear place of eight (top, bottom, left, right, then the corners), its whole
    box inside the square and PAD px clear of every box; a square turned a little on the web map keeps it inside."""
    sq, hw, hh = square(100, 200, 52), 8, 7.25
    middle = [[120, 220, 132, 232]]  # a small box over the middle (126, 226)
    top_too = middle + [[100, 190, 152, 216]]  # and over the square's top band
    sides = top_too + [[100, 236, 152, 262]]  # and the bottom band: left or right is left
    turned = [[100.0, 252.0], [152.0, 254.5], [154.5, 202.5], [102.5, 200.0]]
    cases = [[sq, hw, hh, middle], [sq, hw, hh, top_too], [sq, hw, hh, sides], [turned, hw, hh, middle]]
    got = value_at(tmp_path, bundle, cases)
    assert got[0] == [126, 200 + hh], got  # the top: the square's top edge plus its half height
    assert got[1] == [126, 252 - hh], got  # the bottom
    assert got[2] == [100 + hw, 226], got  # the left
    for (corners, w, h, boxes), at in zip(cases, got):
        assert at is not None and inside(at, w, h, corners) and clear(at, w, h, boxes), (corners, boxes, at)


def test_left_out(tmp_path, bundle):
    """No clear place: null (the value is left out, its square stays). A value wider than its square cannot move
    inside it: under a box in the middle it is left out at once."""
    sq = square(100, 200, 40)
    cases = [[sq, 8, 7.25, [[90, 190, 150, 250]]],  # one box over the whole square
             [sq, 8, 7.25, [[100, 200, 140, 214], [100, 226, 140, 240], [100, 214, 140, 226]]],  # three bands: nothing left
             [square(100, 200, 26), 15.5, 7.25, [[110, 210, 116, 216]]]]  # too wide to move, the middle taken
    assert value_at(tmp_path, bundle, cases) == [None, None, None]


def test_a_pick_number_beside_the_middle(tmp_path, bundle):
    """A pick's diamond (its box, SpotMap markSize: 19 x 13.5 px each way) over a square's middle and its bottom right:
    the value moves away inside its square, clear of the diamond's box by PAD px."""
    sq, hw, hh = square(100, 200, 52), 8, 7.25
    diamond = [[140 - 19, 240 - 13.5, 140 + 19, 240 + 13.5]]  # its middle between the square's middle and corner
    got = value_at(tmp_path, bundle, [[sq, hw, hh, diamond]])[0]
    assert got is not None and inside(got, hw, hh, sq) and clear(got, hw, hh, diamond), got
    assert got == [126, 200 + hh], got  # the top's middle is the first clear place
