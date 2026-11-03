"""The imagery of the 3D view (viewer/src/view3d/tiles.ts, credits.ts, imagery.ts) in Node: the tiles covering a
chunk, their URLs (our cache, the WMS over its base, the base alone, Esri), the UVs, the zoom within 2048 px and
the budgets, the credits' HTML, the white test of a WMS's JPEG against orthophoto._white_blocks, a WMS's version and
CRS against orthophoto._get_map, and the imagery module on a fake scene (docs/3d-view-contract.md, "Wave 2"; "Wave
4", V4c)."""
import io
import json
import math
from urllib.parse import parse_qsl

import numpy as np
import pytest
from PIL import Image

import orthophoto
from test_viewer import pytestmark, run_ts  # noqa: F401 (the skip without Node)

# lon = a0 + a1·x + a2·y, lat = b0 + b1·x + b2·y around Żabi Koń in EPSG:2180 (a 1537 m patch's least squares)
AFFINE = [11.963081470588662, 1.4001724012255665e-05, 1.4190803737725686e-07,
          47.916360330815, -9.117204921194876e-08, 8.99572601321793e-06]
CX, CY = 554008, 254576
# A plane near the equator (a metre is about 9e-6 degrees both ways)
EQUATOR = [0.0, 9e-6, 0.0, 0.0, 0.0, 9e-6]

GEOPORTAL = {"name": "Geoportal", "url": "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/HighResolution",
             "layer": "Raster", "attribution": "Orthophoto: GUGiK", "attribution_url": "https://www.geoportal.gov.pl",
             "base": {"url": "https://example.org/wmts?SERVICE=WMTS&TileMatrix={z}&TileCol={x}&TileRow={y}",
                      "max_zoom": 18},
             "cache": "/runs/r1/../../cache/orthophoto/poland/wm256"}
SWISS = {"name": "SWISSIMAGE", "url": None, "layer": "", "attribution": "swisstopo",
         "base": {"url": "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg",
                  "max_zoom": 20},
         "cache": None}


