"""The trees and buildings of the 3D view (viewer/src/view3d/canopymesh.ts and canopy.ts; docs/3d-view-contract.md,
"Round 2": "The block of trees and buildings" and "V, the canopy"): the answer of /api/patch?part=canopy encoded here
by the contract's rules and decoded by the page's code in Node, the lattice of cells and the mesh against a Python
reckoning of the same grids, the budget; in headless Edge the tool on a real scene (no tool without `surface` in the
meta; switched on it asks the block once and draws the mesh, off hides it and on again asks nothing; a failure shows
its note and the switch goes off; no violation of the Content-Security-Policy). Run the Edge test from PowerShell
(headless Edge prints nothing from Git Bash)."""

import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import zlib

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_viewer import VIEWER, pytestmark, run_ts  # noqa: E402,F401 (the skip without Node)
from test_web import CSP_STUB, EDGE, LOCAL, TOKEN, _server, _violations, web  # noqa: E402

QUANTUM, MIN_HEIGHT = 0.5, 1.0


def encode(values: np.ndarray, **extra) -> bytes:
    """An answer of /api/patch?part=canopy as the contract frames it: uint32 LE N, the meta, the deflated values."""
    height, width = values.shape
    body = zlib.compress(values.astype(np.uint8).tobytes())
    meta = {"part": "canopy", "width": width, "height": height, "step": 1, "res": 1.0, "left": 1000.0,
            "top": 2000.0, "quantum": QUANTUM, "min_height": MIN_HEIGHT, "rule": None, "cells": int((values > 0).sum()),
            "sha256": hashlib.sha256(body).hexdigest()}
    meta.update(extra)
    raw = json.dumps(meta).encode()
    return struct.pack("<I", len(raw)) + raw + body


def js_bytes(data: bytes) -> str:
    return "new Uint8Array(%s).buffer" % json.dumps(list(data))


def test_decode_the_answer(tmp_path):
    rng = np.random.default_rng(3)
    values = (rng.integers(0, 3, (7, 9)) * rng.integers(0, 40, (7, 9))).astype(np.uint8)
    good = encode(values)
    wrong_sum = encode(values, sha256="0" * 64)
    wrong_length = encode(values, width=10)
    wrong_part = encode(values, part="patch")
    found = run_ts(tmp_path, "view3d/canopymesh", f"""
(async () => {{
  const out = {{}};
  const ok = await m.decodeCanopy({js_bytes(good)});
  out.values = Array.from(ok.values);
  out.meta = ok.meta;
  const cases = {{sum: {js_bytes(wrong_sum)}, length: {js_bytes(wrong_length)}, part: {js_bytes(wrong_part)},
                 cut: {js_bytes(good[:20])}, tiny: new Uint8Array([1, 2]).buffer}};
  out.errors = {{}};
  for (const [name, answer] of Object.entries(cases)) {{
    try {{ await m.decodeCanopy(answer); out.errors[name] = null; }}
    catch (e) {{ out.errors[name] = [e instanceof m.CanopyError, String(e.message)]; }}
  }}
  out.unchecked = (await m.decodeCanopy({js_bytes(wrong_sum)}, async () => null)).values.length;
  console.log(JSON.stringify(out));
}})();""")
    assert found["values"] == values.ravel().tolist()
    assert found["meta"]["part"] == "canopy" and found["meta"]["quantum"] == QUANTUM
    for name in ("sum", "length", "part", "cut", "tiny"):
        assert found["errors"][name][0] is True, (name, found["errors"][name])
    assert "checksum" in found["errors"]["sum"][1] and "expected 70 values, got 63" in found["errors"]["length"][1]
    assert found["unchecked"] == values.size  # where crypto.subtle is missing the checksum is left unchecked


