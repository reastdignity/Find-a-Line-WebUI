"""The coarse ring of terrain around the 3D view's patch (docs/3d-view-contract.md, "Wave 3", V3b;
viewer/src/view3d/ring.ts, ringmath.ts): in Node the frame from the tiles' Earth-centred coordinates into the
scene's, the cut-out, the overlays per imagery, the tiles per open; in headless Edge the page of test_view3d with
the meta findaline-3d-ring set to a same-origin template of Terrarium tiles made here from the Ĺ»abi KoĹ„ clip
(never Mapterhorn's), the ring drawn, its bytes within the budget, its heights against the patch's at the edge,
no violation of the Content-Security-Policy. The Edge test runs from PowerShell (headless Edge prints nothing
from Git Bash)."""

import json
import math
import os
import re
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import CLIP_LEFT, CLIP_TOP, TIF, _offline_env, clip_data  # noqa: E402,F401 (the fixture)
from test_view3d import EDGE_SECONDS, READY_SCRIPT, VIRTUAL_BUDGET, _page, _with_until  # noqa: E402,F401
from test_viewer import pytestmark, run_ts  # noqa: E402,F401 (the skip without Node)
from test_web import EDGE, _lines_of, _server, _violations  # noqa: E402

# Grid metres of EPSG:2180 around Ĺ»abi KoĹ„ and the patch's origin height
CX, CY, H0 = 553966.0, 254608.0, 1400.0
# The ring's tiles per open (docs/3d-view-contract.md, "Budgets"): about 1.5 MB on the desktop, 0.6 MB on phones
BUDGET = {"full": 1.5e6, "phone": 0.6e6}


def _affine(cx=CX, cy=CY, side=1537.0):
    """The meta's affine as search.patch_of_line fits it: least squares over a 5 Ă— 5 lattice of the patch."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    xs, ys = np.meshgrid(np.linspace(cx - side / 2, cx + side / 2, 5), np.linspace(cy - side / 2, cy + side / 2, 5))
    lon, lat = t.transform(xs.ravel(), ys.ravel())
    m = np.column_stack([np.ones(xs.size), xs.ravel(), ys.ravel()])
    a = np.linalg.lstsq(m, lon, rcond=None)[0]
    b = np.linalg.lstsq(m, lat, rcond=None)[0]
    return [*map(float, a), *map(float, b)]


def test_frame_places_the_tiles_in_the_scene(tmp_path):
    """Points at their true lon/lat (pyproj) and height, through the plugin's Earth-centred frame and ringFrame,
    land where the scene puts the patch's grid metres: centimetres at the patch's edge, metres at 6 km (the
    affine's derivative at the centre, the Earth's curvature below the plane)."""
    from pyproj import Transformer
    affine = _affine()
    t = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    geocentric = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    points = [(dx, dy, h) for dx, dy in [(0, 0), (768, 0), (0, -768), (-768, 768), (6000, 0), (0, 6000),
                                         (-4243, -4243)] for h in (H0, H0 + 300)]
    lonlat = [t.transform(CX + dx, CY + dy) for dx, dy, _ in points]
    found = run_ts(tmp_path, "view3d/ringmath", f"""
const F = m.ringFrame({{affine: {json.dumps(affine)}}}, {{cx: {CX}, cy: {CY}, h0: {H0}}});
const pts = {json.dumps([[lo, la, h] for (lo, la), (_, _, h) in zip(lonlat, points)])};
console.log(JSON.stringify({{F, ecef: pts.map(([lo, la, h]) => m.ecef(lo, la, h)),
  scene: pts.map(([lo, la, h]) => {{ const p = m.ecef(lo, la, h);
    return [0, 1, 2].map((r) => F[4 * r] * p[0] + F[4 * r + 1] * p[1] + F[4 * r + 2] * p[2] + F[4 * r + 3]); }})}}));""")
    for (lo, la), (_, _, h), e in zip(lonlat, points, found["ecef"]):
        assert e == pytest.approx(geocentric.transform(lo, la, h), abs=1e-3)
    for (dx, dy, h), s in zip(points, found["scene"]):
        d = math.hypot(dx, dy)
        drop = d * d / (2 * 6.38e6)
        horizontal = math.hypot(s[0] - dx, s[2] + dy)
        if d < 1100:
            assert horizontal < 0.1 and abs(s[1] - (h - H0)) < 0.1, (dx, dy, s)
        else:
            assert horizontal < 3 and abs(s[1] - (h - H0) + drop) < 0.3, (dx, dy, s)


def test_cut_out_and_data_rectangle(tmp_path):
    found = run_ts(tmp_path, "view3d/ringmath", """