def world_pixel(affine, x, y, z):
    """Python's own: grid metres → lon/lat (the affine) → world pixels of Web Mercator at zoom z."""
    lon = affine[0] + affine[1] * x + affine[2] * y
    lat = affine[3] + affine[4] * x + affine[5] * y
    n = 256 * 2 ** z
    return ((lon + 180) / 360 * n,
            (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2 * n)


def chunk(i, j, side=513.0, cx=CX, cy=CY):
    x0, y1 = cx - 1537 / 2 + j * (side - 1), cy + 1537 / 2 - i * (side - 1)
    return {"x0": x0, "y0": y1 - side, "x1": x0 + side, "y1": y1}


def test_tiles_covering_a_chunk(tmp_path):
    b = chunk(1, 1)
    found = run_ts(tmp_path, "view3d/tiles", f"""
const p = m.planAt({json.dumps(AFFINE)}, {json.dumps(b)}, 17);
console.log(JSON.stringify({{plan: p, tiles: m.tilesOf(p)}}));""")
    corners = [world_pixel(AFFINE, x, y, 17) for x in (b["x0"], b["x1"]) for y in (b["y0"], b["y1"])]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    plan = found["plan"]
    assert plan["z"] == 17 and plan["px0"] == math.floor(min(xs)) and plan["py0"] == math.floor(min(ys))
    assert plan["width"] == math.ceil(max(xs)) - plan["px0"] and plan["height"] == math.ceil(max(ys)) - plan["py0"]
    expected = [[x, y] for y in range(math.floor(min(ys) / 256), math.floor((math.ceil(max(ys)) - 1) / 256) + 1)
                for x in range(math.floor(min(xs) / 256), math.floor((math.ceil(max(xs)) - 1) / 256) + 1)]
    assert found["tiles"] == expected and len(expected) >= 4


def test_zoom_within_the_canvas_and_the_budgets(tmp_path):
    side5 = 2561.0  # a chunk of 5 m data: 512 samples of 5 m and the edge
    found = run_ts(tmp_path, "view3d/tiles", f"""
const A = {json.dumps(AFFINE)}, E = {json.dumps(EQUATOR)}, b = {json.dumps(chunk(1, 1))};
const z = (a, bounds, line, level) => m.zoomFor(a, bounds, m.maxZoomOf(line, level));
const chunks = (n, side) => {{
  const out = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {{
    const x0 = {CX} - 768.5 + j * (side - 1), y1 = {CY} + 768.5 - i * (side - 1);
    // the patch is 1537 m: the padding beyond it holds no data
    const x1 = Math.min(x0 + side, {CX} + 768.5), y0 = Math.max(y1 - side, {CY} - 768.5);
    out.push({{bounds: {{x0, y0, x1, y1}}, hasLine: i === 1}});
  }}
  return out;
}};
const sizes = (plans) => plans.map((p) => p && [p.z, p.width, p.height, Math.round(m.textureBytes(p) / 1e5) / 10]);
const full = m.planTextures(A, chunks(3, 513), "full"), phone = m.planTextures(A, chunks(2, 1025), "phone");
const total = (plans) => plans.reduce((s, p) => s + m.textureBytes(p), 0);
console.log(JSON.stringify({{
  line: z(A, b, true, "full"), other: z(A, b, false, "full"), phone: z(A, b, true, "phone"),
  equator: z(E, {{x0: 0, y0: 0, x1: 513, y1: 513}}, true, "full"),
  coarse: z(A, {{x0: {CX}, y0: {CY}, x1: {CX} + {side5}, y1: {CY} + {side5}}}, false, "full"),
  full: sizes(full), fullTotal: total(full), phoneSizes: sizes(phone), phoneTotal: total(phone),
  allLines: total(m.planTextures(A, chunks(3, 513).map((c) => ({{...c, hasLine: true}})), "full")),
}}));""")
    # zoom 19 at 1 m does not fit 2048 px at 50° N (0.19 m a pixel): 18; at the equator it does
    assert found["line"]["z"] == 18 and max(found["line"]["width"], found["line"]["height"]) <= 2048
    assert found["equator"]["z"] == 19 and found["equator"]["width"] <= 2048
    assert found["other"]["z"] == 17 and found["phone"]["z"] == 17 and found["coarse"]["z"] == 16
    assert all(max(w, h) <= 2048 for _, w, h, _ in found["full"] + found["phoneSizes"])
    assert found["fullTotal"] <= 60e6 and found["allLines"] <= 60e6 and found["phoneTotal"] <= 18e6
    assert [s[0] for s in found["full"]] == [17, 17, 17, 18, 18, 18, 17, 17, 17]
    print("desktop", found["full"], found["fullTotal"] / 1e6, "phone", found["phoneSizes"], found["phoneTotal"] / 1e6)


def test_urls_of_the_services(tmp_path):
    found = run_ts(tmp_path, "view3d/tiles", f"""
const g = {json.dumps(GEOPORTAL)}, s = {json.dumps(SWISS)}, wmsOnly = {{...g, base: null}};
const plan = {{z: 19, px0: 256 * 290000 + 10, py0: 256 * 180000 + 10, width: 300, height: 10}};
const corridor = {{a: [256 * 290000 + 20, 256 * 180000 + 20], b: [256 * 290000 + 40, 256 * 180000 + 20], half: 30}};
console.log(JSON.stringify({{
  withBase: m.orthoComposed(g, 17, 72000, 44000), wmsOnly: m.orthoLayers(wmsOnly, 17, 72000, 44000),
  baseAbove: m.orthoComposed(g, 20, 290001, 180003), swiss: m.orthoLayers(s, 17, 68000, 46000),
  cache: m.cacheTile("/cache/orthophoto/poland/wm256", 19, 290000, 180000),
  esri: m.esriDraws("k&y", {{z: 17, px0: 256 * 72000, py0: 256 * 44000, width: 256, height: 256}}),
  bbox: m.wmsBbox(17, 72000, 44000),
  draws: m.orthoDraws(g, plan, corridor).map((d) => [d.x, d.y, d.cache]),
  first: [m.cacheFirst(16, 1, 1, null), m.cacheFirst(17, 1, 1, null), m.cacheFirst(19, 1, 1, null)],
  busted: [m.cacheBusted("https://a/b.jpg"), m.cacheBusted("https://a/b?c=1")],
  ortho: [m.orthoOf(g) !== null, m.orthoOf(null), m.orthoOf({{name: "x", attribution: "y", url: null, base: null}})],
}}));""")
    bbox = orthophoto._wms_bbox(17, 72000, 44000)
    assert [float(v) for v in found["bbox"].split(",")] == pytest.approx([float(v) for v in bbox.split(",")], abs=1e-12)
    composed = found["withBase"]
    assert composed["base"] == {"url": "https://example.org/wmts?SERVICE=WMTS&TileMatrix=17&TileCol=72000"
                                       "&TileRow=44000"}
    assert composed["png"]["url"] == (GEOPORTAL["url"] + "?service=WMS&request=GetMap&layers=Raster&styles="
                                      "&format=image%2Fpng&transparent=true&version=1.3.0&width=256&height=256"
                                      "&crs=EPSG%3A4326&bbox=" + found["bbox"])
    assert composed["jpeg"]["url"] == composed["png"]["url"].replace("image%2Fpng&transparent=true",
                                                                     "image%2Fjpeg&transparent=false")
    [jpeg] = found["wmsOnly"]
    assert jpeg == composed["jpeg"]
    # above the base's last zoom (18): the part of its tile there, enlarged (orthophoto.py _base_tile)
    assert found["baseAbove"]["base"] == {"url": "https://example.org/wmts?SERVICE=WMTS&TileMatrix=18&TileCol=72500"
                                                 "&TileRow=45000", "crop": [64, 192, 64]}
    assert "crop" not in found["baseAbove"]["jpeg"] and "crop" not in found["baseAbove"]["png"]
    assert found["swiss"] == [{"url": "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current"
                                      "/3857/17/68000/46000.jpeg"}]
    assert found["cache"] == "/cache/orthophoto/poland/wm256/19/290000/180000.jpg"
    assert found["esri"] == [{"x": 72000, "y": 44000, "cache": None, "layers": [{
        "url": "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/17/44000/72000"
               "?token=k%26y"}]}]
    # zoom 19: the cache first only for the tile the corridor crosses, the next one straight from the service
    cache = GEOPORTAL["cache"]
    assert found["draws"] == [[290000, 180000, f"{cache}/19/290000/180000.jpg"], [290001, 180000, None]]
    assert found["first"] == [True, False, False]
    assert found["busted"] == ["https://a/b.jpg?_fal3d=1", "https://a/b?c=1&_fal3d=1"]
    assert found["ortho"] == [True, None, None]


def test_wms_versions_and_crs_as_the_cache_asks(tmp_path, monkeypatch):
    """A WMS of OrthoService.wms_version 1.1.1 (SRS, EPSG:4326 in lon-lat order) or wms_crs EPSG:3857 (the tile's
    Mercator box, x before y) is asked as orthophoto._get_map asks it (batch 3: Slovenia, Iceland); its JPEG is drawn
    over white, its transparent PNG not."""
    combos = [("1.3.0", "EPSG:4326"), ("1.1.1", "EPSG:4326"), ("1.1.1", "EPSG:3857"), ("1.3.0", "EPSG:3857")]
    orthos = [{**GEOPORTAL, "base": None, **({"wms_version": v} if v != "1.3.0" else {}),
               **({"wms_crs": c} if c != "EPSG:4326" else {})} for v, c in combos]
    found = run_ts(tmp_path, "view3d/tiles", f"""
const orthos = {json.dumps(orthos)};
console.log(JSON.stringify({{
  tiles: orthos.map((o) => [m.wmsTile(o, 17, 72000, 44000), m.wmsTile(o, 17, 72000, 44000, true)]),
  boxes: [m.mercatorBox(17, 72000, 44000), m.mercatorBox(17, 65536, 65535)]}}));""")
    asked = []
    monkeypatch.setattr(orthophoto, "_get", lambda url, params, z, x, y: asked.append((url, params)) or b"")
    for (version, crs), pair in zip(combos, found["tiles"]):
        for tile, png in zip(pair, (False, True)):
            asked.clear()
            orthophoto._get_map(GEOPORTAL["url"], "Raster", 17, 72000, 44000, png=png, version=version, crs=crs)
            [(url, params)] = asked
            base, query = tile["url"].split("?", 1)
            got = {k.upper(): v for k, v in parse_qsl(query, keep_blank_values=True)}
            expected = {k: str(v) for k, v in params.items()}
            assert base == url
            assert [float(v) for v in got.pop("BBOX").split(",")] == pytest.approx(
                [float(v) for v in expected.pop("BBOX").split(",")], abs=1e-9)
            # the server leaves TRANSPARENT out of a JPEG's request (FALSE by default), the page names it
            assert (got.pop("TRANSPARENT"), expected.pop("TRANSPARENT", "FALSE")) == (
                ("true", "TRUE") if png else ("false", "FALSE"))
            assert got == expected, (version, crs, png)
            assert tile.get("white", False) is not png
    assert found["boxes"] == [pytest.approx(list(orthophoto.mercator_box(17, 72000, 44000)), abs=1e-9),
                              pytest.approx(list(orthophoto.mercator_box(17, 65536, 65535)), abs=1e-9)]


def test_composed_everywhere(tmp_path):
    """A WMS over base tiles is composed on every tile (the corridor rule of 4b3da63 gave a patchwork of two
    flights), our cache first where it may hold the tile; a WMS without base tiles and base tiles alone as they
    are."""
    found = run_ts(tmp_path, "view3d/tiles", f"""
const g = {json.dumps(GEOPORTAL)}, wmsOnly = {{...g, base: null}};
const fine = {{z: 19, px0: 256 * 290000 + 10, py0: 256 * 180000 + 10, width: 300, height: 10}};
const overview = {{z: 17, px0: 256 * 72000 + 10, py0: 256 * 44000 + 10, width: 300, height: 10}};
const corridor = {{a: [256 * 290000 + 20, 256 * 180000 + 20], b: [256 * 290000 + 40, 256 * 180000 + 20], half: 30}};
const wide = {{a: [256 * 72000 + 20, 256 * 44000 + 20], b: [256 * 72000 + 400, 256 * 44000 + 20], half: 300}};
const s = {json.dumps(SWISS)};
const kinds = (draws) => draws.map((d) => [d.cache ? "cache" : "-", d.composed ? "composed"
  : d.layers.map((l) => l.url.toLowerCase().includes("wmts") ? "base" : "wms").join("+")]);
console.log(JSON.stringify({{
  fine: kinds(m.orthoDraws(g, fine, corridor)), overview: kinds(m.orthoDraws(g, overview, wide)),
  noCorridor: kinds(m.orthoDraws(g, fine, null)), wmsOnly: kinds(m.orthoDraws(wmsOnly, overview, null)),
  baseOnly: kinds(m.orthoDraws(s, overview, null)),
}}));""")
    assert found["fine"] == [["cache", "composed"], ["-", "composed"]]  # the corridor's tile, then the next one
    assert found["overview"] == [["-", "composed"], ["-", "composed"]]  # the overview's zoom: the service straight
    assert found["noCorridor"] == [["-", "composed"], ["-", "composed"]]  # a chunk without the line
    assert found["wmsOnly"] == [["-", "wms"], ["-", "wms"]]  # no base tiles: the WMS's JPEG
    assert found["baseOnly"] == [["-", "base"], ["-", "base"]]


# Synthetic tiles for the white test: a grey of 120 with white (255) rectangles [row, column, height, width],
# a fifth item drawing grey again
WHITE_CASES = {
    "none": [], "all": [[0, 0, 256, 256]], "block": [[8, 16, 8, 8]], "unaligned": [[3, 3, 9, 9]],
    "wide": [[4, 4, 16, 16]], "all but one": [[0, 0, 256, 256], [255, 255, 1, 1, "grey"]],
    "strip": [[0, 0, 256, 7]], "corner": [[248, 248, 8, 8]],
}


def _white_tile(rects) -> np.ndarray:
    tile = np.full((256, 256, 3), 120, np.uint8)
    for r, c, h, w, *grey in rects:
        tile[r:r + h, c:c + w] = 120 if grey else 255
    return tile


def test_white_blocks_match_python(tmp_path):
    """tiles.ts whiteBlocks on the decoded pixels says what orthophoto._white_blocks says of the same tile (a PNG
    here, lossless); the browser's tolerance takes a JPEG decoder's near-white for white."""
    expected = {}
    for name, rects in WHITE_CASES.items():
        out = io.BytesIO()
        Image.fromarray(_white_tile(rects)).save(out, "PNG")
        expected[name] = list(orthophoto._white_blocks(out.getvalue()))
    found = run_ts(tmp_path, "view3d/tiles", f"""
const tile = (rects, white = 255) => {{
  const px = new Uint8ClampedArray(256 * 256 * 4).fill(120);
  for (let k = 3; k < px.length; k += 4) px[k] = 255;
  for (const [r, c, h, w, grey] of rects) for (let i = r; i < r + h; i++) for (let j = c; j < c + w; j++)
    for (let ch = 0; ch < 3; ch++) px[4 * (i * 256 + j) + ch] = grey ? 120 : white;
  return px;
}};
const cases = {json.dumps(WHITE_CASES)}, out = {{}};
for (const [name, rects] of Object.entries(cases)) out[name] = m.whiteBlocks(tile(rects), 256, 256);
out.nearWhite = m.whiteBlocks(tile(cases.all, 251), 256, 256);
out.offWhite = m.whiteBlocks(tile(cases.all, 245), 256, 256);
console.log(JSON.stringify(out));""")
    assert expected == {"none": [False, False], "all": [True, True], "block": [False, True],
                        "unaligned": [False, False], "wide": [False, True], "all but one": [False, True],
                        "strip": [False, False], "corner": [False, True]}
    assert {k: found[k] for k in WHITE_CASES} == expected
    assert found["nearWhite"] == [True, True] and found["offWhite"] == [False, False]


def test_corridor_distance(tmp_path):
    found = run_ts(tmp_path, "view3d/tiles", """
const c = {a: [100, 100], b: [700, 100], half: 50};
console.log(JSON.stringify([m.tileDistance(c, 0, 0), m.tileDistance(c, 1, 0), m.tileDistance(c, 1, 1),
  m.tileDistance(c, 3, 0), m.tileDistance({a: [-10, -10], b: [600, 600], half: 1}, 1, 1),
  m.tileDistance({a: [-100, 300], b: [600, 300], half: 1}, 1, 0)]));""")
    assert found == [0, 0, pytest.approx(156), pytest.approx(math.hypot(68, 0)), 0, pytest.approx(44)]


def test_uvs_at_a_chunks_corners(tmp_path):
    b = chunk(0, 2)
    found = run_ts(tmp_path, "view3d/tiles", f"""
const A = {json.dumps(AFFINE)}, b = {json.dumps(b)}, p = m.planAt(A, b, 18), uv = m.uvOf(A, p);
console.log(JSON.stringify({{plan: p, corners: [[b.x0, b.y1], [b.x1, b.y1], [b.x0, b.y0], [b.x1, b.y0]].map(([x, y]) => uv(x, y)),
                             centre: uv((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)}}));""")
    plan, corners = found["plan"], found["corners"]
    for (u, v), (x, y) in zip(corners, [(b["x0"], b["y1"]), (b["x1"], b["y1"]), (b["x0"], b["y0"]), (b["x1"], b["y0"])]):
        px, py = world_pixel(AFFINE, x, y, 18)
        assert u == pytest.approx((px - plan["px0"]) / plan["width"], abs=1e-9)
        assert v == pytest.approx(1 - (py - plan["py0"]) / plan["height"], abs=1e-9)
        assert 0 <= u <= 1 and 0 <= v <= 1
    us, vs = [c[0] for c in corners], [c[1] for c in corners]
    assert min(us) < 1 / plan["width"] and max(us) > 1 - 1 / plan["width"]
    assert min(vs) < 1 / plan["height"] and max(vs) > 1 - 1 / plan["height"]
    nw, ne, sw, _ = corners
    assert ne[0] > nw[0] and nw[1] > sw[1]  # east is +u, north is +v (flipY)
    assert found["centre"] == pytest.approx([0.5, 0.5], abs=0.01)


def test_credits_html(tmp_path):
    credits = [{"data": "NMT", "attribution": "GUGiK <data>", "licence": "CC BY 4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/", "notice": ""},
               {"data": "x", "attribution": "Other", "licence": "Terms", "url": "javascript:alert(1)", "notice": ""}]
    found = run_ts(tmp_path, "view3d/credits", f"""
const g = {json.dumps(GEOPORTAL)};
console.log(JSON.stringify([m.dataCredits({json.dumps(credits)}, "2026 run/1"), m.dataCredits(null, "r"),
  m.dataCredits([], "r"), m.imageryCredits("ortho", g), m.imageryCredits("ortho", {{...g, attribution_url: undefined}}),
  m.imageryCredits("esri", null), m.imageryCredits("shaded", g)]));""")
    data, none, empty, ortho, plain, esri, shaded = found
    assert data.startswith("Data: GUGiK &#60;data&#62; (<a href=\"https://creativecommons.org/licenses/by/4.0/\" "
                           "target=\"_blank\" rel=\"noopener\">CC BY 4.0</a>) | Other (Terms). Find-a-Line's"
                           .replace("'", "&#39;"))
    assert data.endswith('<a href="/runs/2026%20run%2F1/ATTRIBUTION.txt" target="_blank">Notices</a>')
    assert "javascript:" not in data and none is None and empty is None
    assert ortho == '<a href="https://www.geoportal.gov.pl" target="_blank" rel="noopener">Orthophoto: GUGiK</a>'
    assert plain == "Orthophoto: GUGiK"
    assert esri == ('<a href="https://www.esri.com" target="_blank" rel="noopener">Powered by Esri</a> | '
                    "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community")
    assert shaded is None


# A fake page for imagery.ts (a chunk's UV read at its north-west corner within the patch): elements, images that load (or fail) a moment later, canvases that record their
# drawing, and a Scene3D of two chunks whose setTexture is recorded
FAKE_DOM = """
const loads = [];
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.hidden = false; this.className = "";
                     this.textContent = ""; this.draws = []; this.ops = []; }
  append(...c) { this.children.push(...c); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  remove() { this.removed = true; }
  // getImageData: the pixels global.PIXELS gives for the image drawn last, else a tainted canvas's error; ops: the
  // fills ([colour, x, y, w, h]) and images in their order
  getContext() { const self = this; return {fillRect(...a) { self.ops.push(["fill", self.fill, ...a]); }, clearRect() {},
                                            set fillStyle(v) { self.fill = v; },
                                            drawImage(img, ...a) { self.draws.push([img.src, ...a]);
                                                                   self.ops.push(["draw", img.src, ...a]); },
                                            getImageData(x, y, w, h) {
                                              if (!global.PIXELS) throw new Error("tainted");
                                              return {data: global.PIXELS(self.draws.at(-1)[0], w, h)}; }}; }
}
global.document = {createElement: (tag) => new El(tag)};
global.getComputedStyle = () => ({getPropertyValue: () => " #bba680 "});
global.location = {origin: "https://example.org"};
global.Image = class {
  set src(v) {
    this._src = v; if (!v) return;
    loads.push([v, this.crossOrigin]);
    // our cache has the tile the line crosses only; a service answers its first request without CORS
    const fails = v.includes("/wm256/") ? !v.includes("/19/") : !v.includes("_fal3d=");
    setTimeout(() => (fails ? this.onerror : this.onload)?.(), 1);
  }
  get src() { return this._src; }
};
const credits = {}, textures = [];
const chunks = [0, 1].map((k) => ({ci: 0, cj: k, hasLine: k === 0, bounds: BOUNDS[k],
  setTexture(tex, uv) { textures.push([k, tex ? [tex.image.width, tex.image.height, tex.image.draws.length] : null,
                                       uv ? uv(BOUNDS[k].x0, Math.min(BOUNDS[k].y1, META.top)).map((v) => Math.round(v * 1e6) / 1e6) : null]); }}));
const toolbar = new El("div");
const scene = {level: "full", meta: META, chunks, toolbar, invalidate() { scene.frames = (scene.frames || 0) + 1; },
  credits: {set(id, html, order) { credits[id] = [html, order]; }, remove(id) { delete credits[id]; }}};
"""


def test_imagery_on_a_fake_scene(tmp_path):
    ax, ay = CX - 100, CY + 50
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}],
            "ortho": {**GEOPORTAL, "cache": "../../cache/orthophoto/poland/wm256"},
            "attribution": [{"data": "NMT", "attribution": "GUGiK", "licence": "CC BY 4.0", "url": "", "notice": ""}]}
    bounds = [{"x0": ax - 60, "y0": ay - 60, "x1": ax + 140, "y1": ay + 60},   # the line's chunk, small
              {"x0": CX + 600, "y0": CY + 600, "x1": CX + 900, "y1": CY + 900}]  # mostly beyond the patch
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: "key"}});
  const seg = toolbar.children[0].children[0];
  const out = {{available: im.available, current: im.current, seg: seg.className, aria: seg.attrs["aria-label"],
               buttons: seg.children.map((b) => [b.textContent, b.className, b.attrs["aria-checked"]])}};
  await im.set("ortho");
  out.ortho = {{textures: textures.splice(0), credits: JSON.parse(JSON.stringify(credits)), loads: loads.splice(0)}};
  await im.set("esri");
  out.esri = {{textures: textures.splice(0), imagery: credits.imagery, loads: loads.splice(0).length,
              checked: seg.children.map((b) => b.attrs["aria-checked"])}};
  await im.set("shaded");
  out.shaded = {{textures: textures.splice(0), imagery: credits.imagery || null}};
  im.dispose();
  out.disposed = {{credits: Object.keys(credits), removed: !!toolbar.children[0].removed}};
  const bare = m.createImagery({{...scene, toolbar: new El("div"), meta: {{...META, ortho: null}}}}, {{runId: "r1", esriKey: null}});
  out.bare = {{available: bare.available}};
  console.log(JSON.stringify(out));
}})();""")
    assert found["available"] == ["ortho", "esri", "shaded"] and found["current"] == "ortho"
    assert found["seg"] == "u-seg" and found["aria"] == "Imagery"
    assert found["buttons"] == [["Orthophoto", "u-on", "true"], ["Satellite (Esri)", "", "false"],
                                ["Shaded", "", "false"]]
    ortho = found["ortho"]
    # every image is asked with CORS set before its address
    assert ortho["loads"] and all(cors == "anonymous" for _, cors in ortho["loads"])
    urls = [u for u, _ in ortho["loads"]]
    # the line's chunk at zoom 19: our cache (resolved from the run's map.html) for the tiles in the corridor
    assert any(u.startswith("/cache/orthophoto/poland/wm256/19/") for u in urls)
    # a service failing once is asked again past the browser's cache
    assert any("_fal3d=1" in u for u in urls)
    assert {k for k, _, _ in ortho["textures"]} == {0, 1}
    for k, (w, h, draws), uv in ortho["textures"]:
        assert w <= 2048 and h <= 2048 and draws > 0 and 0 <= uv[0] <= 1 and 0 <= uv[1] <= 1
    assert ortho["credits"]["data"][1] == 1 and ortho["credits"]["data"][0].startswith("Data: GUGiK (CC BY 4.0).")
    assert ortho["credits"]["imagery"] == ['<a href="https://www.geoportal.gov.pl" target="_blank" rel="noopener">'
                                           "Orthophoto: GUGiK</a>", 2]
    esri = found["esri"]
    assert esri["imagery"][0].startswith('<a href="https://www.esri.com"') and esri["loads"] > 0
    assert esri["checked"] == ["false", "true", "false"] and len(esri["textures"]) == 2
    assert found["shaded"] == {"textures": [[0, None, None], [1, None, None]], "imagery": None}
    assert found["disposed"] == {"credits": [], "removed": True}
    assert found["bare"]["available"] == ["shaded"]


def test_imagery_composes_as_the_cache(tmp_path):
    """A tile of the WMS over base tiles as orthophoto.tile_content composes it: the JPEG first; all white → the
    base; a white block → the base with the PNG over it; else the JPEG alone; pixels that cannot be read → the base
    with the PNG."""
    ax, ay = CX - 100, CY + 50
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}],
            "ortho": {**GEOPORTAL, "cache": None}, "attribution": None}
    bounds = [{"x0": ax - 60, "y0": ay - 60, "x1": ax + 140, "y1": ay + 60},
              {"x0": CX - 700, "y0": CY - 700, "x1": CX - 300, "y1": CY - 300}]
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
// The WMS's JPEGs in the order first asked: all white, partly white (one 8x8 block), imagery throughout, ...
const kinds = new Map(), KINDS = ["white", "partly", "full"];
const plain = (src) => src.replace(/[?&]_fal3d=\\d+$/, "");
global.PIXELS = (src, w, h) => {{
  const key = plain(src);
  if (!kinds.has(key)) kinds.set(key, KINDS[kinds.size % 3]);
  const kind = kinds.get(key), px = new Uint8ClampedArray(w * h * 4).fill(kind === "white" ? 255 : 90);
  if (kind === "partly") for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) px.fill(253, 4 * (i * w + j), 4 * (i * w + j) + 4);
  return px;
}};
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: null}});
  await im.set("ortho");
  const asked = loads.splice(0).map(([u]) => u).filter((u) => u.includes("_fal3d=1"));  // each tile's second ask
  const jpegs = asked.filter((u) => u.includes("image%2Fjpeg")), pngs = asked.filter((u) => u.includes("image%2Fpng"));
  const bases = asked.filter((u) => u.includes("SERVICE=WMTS"));
  const count = (k) => [...kinds.values()].filter((v) => v === k).length;
  const out = {{jpegs: jpegs.length, pngs: pngs.length, bases: bases.length, white: count("white"),
               partly: count("partly"), full: count("full"), textures: textures.length}};
  im.dispose();
  global.PIXELS = undefined;  // a tainted canvas: every tile the base with the PNG over it
  textures.splice(0);
  const im2 = m.createImagery({{...scene, toolbar: new El("div")}}, {{runId: "r1", esriKey: null}});
  await im2.set("ortho");
  const again = loads.splice(0).map(([u]) => u).filter((u) => u.includes("_fal3d=1"));
  out.tainted = {{jpegs: again.filter((u) => u.includes("image%2Fjpeg")).length,
                 pngs: again.filter((u) => u.includes("image%2Fpng")).length,
                 bases: again.filter((u) => u.includes("SERVICE=WMTS")).length}};
  console.log(JSON.stringify(out));
}})();""")
    assert found["jpegs"] > 3 and found["jpegs"] == found["white"] + found["partly"] + found["full"]
    assert found["bases"] == found["white"] + found["partly"] and found["pngs"] == found["partly"]
    assert found["textures"] == 2
    tainted = found["tainted"]
    assert tainted["jpegs"] == found["jpegs"] and tainted["pngs"] == tainted["bases"] == found["jpegs"]