def pool(values: np.ndarray, k: int, minimum: int) -> np.ndarray:
    """The largest value of each cell of k × k samples (edge cells smaller), 0 below the minimum."""
    h, w = values.shape
    ny, nx = math.ceil(h / k), math.ceil(w / k)
    cells = np.zeros((ny, nx), dtype=np.uint8)
    for r in range(ny):
        for c in range(nx):
            cells[r, c] = values[r * k:(r + 1) * k, c * k:(c + 1) * k].max()
    cells[cells < minimum] = 0
    return cells


def counts(cells: np.ndarray) -> dict:
    """Cells drawn, their corners and the sides next to no cell drawn."""
    ny, nx = cells.shape
    drawn = cells > 0
    corners = set()
    edges = 0
    for r in range(ny):
        for c in range(nx):
            if not drawn[r, c]:
                continue
            corners.update({(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)})
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                edges += not (0 <= rr < ny and 0 <= cc < nx and drawn[rr, cc])
    return {"drawn": int(drawn.sum()), "corners": len(corners), "edges": edges,
            "vertices": len(corners) + 4 * edges, "triangles": 2 * int(drawn.sum()) + 2 * edges}


def wood_grid() -> np.ndarray:
    """9 × 7 samples: a wood, a lone tree, a one-sample speck below the minimum, a strip along the edge."""
    v = np.zeros((7, 9), dtype=np.uint8)
    v[1:5, 1:6] = 30            # a wood of 15 m
    v[2, 3] = 44                # a taller crown inside it
    v[6, 8] = 12                # a lone tree in the corner cell (6 m), the last row and column
    v[0, 7] = 1                 # below the minimum height (0.5 m): no cell
    v[5:7, 0] = 6               # a strip of bushes at the edge
    return v


MINIMUM = math.ceil(MIN_HEIGHT / QUANTUM)


@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_lattice_cells_and_counts(tmp_path, k):
    values = wood_grid()
    expected = pool(values, k, MINIMUM)
    found = run_ts(tmp_path, "view3d/canopymesh", f"""
const v = Uint8Array.from({json.dumps(values.ravel().tolist())});
const l = m.lattice(v, 9, 7, {k}, {MINIMUM});
console.log(JSON.stringify({{k: l.k, nx: l.nx, ny: l.ny, cells: Array.from(l.cells), drawn: l.drawn, corners: l.corners,
  edges: l.edges, vertices: l.vertices, triangles: l.triangles}}));""")
    assert (found["nx"], found["ny"], found["k"]) == (expected.shape[1], expected.shape[0], k)
    assert found["cells"] == expected.ravel().tolist()
    want = counts(expected)
    assert {key: found[key] for key in want} == want, (found, want)
    if k == 2:
        assert want["drawn"] > 4 and 0 < expected[3, 4] and expected[0, 3] == 0  # the speck is not a cell


def test_one_cell_and_the_minimum(tmp_path):
    values = np.zeros((6, 6), dtype=np.uint8)
    values[3, 3] = 2   # exactly the minimum (1 m): drawn
    values[0, 0] = 1   # below it: not
    found = run_ts(tmp_path, "view3d/canopymesh", f"""
const v = Uint8Array.from({json.dumps(values.ravel().tolist())});
const l = m.lattice(v, 6, 6, 2, m.minValue({{min_height: 1, quantum: 0.5}}));
console.log(JSON.stringify({{min: m.minValue({{min_height: 1, quantum: 0.5}}), min2: m.minValue({{min_height: 1.2, quantum: 0.5}}),
  cells: Array.from(l.cells), drawn: l.drawn, corners: l.corners, edges: l.edges, vertices: l.vertices, triangles: l.triangles}}));""")
    assert found["min"] == 2 and found["min2"] == 3
    assert found["drawn"] == 1 and found["cells"] == [0, 0, 0, 0, 2, 0, 0, 0, 0]
    # a single cell: four corners, four sides of four vertices, two triangles for the top and two a side
    assert (found["corners"], found["edges"], found["vertices"], found["triangles"]) == (4, 4, 20, 10)