const cols = 6, heights = new Float32Array(cols * 5).fill(NaN);
for (let i = 1; i < 4; i++) for (let j = 2; j < 5; j++) heights[i * cols + j] = 100;
const patch = {meta: {left: 1000, top: 2000, res: 2, width: 6, height: 5}, heights, cols};
const r = m.dataRect(patch), origin = {cx: 1006, cy: 1995, h0: 0};
const planes = m.cutPlanes(r, origin);
const scene = (x, y, h) => [x - origin.cx, h, -(y - origin.cy)];
console.log(JSON.stringify({r, empty: m.dataRect({...patch, heights: new Float32Array(30).fill(NaN)}),
  inside: m.isCut(planes, scene(1007, 1995, 50)), corner: m.isCut(planes, scene(1004.01, 1993.99, -9)),
  west: m.isCut(planes, scene(1003.9, 1995, 0)), north: m.isCut(planes, scene(1007, 1998.1, 0)),
  far: m.isCut(planes, scene(5000, 5000, 0)), edge: m.edgeSamples(patch, 1).length,
  stats: m.offsetStats([1, -2, 3, -4, 5, 0.5, -0.25, 7, 8, 9]), none: m.offsetStats([])}));""")
    assert found["r"] == {"x0": 1004, "x1": 1010, "y0": 1992, "y1": 1998}
    assert found["empty"] is None
    assert found["inside"] and found["corner"]
    assert not found["west"] and not found["north"] and not found["far"]
    assert found["edge"] == 8  # the rim of a 3 Ă— 3 block
    assert found["stats"] == {"median": 4, "p90": 8} and found["none"] is None


def test_overlays_per_imagery(tmp_path):
    ortho = {"name": "Geoportal", "url": "https://example.org/wms", "layer": "Raster", "attribution": "GUGiK",
             "base": {"url": "https://example.org/base/{z}/{x}/{y}", "max_zoom": 18}, "cache": None}
    found = run_ts(tmp_path, "view3d/ringmath", f"""
const ortho = {json.dumps(ortho)};
console.log(JSON.stringify({{esri: m.overlaySpecs("esri", ortho, "KEY"), nokey: m.overlaySpecs("esri", ortho, null),
  both: m.overlaySpecs("ortho", ortho, "KEY"), wms: m.overlaySpecs("ortho", {{...ortho, base: null}}, null),
  base: m.overlaySpecs("ortho", {{...ortho, url: null}}, null), shaded: m.overlaySpecs("shaded", ortho, "KEY"),
  edges: m.overlaySpecs("edges", ortho, "KEY"),
  iceland: m.overlaySpecs("ortho", {{...ortho, base: null, wms_version: "1.1.1", wms_crs: "EPSG:3857"}}, null),
  none: m.overlaySpecs("ortho", null, null)}}));""")
    assert found["esri"] == [{"type": "xyz", "levels": 20, "url": "https://ibasemaps-api.arcgis.com/arcgis/rest/"
                              "services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=KEY"}]
    assert found["nokey"] == [] and found["shaded"] == [] and found["none"] == [] and found["edges"] == []
    assert found["both"] == [{"type": "xyz", "url": "https://example.org/base/{z}/{x}/{y}", "levels": 19},
                             {"type": "wms", "url": "https://example.org/wms", "layer": "Raster",
                              "format": "image/png", "transparent": True, "version": "1.3.0", "crs": "EPSG:4326"}]
    assert found["wms"] == [{"type": "wms", "url": "https://example.org/wms", "layer": "Raster",
                             "format": "image/jpeg", "transparent": False, "version": "1.3.0", "crs": "EPSG:4326"}]
    # a WMS of another version and CRS (batch 3's Iceland) as the 2D map asks it (orthophoto._get_map)
    assert found["iceland"] == [{"type": "wms", "url": "https://example.org/wms", "layer": "Raster",
                                 "format": "image/jpeg", "transparent": False, "version": "1.1.1",
                                 "crs": "EPSG:3857"}]
    assert found["base"] == [{"type": "xyz", "url": "https://example.org/base/{z}/{x}/{y}", "levels": 19}]


def test_levels_and_tiles_per_open(tmp_path):
    """The mesh refined by the distance only, and the elevation tiles an open reads at 50Â° N: a 6 km disc at
    zoom 12 (6.3 km tiles) on the desktop, 3 km at zoom 10 on phones."""
    found = run_ts(tmp_path, "view3d/ringmath", """