def test_wms_tiles_drawn_over_white(tmp_path):
    """A WMS without base tiles in another version and CRS (Iceland's gis.natt.is: 1.1.1 in Web Mercator, answering
    PNG for JPEG) is asked so, and each of its tiles is drawn over white as our cache lays it (orthophoto._on_white),
    not over the shaded terrain's colour a failed tile leaves."""
    ax, ay = CX - 100, CY + 50
    iceland = {**GEOPORTAL, "base": None, "cache": None, "wms_version": "1.1.1", "wms_crs": "EPSG:3857"}
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}], "ortho": iceland,
            "attribution": None}
    bounds = [{"x0": ax - 60, "y0": ay - 60, "x1": ax + 140, "y1": ay + 60},
              {"x0": CX - 700, "y0": CY - 700, "x1": CX - 300, "y1": CY - 300}]
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
const canvases = [], create = document.createElement;
document.createElement = (tag) => {{ const e = create(tag); if (tag === "canvas") canvases.push(e); return e; }};
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: null}});
  await im.set("ortho");
  console.log(JSON.stringify({{urls: loads.splice(0).map(([u]) => u),
                              ops: canvases.filter((c) => c.ops.length).map((c) => c.ops)}}));
}})();""")
    assert found["urls"] and all("version=1.1.1" in u and "srs=EPSG%3A3857" in u for u in found["urls"])
    # the default imagery's canvases, stopped by set() after their first fill, then one canvas per chunk
    assert all(ops[0][:2] == ["fill", "#bba680"] for ops in found["ops"])
    drawn = [ops for ops in found["ops"] if any(op[0] == "draw" for op in ops)]
    assert len(drawn) == 2
    for ops in drawn:
        draws = [k for k, op in enumerate(ops) if op[0] == "draw"]
        assert all(ops[k - 1] == ["fill", "#ffffff", *ops[k][2:4], 256, 256] for k in draws)


def test_no_imagery_note(tmp_path):
    meta = {"left": 0, "top": 513, "width": 513, "height": 513, "res": 1, "affine": EQUATOR,
            "anchors": [{"x": 100, "y": 100, "h": 1}, {"x": 200, "y": 100, "h": 1}], "ortho": None, "attribution": None}
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = [{{x0: 0, y0: 0, x1: 513, y1: 513}}, {{x0: 0, y0: 0, x1: 513, y1: 513}}];
{FAKE_DOM}
const im = m.createImagery(scene, {{runId: "r", esriKey: null}});
const row = toolbar.children[0];
console.log(JSON.stringify({{available: im.available, texts: row.children.map((c) => [c.className, c.textContent, c.hidden]),
                            credits: Object.keys(credits)}}));""")
    assert found["available"] == ["shaded"]
    assert found["texts"] == [["u-small v3-imagery-note", "No imagery for this result: the terrain is shaded.", False],
                              ["u-small v3-imagery-status", "Loading the imagery…", True]]
    assert found["credits"] == []