PRELUDE = """
const ground = (w, h, f, res = 1, left = 1000, top = 2000, cols = w + 3) => {
  const heights = new Float32Array(cols * h).fill(NaN);
  for (let i = 0; i < h; i++) for (let j = 0; j < w; j++) { const z = f(i, j); heights[i * cols + j] = z === null ? NaN : z; }
  return {width: w, height: h, res, left, top, heights, cols};
};
const originOf = (g, h0 = 90) => ({cx: g.left + g.width * g.res / 2, cy: g.top - g.height * g.res / 2, h0});
const faces = (mesh) => {  // geometric normal of each triangle against the stored normals of its vertices
  const out = [];
  for (let t = 0; t < mesh.triangles; t++) {
    const [a, b, c] = [0, 1, 2].map((s) => mesh.indices[3 * t + s]);
    const p = (v) => [mesh.positions[3 * v], mesh.positions[3 * v + 1], mesh.positions[3 * v + 2]];
    const [pa, pb, pc] = [p(a), p(b), p(c)];
    const u = pb.map((x, i) => x - pa[i]), w = pc.map((x, i) => x - pa[i]);
    const n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
    const len = Math.hypot(...n) || 1;
    const stored = [0, 1, 2].map((i) => (mesh.normals[3 * a + i] + mesh.normals[3 * b + i] + mesh.normals[3 * c + i]) / 3);
    out.push({n: n.map((x) => x / len), dot: n.reduce((s, x, i) => s + x * stored[i], 0) / len});
  }
  return out;
};
"""


def test_mesh_of_a_wood_on_flat_ground(tmp_path):
    values = np.zeros((8, 8), dtype=np.uint8)
    values[2:6, 2:6] = 8   # 4 m, 2 × 2 cells of 2 × 2 samples
    sink = 0.35
    found = run_ts(tmp_path, "view3d/canopymesh", PRELUDE + f"""
const v = Uint8Array.from({json.dumps(values.ravel().tolist())});
const g = ground(8, 8, () => 100);
const lat = m.lattice(v, 8, 8, 2, 2);
const mesh = m.buildMesh(g, lat, originOf(g), 0.5, {sink});
const ys = Array.from({{length: mesh.vertices}}, (_, i) => mesh.positions[3 * i + 1]);
console.log(JSON.stringify({{vertices: mesh.vertices, triangles: mesh.triangles, cells: mesh.cells, edges: mesh.edges,
  positions: Array.from(mesh.positions), indices: Array.from(mesh.indices), faces: faces(mesh),
  normals: Array.from(mesh.normals), maxIndex: Math.max(...mesh.indices)}}));""")
    assert (found["cells"], found["edges"], found["vertices"], found["triangles"]) == (4, 8, 9 + 32, 8 + 16)
    assert found["maxIndex"] == found["vertices"] - 1
    pos = np.array(found["positions"]).reshape(-1, 3)
    # the top: nine corners at 100 + 4 m, the heights relative to h0 = 90
    assert np.allclose(pos[:9, 1], 14.0)
    assert sorted({(round(x), round(z)) for x, _, z in pos[:9]}) == sorted({(x, z) for x in (-2, 0, 2) for z in (-2, 0, 2)})
    # the sides' feet under the terrain by the sink
    feet = pos[9:][np.isclose(pos[9:, 1], 10 - sink)]
    assert len(feet) == 16 and np.isclose(pos[9:, 1], 14.0).sum() == 16
    normals = np.array(found["normals"]).reshape(-1, 3)
    assert np.allclose(normals[:9], [0, 1, 0], atol=1e-6)
    outward = {tuple(n) for n in normals[9:].round(6).tolist()}
    assert outward == {(0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)}
    # every face is wound as its normal says: tops up, sides outward
    for face in found["faces"]:
        assert face["dot"] > 0.99, face
    ups = [f for f in found["faces"][:8]]
    assert all(f["n"][1] > 0.99 for f in ups)
    # the side faces are vertical and face away from the wood's centre
    centre = np.array([0.0, 0.0])
    indices = np.array(found["indices"]).reshape(-1, 3)
    for tri, face in zip(indices[8:], found["faces"][8:]):
        assert abs(face["n"][1]) < 1e-6
        middle = pos[tri].mean(axis=0)
        assert np.dot(np.array([face["n"][0], face["n"][2]]), np.array([middle[0], middle[2]]) - centre) > 0