const px = (z, lat) => 40075016.686 * Math.cos(lat * Math.PI / 180) / 2 ** z / 512;  // a tile pixel, metres
const out = {};
for (const level of ["full", "phone"]) {
  const L = m.RING[level];
  out[level] = {zoom: L.zoom, radius: L.radius,
    deepest: [0, 1000, 3000, 5000].map((d) => { let z = 0; while (z < m.MESH_ZOOM && m.refines(L, px(z, 50), d)) z++; return z; }),
    tiles: [[19.7563, 50.1560], [19.0, 49.99], [7.5, 46.5]].map(([lo, la]) => m.tilesWithin(lo, la, L.radius, L.zoom).length)};
}
console.log(JSON.stringify(out));""")
    assert found["full"]["zoom"] == 12 and found["full"]["radius"] == 6000
    assert found["full"]["deepest"] == [15, 15, 14, 13]
    assert found["phone"]["deepest"] == [14, 14, 13, 13]
    assert all(n <= 9 for n in found["full"]["tiles"]) and all(n <= 4 for n in found["phone"]["tiles"])
    print(found)


# The Terrarium tiles of the test: the clip's heights (bilinear), outside it its nearest edge, as PNG
def _terrarium_tiles(folder, lon, lat, radius, z):
    from PIL import Image
    from pyproj import Transformer
    import rasterio as rio
    with rio.open(TIF) as src:
        clip = src.read(1).astype(np.float64)
    t = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    n = 2 ** z
    d_lat, d_lon = radius / 111320, radius / (111320 * math.cos(math.radians(lat)))
    tx = lambda lo: math.floor((lo + 180) / 360 * n)  # noqa: E731
    ty = lambda la: math.floor((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n)  # noqa: E731
    count = 0
    for y in range(ty(lat + d_lat), ty(lat - d_lat) + 1):
        for x in range(tx(lon - d_lon), tx(lon + d_lon) + 1):
            u = (x + (np.arange(512) + 0.5) / 512) / n
            v = (y + (np.arange(512) + 0.5) / 512) / n
            lons = u * 360 - 180
            lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * v))))
            glon, glat = np.meshgrid(lons, lats)
            gx, gy = t.transform(glon, glat)
            c = np.clip(gx - CLIP_LEFT - 0.5, 0, clip.shape[1] - 1.001)
            r = np.clip(CLIP_TOP - gy - 0.5, 0, clip.shape[0] - 1.001)
            j, i = np.floor(c).astype(int), np.floor(r).astype(int)
            a, b = c - j, r - i
            h = ((clip[i, j] * (1 - a) + clip[i, j + 1] * a) * (1 - b)
                 + (clip[i + 1, j] * (1 - a) + clip[i + 1, j + 1] * a) * b)
            value = h + 32768
            rgb = np.stack([np.floor(value / 256), np.floor(value) % 256, np.floor((value % 1) * 256)], -1)
            path = folder / str(z) / str(x)
            path.mkdir(parents=True, exist_ok=True)
            Image.fromarray(rgb.astype(np.uint8), "RGB").save(path / f"{y}.png")
            count += 1
    return count


def _imagery_tiles(folder, lon, lat, radius, zooms):
    """Plain imagery tiles (the orthophoto's base tiles of the stubbed meta) for the ring's overlay."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (90, 140, 70)).save(buf, "PNG")
    data = buf.getvalue()
    for z in zooms:
        n = 2 ** z
        d_lat, d_lon = radius / 111320, radius / (111320 * math.cos(math.radians(lat)))
        tx = lambda lo: math.floor((lo + 180) / 360 * n)  # noqa: E731
        ty = lambda la: math.floor((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n)  # noqa: E731
        for y in range(ty(lat + d_lat), ty(lat - d_lat) + 1):
            for x in range(tx(lon - d_lon), tx(lon + d_lon) + 1):
                path = folder / str(z) / str(x)
                path.mkdir(parents=True, exist_ok=True)
                (path / f"{y}.png").write_bytes(data)


# Before the bundle: the patch's answer (an XMLHttpRequest's response: viewer/src/download.ts) with an orthophoto of
# plain base tiles of the test (same origin), so the ring's overlay is drawn too; its body (and so its sha256) stays
# as it came
ORTHO_STUB = """
(function () {
  const open = XMLHttpRequest.prototype.open;
  const response = Object.getOwnPropertyDescriptor(XMLHttpRequest.prototype, "response");
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.falUrl = String(url);
    return open.call(this, method, url, ...rest);
  };
  const withOrtho = (buf) => {
    const n = new DataView(buf).getUint32(0, true);
    const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
    meta.ortho = {name: "Test", url: null, layer: "", attribution: "Test imagery", cache: null,
                  base: {url: "/runs/view3dtest/img/{z}/{x}/{y}.png", max_zoom: 15}};
    const head = new TextEncoder().encode(JSON.stringify(meta)), body = new Uint8Array(buf, 4 + n);
    const out = new Uint8Array(4 + head.length + body.length);
    new DataView(out.buffer).setUint32(0, head.length, true);
    out.set(head, 4);
    out.set(body, 4 + head.length);
    return out.buffer;
  };
  Object.defineProperty(XMLHttpRequest.prototype, "response", {configurable: true, get() {
    const buf = response.get.call(this);
    if (!this.falUrl?.startsWith("/api/patch") || this.readyState !== 4 || this.status !== 200 ||
        !(buf instanceof ArrayBuffer)) return buf;
    if (!this.falPatched) this.falPatched = withOrtho(buf);
    return this.falPatched;
  }});
})();
"""

# After the bundle: waits for the ring (data-ring="loaded"), then writes what it found into <pre id="ring">; with
# window.FINDALINE_RING_EDGES (edges.js) it first chooses the "Edges" look and counts the imagery's requests
# before and after it
RING_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  let look = null;
  // The ring's and the imagery's requests, by an observer: the page's buffer of resource entries holds 250, which
  // the polls of UNTIL_JS may fill before the ring loads (takeRecords: those not yet handed to the observer)
  const seen = [];
  const take = (entries) => { for (const e of entries) if (/\\/runs\\/view3dtest\\/(ring|img)\\//.test(e.name)) seen.push(e); };
  const observer = new PerformanceObserver((list) => take(list.getEntries()));
  observer.observe({type: "resource", buffered: true});
  const requests = () => { take(observer.takeRecords()); return seen; };
  const images = () => requests().filter((e) => /\\/runs\\/view3dtest\\/img\\//.test(e.name)).length;
  const done = (what) => {
    const out = document.createElement("pre");
    out.id = "ring";
    out.textContent = JSON.stringify(what);
    document.body.appendChild(out);
  };
  // The ring's tiles are asked for from animation frames (3d-tiles-renderer's queue): behind plain timers no tile
  // was asked for in most runs. The polls over the browser's frames of test_view3d.UNTIL_JS (their small file is
  // not under ring/ or img/, so not among the entries counted).
  /* until */
  const loaded = () => root.dataset.ring === "loaded" && root.dataset.ready === "1";
  const pause = (ms, then) => until(() => false, ms, () => then());
  const record = () => {
    if (look) Object.assign(look, {after: images(), imagery: root.dataset.imagery || null, edges: root.dataset.edges || null});
    const entries = requests()
      .map((e) => ({url: e.name.replace(/^.*\\/view3dtest\\//, ""), bytes: e.encodedBodySize, transfer: e.transferSize}));
    done({ring: root.dataset.ring, offset: root.dataset.ringOffset ? JSON.parse(root.dataset.ringOffset) : null,
          errors: Number(root.dataset.ringErrors || 0), visible: Number(root.dataset.ringTiles || 0), entries, triangles: Number(root.dataset.triangles),
          credits: (document.querySelector(".v3-credits") || document.body).innerHTML, look});
  };
  const timeout = () => done({ring: root.dataset.ring || null, timeout: true, data: {...root.dataset}});
  until(loaded, 50000, (ok) => {
    if (!ok) { timeout(); return; }
    if (!window.FINDALINE_RING_EDGES) { pause(2000, record); return; }
    const edges = [...document.querySelectorAll(".v3-toolbar [role=radio]")].find((b) => b.textContent.trim() === "Edges");
    look = {before: images(), found: !!edges};
    if (edges) edges.click();
    pause(2500, () => until(loaded, 50000, (again) => again ? pause(2000, record) : timeout()));
  });
})();
""")


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level,look", [("full", None), ("phone", None), ("full", "edges")])
def test_ring_drawn_within_its_budget(clip_data, tmp_path, monkeypatch, level, look):
    """The ring drawn within its budget; once with the "Edges" look chosen after it loaded (docs/3d-view-contract.md,
    "Wave E": its tiles on the terrain's layer, on paper, without an overlay: no more imagery requested)."""
    from pyproj import Transformer
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _page(data, meta["id"])
    folder = data / "runs" / "view3dtest"
    lon, lat = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform(CX, CY)
    zoom, radius = {"full": (12, 6000), "phone": (10, 3000)}[level]
    made = _terrarium_tiles(folder / "ring", lon, lat, radius + 7000, zoom)
    _imagery_tiles(folder / "img", lon, lat, radius + 2000, range(10, 16))
    (folder / "ortho.js").write_text(ORTHO_STUB, encoding="utf-8")
    (folder / "ring.js").write_text(RING_SCRIPT, encoding="utf-8")
    (folder / "edges.js").write_text("window.FINDALINE_RING_EDGES = true;" if look == "edges" else "", encoding="utf-8")
    html = (folder / "index.html").read_text("utf-8")
    template = "/runs/view3dtest/ring/{z}/{x}/{y}.png"
    html = re.sub(r'(<meta name="findaline-3d-ring" content=")[^"]*(")', lambda m: m.group(1) + template + m.group(2),
                  html)
    html = html.replace('<script src="/app/view3d.js"></script>',
                        '<script src="ortho.js"></script><script src="/app/view3d.js"></script>')
    html = html.replace('<script src="test.js"></script>',
                        '<script src="test.js"></script><script src="edges.js"></script><script src="ring.js"></script>')
    assert template in html and "ring.js" in html
    (folder / "index.html").write_text(html, encoding="utf-8")
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="ring">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<")
                        .replace("&gt;", ">"))
    terrain = [e for e in result.get("entries", []) if e["url"].startswith("ring/")]
    imagery = [e for e in result.get("entries", []) if e["url"].startswith("img/")]
    total = sum(e["bytes"] for e in terrain + imagery)
    print(level, {k: v for k, v in result.items() if k != "entries"}, "tiles made", made,
          "terrain", len(terrain), sum(e["bytes"] for e in terrain), "imagery", len(imagery),
          sum(e["bytes"] for e in imagery))
    assert result["ring"] == "loaded", result
    assert result["errors"] == 0 and result["visible"] > 0
    # only the elevation tiles of the level's zoom, within the disc
    assert terrain and all(e["url"].startswith(f"ring/{zoom}/") for e in terrain), terrain
    assert len(terrain) <= (9 if level == "full" else 4)
    assert imagery, "the ring's overlay"
    assert total <= BUDGET[level], total
    assert "mapterhorn.com/attribution" in result["credits"]
    off = result["offset"]
    assert off and off["samples"] > 20 and off["median"] < 5, off
    assert _violations(dom) == []
    if look == "edges":
        seen = result["look"]
        assert seen["found"] and seen["imagery"] == "edges" and seen["edges"] == "on", seen
        assert seen["after"] == seen["before"], seen  # no overlay: no imagery asked for after the switch
    shot = os.environ.get("FINDALINE_RING_SHOT")  # a look by hand: the folder for a screenshot of each level
    if shot:  # shaded (no orthophoto), as Mapterhorn's tiles would look without imagery
        (folder / "shaded.html").write_text(html.replace('<script src="ortho.js"></script>', ""), encoding="utf-8")
        with _server(data, start_scheduler=True) as port:
            subprocess.run([EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge2'}",
                            "--no-first-run", "--window-size=1200,800", "--virtual-time-budget=60000",
                            f"--screenshot={os.path.join(shot, level + '.png')}",
                            f"http://127.0.0.1:{port}/runs/view3dtest/shaded.html?level={level}#run={meta['id']}&line={line}"],
                           capture_output=True, timeout=300)