def test_corners_take_the_tallest_cell_around_them(tmp_path):
    values = np.zeros((2, 4), dtype=np.uint8)
    values[:, 0:2] = 4    # 2 m
    values[:, 2:4] = 20   # 10 m
    found = run_ts(tmp_path, "view3d/canopymesh", PRELUDE + """
const v = Uint8Array.from(%s);
const g = ground(4, 2, (i, j) => 50 + j);
const mesh = m.buildMesh(g, m.lattice(v, 4, 2, 2, 2), originOf(g, 0), 0.5, 0.3);
const tops = [];
for (let i = 0; i < 6; i++) tops.push([mesh.positions[3 * i], mesh.positions[3 * i + 1], mesh.positions[3 * i + 2]]);
console.log(JSON.stringify({vertices: mesh.vertices, cells: mesh.cells, tops}));""" % json.dumps(values.ravel().tolist()))
    # two cells, six corners in three columns (x = left + 0, 2, 4 kept within the samples' centres 0.5 .. 3.5, so
    # at 0.5, 2 and 3.5); the ground is a plane 50 + j at the samples' centres, so 50, 51.5 and 53 there; the left
    # cell 2 m tall, the right 10 m: the shared middle column takes the right one's
    assert found["cells"] == 2 and found["vertices"] == 6 + 4 * 6
    by_x = {}
    for x, y, _ in found["tops"]:
        by_x.setdefault(round(x, 6), []).append(round(y, 6))
    assert by_x == {-1.5: [52.0, 52.0], 0.0: [61.5, 61.5], 1.5: [63.0, 63.0]}


def test_no_triangles_over_no_data(tmp_path):
    values = np.zeros((8, 8), dtype=np.uint8)
    values[2:6, 2:6] = 8
    found = run_ts(tmp_path, "view3d/canopymesh", PRELUDE + f"""
const v = Uint8Array.from({json.dumps(values.ravel().tolist())});
// no data from column 5 on: the corner at x = left + 6 has none of its four samples (5 and 6), so the cells that
// reach it drop out; the corners at x = left + 4 (samples 3 and 4) keep their terrain
const g = ground(8, 8, (i, j) => j >= 5 ? null : 100);
const lat = m.lattice(v, 8, 8, 2, 2);
const mesh = m.buildMesh(g, lat, originOf(g), 0.5, 0.3);
const xs = [];
for (let i = 0; i < mesh.vertices; i++) xs.push(mesh.positions[3 * i]);
const none = ground(8, 8, () => null);
const empty = m.buildMesh(none, lat, originOf(none), 0.5, 0.3);
console.log(JSON.stringify({{planned: lat.drawn, cells: mesh.cells, triangles: mesh.triangles, vertices: mesh.vertices,
  maxX: Math.max(...xs), emptyTriangles: empty.triangles, emptyVertices: empty.vertices, emptyCells: empty.cells,
  zeroCells: m.buildMesh(g, m.lattice(new Uint8Array(64), 8, 8, 2, 2), originOf(g), 0.5, 0.3).triangles}}));""")
    assert found["planned"] == 4 and found["cells"] == 2   # the two cells at samples 2..3 keep their corners
    assert found["maxX"] <= 1e-6   # x = left + 4 is the centre (0): nothing east of the last corner with data
    assert found["emptyTriangles"] == 0 and found["emptyVertices"] == 0 and found["emptyCells"] == 0
    assert found["zeroCells"] == 0


def lattice_for(tmp_path, side, res, k0, budget):
    return run_ts(tmp_path, "view3d/canopymesh", PRELUDE + f"""
const side = {side}, v = new Uint8Array(side * side).fill(40);
const l = m.chooseLattice(v, side, side, {k0}, 2, {budget});
const finer = m.lattice(v, side, side, l.k - 1, 2);
const g = ground(side, side, () => 100, {res});
const t0 = Date.now();
const mesh = m.buildMesh(g, l, originOf(g), 0.5, 0.3);
console.log(JSON.stringify({{k: l.k, nx: l.nx, vertices: l.vertices, triangles: l.triangles, finerVertices: finer.vertices,
  meshVertices: mesh.vertices, meshTriangles: mesh.triangles, ms: Date.now() - t0}}));""")


@pytest.mark.parametrize("level, side, res, budget, cell", [("full", 1537, 1.0, 100_000, 2), ("phone", 769, 2.0, 43_000, 4)])
def test_the_budget_makes_the_lattice_coarser(tmp_path, level, side, res, budget, cell):
    """A wood over the whole patch (the worst case) fits the vertex budget, and one cell finer would not."""
    k0 = max(1, round(cell / res))
    found = lattice_for(tmp_path, side, res, k0, budget)
    print(level, found)
    assert found["vertices"] <= budget < found["finerVertices"] and found["k"] > k0
    assert found["meshVertices"] == found["vertices"] and found["meshTriangles"] == found["triangles"]
    n = math.ceil(side / found["k"])
    assert found["nx"] == n and found["triangles"] == 2 * n * n + 8 * n


def test_a_sparse_canopy_keeps_the_cells_asked_for(tmp_path):
    rng = np.random.default_rng(1)
    side = 400
    values = np.zeros((side, side), dtype=np.uint8)
    for _ in range(40):  # clumps of trees
        r, c = rng.integers(10, side - 40, 2)
        values[r:r + rng.integers(5, 30), c:c + rng.integers(5, 30)] = 30
    found = run_ts(tmp_path, "view3d/canopymesh", f"""
const v = Uint8Array.from({json.dumps(values.ravel().tolist())});
const l = m.chooseLattice(v, {side}, {side}, 2, 2, 100000);
console.log(JSON.stringify({{k: l.k, vertices: l.vertices, cells: Array.from(l.cells)}}));""")
    assert found["k"] == 2 and found["vertices"] <= 100_000
    assert found["cells"] == pool(values, 2, MINIMUM).ravel().tolist()
    assert counts(pool(values, 2, MINIMUM))["vertices"] == found["vertices"]


def test_samples_per_cell(tmp_path):
    found = run_ts(tmp_path, "view3d/canopymesh", """
console.log(JSON.stringify([[2, 1], [4, 2], [2, 0.5], [4, 0.5], [2, 3], [2, 5]].map(([c, r]) => m.samplesPerCell(c, r))));""")
    assert found == [2, 2, 4, 8, 1, 1]


# ---------------------------------------------------------------------------------------------------------------
# In headless Edge: a real scene (scene.ts) over a synthetic hill of 513 × 513 samples, the tool of canopy.ts on it.
# The page is the app's /view3d template with a test bundle instead of view3d.js (main.ts is the coordinator's):
# the bundle builds the page's frame, the patch (its meta with or without `surface`), the scene and the canopy,
# then drives the tool by clicks and writes what it saw into <pre id="result">. The block is a file next to the
# page (the `url` option of createCanopy), so the real download.ts asks it as the page asks the server.

ENTRY = r"""
import { createScene } from "SRC/scene";
import { createCanopy } from "SRC/canopy";
import { toHeights } from "SRC/decode";

const params = new URLSearchParams(location.hash.slice(1));
const level = new URLSearchParams(location.search).get("level") === "phone" ? "phone" : "full";
const root = document.getElementById("view3d")!;
const el = (tag: string, cls: string, parent: HTMLElement) => {
  const e = document.createElement(tag);
  e.className = cls;
  parent.append(e);
  return e as HTMLElement;
};
const stage = el("div", "v3-stage", root), status = el("div", "v3-status v3-hidden", stage);
const credits = el("div", "v3-credits v3-hidden", stage), activity = el("div", "v3-activity v3-hidden", stage);
const tools = el("div", "v3-tools", stage), bottom = el("div", "v3-bottom", stage), card = el("div", "v3-card", bottom);
const bar = el("div", "v3-bar", root), readout = el("div", "v3-readout", bar), toolbar = el("div", "v3-toolbar", bar);
el("p", "v3-note", bar).textContent = "A visual preview";

// A hill of 513 × 513 samples of 1 m, the canopy's grid
const W = 513, H = 513, left = 1000, top = 2000, base_dm = 800;
const z = (i: number, j: number) => 100 + 25 * Math.exp(-(((i - 256) ** 2 + (j - 256) ** 2) / 20000)) + 0.02 * j;
const values = new Int16Array(W * H);
for (let i = 0; i < H; i++) for (let j = 0; j < W; j++) values[i * W + j] = Math.round(z(i, j) * 10) - base_dm;
const meta: any = {
  width: W, height: H, step: 1, res: 1, crs: "EPSG:2180", left, top, base_dm,
  anchors: [{x: left + 150, y: top - 256, h: z(256, 150)}, {x: left + 360, y: top - 256, h: z(256, 360)}],
  affine: [19, 1e-5, 0, 50, 0, 9e-6], rigging: {}, model: "sag", ortho: null, attribution: null, sha256: "",
};
if (params.get("surface") === "1") meta.surface = true;
const patch = {meta, values, ...toHeights(values, W, H, base_dm)};
const scene = createScene(patch, level, {stage, toolbar, credits, activity, tools, card}, () => {});
const out: any = {level, errors: [] as string[]};
const error = console.error.bind(console);
console.error = (...args: unknown[]) => { out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
let frames = 0;
scene.view.onDrawn(() => { root.dataset.frames = String(++frames); root.dataset.triangles = String(scene.view.renderer.info.render.triangles); });
scene.invalidate();

const asked: string[] = [], headers: string[] = [];
const open = XMLHttpRequest.prototype.open, setHeader = XMLHttpRequest.prototype.setRequestHeader;
XMLHttpRequest.prototype.open = function (this: XMLHttpRequest, method: string, url: string | URL, ...rest: any[]) {
  asked.push(String(url));
  return (open as any).call(this, method, url, ...rest);
} as any;
XMLHttpRequest.prototype.setRequestHeader = function (this: XMLHttpRequest, name: string, value: string) {
  headers.push(name + ": " + value);
  return setHeader.call(this, name, value);
};
const pill: string[] = [];
new MutationObserver(() => {
  const text = activity.querySelector(".v3-activity-text")?.textContent || "";
  if (!activity.classList.contains("v3-hidden") && text && pill[pill.length - 1] !== text) pill.push(text);
}).observe(activity, {subtree: true, childList: true, characterData: true, attributes: true});

// Under a virtual time budget headless Edge draws frames only while something loads: each poll loads a small file
let n = 0;
const until = (test: () => boolean, ms: number) => new Promise<boolean>((resolve) => {
  const started = Date.now();
  const poll = () => {
    if (test()) resolve(true);
    else if (Date.now() - started > ms) resolve(false);
    else fetch("stubs.js?poll=" + (++n)).then(() => setTimeout(poll, 50), () => setTimeout(poll, 50));
  };
  poll();
});
const trees = () => document.querySelector<HTMLButtonElement>('[data-tool="trees"]');
const state = () => ({trees: root.dataset.trees || null, frames: Number(root.dataset.frames), triangles: Number(root.dataset.triangles),
                      pressed: trees()?.getAttribute("aria-pressed") ?? null});
const finish = () => {
  const pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
};
(async () => {
  await until(() => frames > 0, 20000);
  await until(() => false, 800);
  out.drawn = frames > 0;
  const canopy = createCanopy(scene as any, {page: {run: "r", line: "1,2,3,4", level}, url: params.get("url") || "canopy.bin"});
  out.created = canopy !== null;
  out.tool = trees() !== null;
  out.toolLabel = trees()?.textContent?.trim() ?? null;
  out.dataTrees = root.dataset.trees ?? null;
  out.pickTargets = scene.pickTargets.length;
  if (!canopy) { finish(); return; }
  out.off = state();
  const click = () => trees()!.click();
  click();
  out.waitingState = state();
  out.pillOn = !activity.classList.contains("v3-hidden");
  out.arrived = await until(() => root.dataset.trees === "on" || root.dataset.trees === "failed", 20000);
  out.fresh = state();
  if (root.dataset.trees === "failed") {
    const note = document.querySelector(".v3-toolbar + .v3-note");
    out.note = note?.textContent ?? null;
    out.noteShown = !!note && !note.classList.contains("v3-hidden");
    out.pillAfter = activity.classList.contains("v3-hidden");
    out.group = scene.view.scene.getObjectByName("canopy") !== undefined;
    finish();
    return;
  }
  await until(() => state().frames > out.off.frames, 15000);
  await until(() => false, 800);
  out.on = state();
  out.meshTriangles = Number(root.dataset.treesTriangles);
  out.meshVertices = Number(root.dataset.treesVertices);
  out.cell = Number(root.dataset.treesCell);
  const group = scene.view.scene.getObjectByName("canopy")!;
  out.canopyLayers = group.children.map((c: any) => c.layers.mask);
  out.terrainLayer = scene.terrainLayer;
  out.pickTargetsOn = scene.pickTargets.length;
  out.canopyPicked = scene.pickTargets.some((o: any) => o === group || group.children.includes(o));
  out.canopyOrders = group.children.map((c: any) => c.renderOrder);
  out.pillAfter = activity.classList.contains("v3-hidden");
  out.pillTexts = pill;
  click();
  await until(() => root.dataset.trees === "off", 5000);
  await until(() => state().frames > out.on.frames, 15000);
  await until(() => false, 800);
  out.hidden = state();
  out.groupVisible = group.visible;
  click();
  await until(() => root.dataset.trees === "on", 5000);
  await until(() => state().frames > out.hidden.frames, 15000);
  await until(() => false, 800);
  out.again = state();
  out.requests = asked.filter((u) => u.includes(".bin"));
  out.header = headers.filter((h) => h.startsWith("X-Findaline"));
  scene.dispose();
  out.afterDispose = {tool: trees() !== null, trees: root.dataset.trees ?? null, group: scene.view.scene.getObjectByName("canopy") !== undefined};
  finish();
})().catch((e) => { out.crash = String((e && e.stack) || e); finish(); });
"""


def canopy_answer(side: int = 513) -> bytes:
    """A wood of 150 × 300 samples (10 m) and a house of 20 × 20 (8 m) on the patch's grid of the test scene."""
    values = np.zeros((side, side), dtype=np.uint8)
    values[100:250, 100:400] = 20
    values[300:320, 300:320] = 16
    return encode(values, left=1000.0, top=2000.0, res=1.0)


def _canopy_page(data, tmp_path) -> str:
    """The app's /view3d template with the test bundle instead of view3d.js, in runs/canopytest/ (served as it is
    locally), and the canopy block beside it."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / "canopytest"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "canopy.bin").write_bytes(canopy_answer())
    entry = tmp_path / "entry.ts"
    entry.write_text(ENTRY.replace("SRC", (VIEWER + "/src/view3d").replace("\\", "/")), encoding="utf-8")
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: [%s], bundle: true, format: 'iife', "
                                  "platform: 'browser', outfile: %s})" % (json.dumps(str(entry)),
                                                                          json.dumps(str(folder / "bundle.js")))],
                   cwd=VIEWER, check=True)
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    assert script in page
    (folder / "index.html").write_text(page.replace(
        script, '<script src="stubs.js"></script><script src="bundle.js"></script>'), encoding="utf-8")
    return "runs/canopytest/index.html"


def _in_edge(tmp_path, query: str, hash_: str) -> tuple:
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    page = _canopy_page(data, tmp_path)
    with _server(data) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", "--virtual-time-budget=60000", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}{query}#{hash_}"],
            capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    result = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    return result, dom


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_no_tool_without_a_surface_model(tmp_path):
    """The patch's meta without `surface`: createCanopy gives nothing, no tool in the strip, nothing on the root."""
    result, dom = _in_edge(tmp_path, "", "surface=0")
    print(result)
    assert "crash" not in result and result["drawn"], result
    assert result["created"] is False and result["tool"] is False and result["dataTrees"] is None
    assert not result["errors"] and _violations(dom) == []


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_the_tool_draws_the_canopy(tmp_path, level):
    """With `surface` in the meta the tool "Trees and buildings" exists; switched on it asks the block once (the
    activity pill meanwhile) and draws the mesh as two passes of its triangles (the scene's triangles grow by
    twice the mesh's), off the mesh is hidden (the scene as before), on again asks nothing; the meshes sit on
    layer 0 only (not the edges' terrain layer), are no pick target, and the scene's dispose takes the tool away."""
    result, dom = _in_edge(tmp_path, f"?level={level}", "surface=1")
    print(level, {k: v for k, v in result.items() if k != "errors"})
    assert "crash" not in result and result["drawn"], result
    assert result["created"] and result["tool"] and result["toolLabel"] == "Trees and buildings"
    assert result["off"]["trees"] == "off" and result["off"]["pressed"] == "false"
    assert result["waitingState"]["trees"] == "loading" and result["waitingState"]["pressed"] == "true"
    assert result["pillOn"] is True and result["pillTexts"] == ["Loading trees and buildings…"]
    assert result["fresh"]["trees"] == "on" and result["pillAfter"] is True
    # the mesh: cells of the level's side (the test's samples are 1 m at both levels)
    assert result["meshTriangles"] > 0 and 0 < result["meshVertices"] <= {"full": 100_000, "phone": 43_000}[level]
    assert result["cell"] == {"full": 2, "phone": 4}[level]
    assert result["on"]["triangles"] - result["off"]["triangles"] == 2 * result["meshTriangles"], result
    assert result["on"]["pressed"] == "true"
    assert result["hidden"]["trees"] == "off" and result["hidden"]["pressed"] == "false"
    assert result["groupVisible"] is False and result["hidden"]["triangles"] == result["off"]["triangles"]
    assert result["again"]["trees"] == "on" and result["again"]["triangles"] == result["on"]["triangles"]
    assert len(result["requests"]) == 1 and result["requests"][0].endswith("canopy.bin"), result["requests"]
    assert result["header"] == ["X-Findaline-Patch: 1"]
    # layer 0 only (bit 0), not the edges' terrain layer (1), no pick target, drawn after the lines and the other
    # transparent objects
    assert result["canopyLayers"] == [1, 1] and result["terrainLayer"] == 1
    assert result["canopyPicked"] is False and result["pickTargetsOn"] == result["pickTargets"]
    assert result["canopyOrders"] == [3, 4]
    assert result["afterDispose"] == {"tool": False, "trees": None, "group": False}
    assert not result["errors"] and _violations(dom) == []


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_a_failed_block_shows_its_note(tmp_path):
    """The block cannot be had (a 404 here): the note "could not be loaded" under the toolbar, the switch off, the
    activity pill gone, no mesh."""
    result, dom = _in_edge(tmp_path, "", "surface=1&url=missing.bin")
    print(result)
    assert "crash" not in result and result["created"] and result["tool"]
    assert result["fresh"]["trees"] == "failed" and result["fresh"]["pressed"] == "false"
    assert result["note"].startswith("Trees and buildings could not be loaded: ") and result["noteShown"] is True
    assert result["pillAfter"] is True and result["group"] is False
    assert _violations(dom) == []
