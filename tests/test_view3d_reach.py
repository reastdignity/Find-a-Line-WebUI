"""The page's side of "Only valid lines" (docs/3d-view-contract.md, "Round 2", point 3; viewer/src/view3d/reach.ts,
overlay.ts, edit.ts, scene.ts): in Node an answer of /api/reach encoded here by the contract's rules and decoded by
the page, the class and clearance of samples, the nearest valid sample, the overlay's RGBA picture and its UVs, the
lane that sends the reach requests one at a time beside the profile requests (fake fetches and timers), and the
overlay's mesh on the terrain's chunks; in headless Edge (from PowerShell) the tool, the overlay, the snap of a
dragged anchor and the order of the requests on the page of the local app, with /api/reach answered by a stub in the
page (the server's route is agent S's: XMLHttpRequest is wrapped before the bundle, see STUB)."""

import base64
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


def run_entry(tmp_path, source: str, script: str):
    """Like run_ts for a module made of `source` (TypeScript importing from viewer/src/view3d): bundled for Node,
    `script` run with it as `m`; returns its JSON output."""
    bundle = tmp_path / "entry.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{stdin: {{contents: {json.dumps(source)}, "
                                  f"resolveDir: {json.dumps(os.path.join(VIEWER, 'src', 'view3d'))}, loader: 'ts'}}, "
                                  f"bundle: true, format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    path = tmp_path / "entry-test.cjs"
    path.write_text(f"const m = require({json.dumps(str(bundle))});\n{script}", encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def encode(mask: np.ndarray, **meta) -> bytes:
    """An answer of /api/reach as the contract has it: uint32 LE N | N bytes of JSON meta | the deflated values."""
    values = zlib.compress(np.ascontiguousarray(mask, dtype=np.uint8).tobytes())
    full = {"width": mask.shape[1], "height": mask.shape[0], "lattice": 1, "res": 1.0, "left": 1000.0, "top": 2000.0,
            "anchor": {"x": 1010.5, "y": 1990.5, "h": 500.0}, "as": 1, "min_length": 10, "max_length": 60,
            "valid": int((mask > 0).sum()), "trees": int((mask >= 128).sum()), "quantum": 0.5,
            "sha256": hashlib.sha256(values).hexdigest(), **meta}
    head = json.dumps(full).encode("utf-8")
    return struct.pack("<I", len(head)) + head + values


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def small_mask() -> np.ndarray:
    """40 x 30 samples: a block of valid ones (clearance 1.5 m = 3 quanta) with a band over trees (high bit set)."""
    mask = np.zeros((30, 40), dtype=np.uint8)
    mask[5:20, 10:30] = 3
    mask[8:12, 15:25] = 3 | 0x80
    mask[0, 0] = 127  # a corner sample, capped clearance
    return mask


def test_answer_decodes_as_the_contract_says(tmp_path):
    """decodeReach: the meta, the mask as encoded, the sha256 and the size checked; fetchReach: the header, the
    refusals' messages."""
    mask = small_mask()
    good = encode(mask)
    sha = bytearray(good)
    sha[-5] ^= 0xFF  # a damaged byte of the deflated values
    short = encode(mask[:10], height=30)  # fewer values than the meta says
    bad_meta = encode(mask, lattice=0)
    found = run_ts(tmp_path, "view3d/reach", f"""
const bytes = (b64) => Uint8Array.from(Buffer.from(b64, "base64")).buffer;
(async () => {{
  const out = {{}};
  const reach = await m.decodeReach(bytes({json.dumps(b64(good))}));
  out.meta = reach.meta;
  out.mask = Array.from(reach.mask);
  for (const [name, data] of [["damaged", {json.dumps(b64(bytes(sha)))}], ["short", {json.dumps(b64(short))}],
                              ["badMeta", {json.dumps(b64(bad_meta))}], ["cut", {json.dumps(b64(good[:20]))}]]) {{
    try {{ await m.decodeReach(bytes(data)); out[name] = "decoded"; }} catch (e) {{ out[name] = e instanceof m.ReachError; }}
  }}
  const seen = [];
  const get = (status, body) => (url, headers) => {{ seen.push([url, headers]); return Promise.resolve({{status, body}}); }};
  out.ok = (await m.fetchReach("/api/reach?x", get(200, bytes({json.dumps(b64(good))})))).meta.valid;
  const refused = new TextEncoder().encode(JSON.stringify({{detail: {{message: "The anchor is outside the patch.",
                                                                    code: "reach_anchor_nope", params: {{}}}}}}));
  try {{ await m.fetchReach("/api/reach?y", get(400, refused.buffer)); out.refused = "fetched"; }}
  catch (e) {{ out.refused = e.message; }}
  try {{ await m.fetchReach("/api/reach?z", get(502, new TextEncoder().encode("Bad gateway").buffer)); }}
  catch (e) {{ out.html = e.message; }}
  out.seen = seen;
  out.header = m.REACH_HEADER;
  console.log(JSON.stringify(out));
}})();""")
    assert found["meta"]["width"] == 40 and found["meta"]["height"] == 30 and found["meta"]["quantum"] == 0.5
    assert found["meta"]["valid"] == int((mask > 0).sum()) and found["meta"]["as"] == 1
    assert found["mask"] == mask.ravel().tolist()
    assert found["damaged"] is True and found["short"] is True and found["badMeta"] is True and found["cut"] is True
    assert found["ok"] == int((mask > 0).sum()) and found["header"] == "X-Findaline-Reach"
    assert [h for _, h in found["seen"]] == [{"X-Findaline-Reach": "1"}] * 3
    # the server's message reaches the page as it is (an unknown code falls back to the message); a body that is not JSON
    # gives the status
    assert found["refused"] == "The anchor is outside the patch." and found["html"] == "502"


def test_request_address(tmp_path):
    """reachUrl: the page's run and line as /api/patch took them, the step of its level, the fixed point as lat,lon
    with 7 decimals, which end it is."""
    found = run_ts(tmp_path, "view3d/reach", """
const page = {run: "2026-11-05_x y", line: "50.1,19.7,50.2,19.8", level: "full"};
console.log(JSON.stringify([m.reachUrl(page, [19.75627221, 50.15595081], 1), m.reachUrl({...page, level: "phone"}, [19.8, 50.2], 2),
                            m.reachUrl(page, [19.8, 50.2], 2, 2)]));""")
    assert found[0] == "/api/reach?run=2026-11-05_x%20y&line=50.1%2C19.7%2C50.2%2C19.8&step=1&anchor=50.1559508,19.7562722&as=1"
    assert found[1].endswith("&step=2&anchor=50.2000000,19.8000000&as=2")
    assert found[2].endswith("&step=2&anchor=50.2000000,19.8000000&as=2")


def reach_literal(mask: np.ndarray, **meta) -> str:
    """A Reach object in JS for `mask` (the meta of `encode`'s defaults)."""
    full = {"width": mask.shape[1], "height": mask.shape[0], "lattice": 1, "res": 1.0, "left": 1000.0, "top": 2000.0,
            "quantum": 0.5, "as": 1, **meta}
    return f"{{meta: {json.dumps(full)}, mask: Uint8Array.from({json.dumps(mask.ravel().tolist())})}}"


def cell_of(meta, x, y):
    """Python's own: the lattice cell (row, column) holding the grid point, None outside."""
    step = meta["lattice"] * meta["res"]
    j = math.floor((x - (meta["left"] + (0.5 - meta["lattice"] / 2) * meta["res"])) / step)
    i = math.floor(((meta["top"] - (0.5 - meta["lattice"] / 2) * meta["res"]) - y) / step)
    return (i, j) if 0 <= i < meta["height"] and 0 <= j < meta["width"] else None


def centre_of(meta, i, j):
    return (meta["left"] + (j * meta["lattice"] + 0.5) * meta["res"], meta["top"] - (i * meta["lattice"] + 0.5) * meta["res"])


@pytest.mark.parametrize("lattice, res", [(1, 1.0), (2, 1.0), (2, 0.5)])
def test_samples_classes_and_the_nearest_valid(tmp_path, lattice, res):
    """The class and clearance of the sample holding a point, and the nearest valid sample's centre within a
    radius, against a brute-force Python version, on the 1 m and the thinned lattice."""
    rng = np.random.default_rng(lattice)
    mask = np.zeros((30, 40), dtype=np.uint8)
    mask[rng.random(mask.shape) < 0.08] = 4
    mask[rng.random(mask.shape) < 0.04] = 9 | 0x80
    meta = {"width": 40, "height": 30, "lattice": lattice, "res": res, "left": 1000.0, "top": 2000.0, "quantum": 0.5}
    step = lattice * res
    points = [(1000 + rng.uniform(-3, 45) * step, 2000 - rng.uniform(-3, 35) * step) for _ in range(120)]
    radii = [float(rng.uniform(0.2, 6) * step) for _ in points]
    found = run_ts(tmp_path, "view3d/reach", f"""
const reach = {reach_literal(mask, lattice=lattice, res=res)};
const points = {json.dumps(points)}, radii = {json.dumps(radii)};
console.log(JSON.stringify(points.map(([x, y], k) => [m.kindAt(reach, x, y), m.clearanceAt(reach, x, y), m.nearestValid(reach, x, y, radii[k])])));""")
    for (x, y), radius, (kind, clearance, near) in zip(points, radii, found):
        at = cell_of(meta, x, y)
        value = int(mask[at]) if at else 0
        assert kind == (0 if value == 0 else 2 if value & 0x80 else 1)
        assert clearance == (None if value == 0 else (value & 0x7F) * 0.5)
        best = None
        for i, j in zip(*np.nonzero(mask)):
            cx, cy = centre_of(meta, i, j)
            d = math.hypot(cx - x, cy - y)
            if d <= radius and (best is None or d < best[0] - 1e-9):
                best = (d, i, j)
        if best is None:
            assert near is None
        else:
            assert near is not None and near["distance"] == pytest.approx(best[0], abs=1e-9)
            assert (near["x"], near["y"]) == pytest.approx(centre_of(meta, near["i"], near["j"]), abs=1e-9)
            assert near["kind"] == (2 if mask[near["i"], near["j"]] & 0x80 else 1)
            assert near["clearance"] == (int(mask[near["i"], near["j"]]) & 0x7F) * 0.5


def test_snap_radius(tmp_path):
    """snapRadius: SNAP_PX pixels at the hit's distance, at least a cell and a half, at most SNAP_MAX_M."""
    found = run_ts(tmp_path, "view3d/reach", """
console.log(JSON.stringify({near: m.snapRadius(10, 50, 800, 1), mid: m.snapRadius(400, 50, 800, 1), far: m.snapRadius(50000, 50, 800, 1),
                            cell: m.snapRadius(10, 50, 800, 2), max: m.SNAP_MAX_M, px: m.SNAP_PX}));""")
    per_pixel = 2 * 400 * math.tan(math.radians(25)) / 800
    assert found["near"] == 1.5 and found["far"] == found["max"] == 80 and found["cell"] == 3.0
    assert found["mid"] == pytest.approx(found["px"] * per_pixel)


@pytest.mark.parametrize("lattice", [1, 2])
def test_the_overlay_picture(tmp_path, lattice):
    """reachPicture: cropped to the valid samples with a transparent pixel around, the fitting colour where the line
    fits and the trees' where it passes over trees, 45 % opaque, transparent elsewhere; pictureUv maps a sample's
    centre to the middle of its pixel; nothing valid, no picture."""
    mask = small_mask()
    mask[0, 0] = 0
    meta = {"width": 40, "height": 30, "lattice": lattice, "res": 1.0, "left": 1000.0, "top": 2000.0, "quantum": 0.5}
    found = run_ts(tmp_path, "view3d/reach", f"""
const reach = {reach_literal(mask, lattice=lattice)}, p = m.reachPicture(reach, [10, 120, 60], [240, 130, 0]);
const uv = m.pictureUv(p);
const centres = [];
for (const [i, j] of {json.dumps([[5, 10], [8, 15], [19, 29], [11, 24]])}) {{
  centres.push(uv(reach.meta.left + (j * {lattice} + 0.5), reach.meta.top - (i * {lattice} + 0.5)));
}}
console.log(JSON.stringify({{width: p.width, height: p.height, left: p.left, top: p.top, cell: p.cell, rgba: Array.from(p.rgba), centres,
  none: m.reachPicture({{meta: reach.meta, mask: new Uint8Array(40 * 30)}}, [0, 0, 0], [0, 0, 0])}}));""")
    assert found["none"] is None
    assert (found["width"], found["height"], found["cell"]) == (22, 17, lattice)
    pixels = np.array(found["rgba"], dtype=np.uint8).reshape(17, 22, 4)
    inner = pixels[1:-1, 1:-1]
    expected_alpha = np.where(mask[5:20, 10:30] > 0, 115, 0)
    assert np.array_equal(inner[..., 3], expected_alpha)
    assert (pixels[0, :, 3] == 0).all() and (pixels[-1, :, 3] == 0).all()
    assert (pixels[:, 0, 3] == 0).all() and (pixels[:, -1, 3] == 0).all()
    over_trees = mask[5:20, 10:30] >= 128
    assert (inner[over_trees][:, :3] == [240, 130, 0]).all() and (inner[~over_trees][:, :3] == [10, 120, 60]).all()
    assert (pixels[0, :, :3] == [10, 120, 60]).all()  # transparent, but the fitting colour: mipmaps do not darken
    # the west and north edges of the picture: one pixel before the first valid sample's cell
    edge = (0.5 - lattice / 2)
    assert found["left"] == pytest.approx(1000 + (10 - 1) * lattice + edge)
    assert found["top"] == pytest.approx(2000 - (5 - 1) * lattice - edge)
    for (i, j), (u, v) in zip([[5, 10], [8, 15], [19, 29], [11, 24]], found["centres"]):
        assert u == pytest.approx((j - 10 + 1 + 0.5) / 22) and v == pytest.approx((i - 5 + 1 + 0.5) / 17)


def test_the_overlay_meshes_use_the_surface_only(tmp_path):
    """scene.ts' overlay: it draws the chunk's surface triangles (the draw range before the skirts) with UVs for the
    surface vertices only, so every index in that range must name a surface vertex (and the skirts follow)."""
    found = run_ts(tmp_path, "view3d/terrain", """
const cols = 513, heights = new Float32Array(cols * cols);
for (let i = 0; i < cols; i++) for (let j = 0; j < cols; j++) heights[i * cols + j] = 300 + 40 * Math.sin(i / 40) * Math.cos(j / 55);
const meta = {left: 0, top: 513, res: 1, width: cols, height: cols, base_dm: 2500,
  anchors: [{x: 156.5, y: 256.5, h: heights[256 * cols + 156]}, {x: 356.5, y: 256.5, h: heights[256 * cols + 356]}]};
const patch = {meta, heights, cols, rows: cols}, origin = {cx: 256.5, cy: 256.5, h0: 250};
const built = m.buildTerrain(patch, origin, 0.25, 300000);
console.log(JSON.stringify(built.chunks.map((c) => {
  let max = -1;
  for (let k = 0; k < c.surfaceIndices; k++) max = Math.max(max, c.indices[k]);
  return [max < c.surfaceVertices, c.grid.length / 2 >= c.surfaceVertices, c.indices.length > c.surfaceIndices];
})));""")
    assert found and all(f[0] and f[1] for f in found)


# The lane and the profile queue in turn, with fake fetches and fake timers
LANE_ENTRY = "export * from './reach'; export * from './interact';"

LANE_PREAMBLE = """
// a fetch under the test's control: resolve/reject it by hand; `quick` counts the requests in flight at once
const quick = {now: 0, max: 0, started: []};
const task = (name, value) => {
  quick.now++; quick.max = Math.max(quick.max, quick.now); quick.started.push(name);
  let done;
  const promise = new Promise((resolve, reject) => { done = {resolve, reject}; });
  const finish = (how, v) => { quick.now--; done[how](v); };
  return {promise, ok: (v) => finish("resolve", v ?? value), fail: (e) => finish("reject", new Error(e))};
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 5; i++) await tick(); };
const reachOf = (slot) => ({meta: {as: slot + 1}, mask: new Uint8Array(1)});
function make() {
  const sent = [], got = [], failed = [], busy = [];
  const tasks = {};
  const lane = m.reachLane((slot) => { const t = task("reach" + slot, reachOf(slot)); sent.push(slot); tasks["r" + slot] = t; return t.promise; },
    {got: (slot, r) => got.push([slot, r.meta.as]), failed: (slot, e) => failed.push([slot, e.message]), busy: (on) => busy.push(on)});
  return {lane, sent, got, failed, busy, tasks};
}
"""


def test_the_lane_sends_one_request_at_a_time(tmp_path):
    """reachLane: reach requests in turn (the slot named first goes first), none while off or held, answers of an
    ask made again or dropped ignored, a failure reported while the other slot is still served."""
    found = run_entry(tmp_path, LANE_ENTRY, LANE_PREAMBLE + """
(async () => {
  const out = {};
  let s = make();
  s.lane.want(0); s.lane.want(1);
  await settle();
  out.off = [s.sent.length];                       // not on: nothing goes
  s.lane.on = true;
  await settle();
  out.first = [s.sent.slice(), s.lane.running];
  s.tasks.r0.ok(); await settle();
  out.second = [s.sent.slice(), s.got.slice()];
  s.tasks.r1.ok(); await settle();
  out.done = [s.got.slice(), s.lane.running, s.busy.slice(), quick.max];

  // held: waits; released: goes
  s = make(); s.lane.on = true; s.lane.hold(true); s.lane.want(1); await settle();
  out.held = s.sent.length;
  s.lane.hold(false); await settle();
  out.released = s.sent.slice();
  s.tasks.r1.ok(); await settle();

  // an ask made again while one is in flight: the old answer ignored, the new one asked after it
  s = make(); s.lane.on = true; s.lane.want(0); await settle();
  s.lane.want(0); await settle();
  out.againSent = s.sent.length;
  s.tasks.r0.ok(); await settle();
  out.againGot = s.got.length; out.againSent2 = s.sent.length;
  s.tasks.r0.ok(); await settle();
  out.againGot2 = s.got.slice();

  // dropped: the answer ignored, nothing asked again
  s = make(); s.lane.on = true; s.lane.want(1); await settle(); s.lane.drop(1); s.tasks.r1.ok(); await settle();
  out.dropped = [s.got.length, s.sent.length, s.lane.running];

  // stop: ignored, nothing starts; on again works
  s = make(); s.lane.on = true; s.lane.want(0); s.lane.want(1); await settle();
  s.lane.stop(); s.tasks.r0.ok(); await settle();
  out.stopped = [s.got.length, s.sent.length, s.lane.on];
  s.lane.on = true; s.lane.want(1); await settle();
  out.again = [s.sent.slice()];
  s.tasks.r1.ok(); await settle();
  out.againDone = s.got.slice();

  // a failure is reported and the other slot is still served
  s = make(); s.lane.on = true; s.lane.want(0); s.lane.want(1); await settle();
  s.tasks.r0.fail("no good"); await settle();
  out.failed = [s.failed.slice(), s.sent.slice()];
  s.tasks.r1.ok(); await settle();
  out.failedGot = s.got.slice();

  // the first() slot goes first
  s = make(); let first = 1;
  const lane = m.reachLane((slot) => { s.sent.push(slot); return task("x" + slot, reachOf(slot)).promise; }, {got() {}, failed() {}, busy() {}}, () => first);
  lane.want(0); lane.want(1); lane.on = true; await settle();
  out.order = s.sent.slice();
  console.log(JSON.stringify(out));
})();""")
    assert found["off"] == [0]
    assert found["first"] == [[0], True]
    assert found["second"] == [[0, 1], [[0, 1]]]
    assert found["done"][0] == [[0, 1], [1, 2]] and found["done"][1] is False and found["done"][2] == [True, False, True, False]
    assert found["done"][3] == 1
    assert found["held"] == 0 and found["released"] == [1]
    assert found["againSent"] == 1 and found["againGot"] == 0 and found["againSent2"] == 2 and found["againGot2"] == [[0, 1]]
    assert found["dropped"] == [0, 1, False]
    assert found["stopped"] == [0, 1, False] and found["again"] == [[0, 1]] and found["againDone"] == [[1, 2]]
    assert found["failed"] == [[[0, "no good"]], [0, 1]] and found["failedGot"] == [[1, 2]]
    assert found["order"] == [1]  # both wanted before the switch: the slot first() names goes first


def test_reach_and_profile_requests_never_overlap(tmp_path):
    """A release with the switch on, as edit.ts wires it: the profile queue's debounce holds the lane, its fetch goes
    through `guard` (waiting for a reach request in flight), and once its answer is in the moved anchor's reach is
    asked. At no time are two requests of the quick lane in flight."""
    found = run_entry(tmp_path, LANE_ENTRY, LANE_PREAMBLE + """
(async () => {
  const out = {};
  const timers = [];
  const clock = {setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearTimeout: (h) => { timers[h - 1] = {fn: () => {}, ms: 0}; }};
  const s = make();
  const lane = s.lane;
  const profiles = [];
  const queue = m.profileQueue((key) => lane.guard(() => { const t = task("profile " + key, {line: key}); profiles.push(t); return t.promise; }),
    () => lane.hold(false), 300, clock);
  lane.on = true;
  lane.want(0); lane.want(1);                          // the switch goes on: both reaches are asked
  await settle();                                      // reach 0 in flight
  // a release while reach 0 is in flight: the profile waits its debounce, then for the reach in flight
  lane.hold(true); queue.push("moved-1");
  s.tasks.r0.ok(); await settle();                     // reach 0 in; the lane is held: reach 1 waits
  out.afterReach0 = [quick.started.slice(), quick.now];
  timers[timers.length - 1].fn(); await settle();      // the debounce is over: the profile goes
  out.profileStarted = [quick.started.slice(), quick.now];
  // a reach is wanted anew (the moved anchor's) during the profile: it waits
  lane.want(1); await settle();
  out.duringProfile = [quick.started.slice(), quick.now];
  profiles[0].ok(); await settle();                    // the profile in: hold released, the reach goes
  out.afterProfile = [quick.started.slice(), quick.now];
  s.tasks.r1.ok(); await settle();
  out.end = [quick.started.slice(), quick.now, quick.max, s.got];
  // a profile cancelled while waiting its debounce lets the reach go
  const t2 = make();
  t2.lane.on = true;
  t2.lane.hold(true); t2.lane.want(0); await settle();
  out.heldSent = t2.sent.length;
  t2.lane.hold(false); await settle();
  out.heldSent2 = t2.sent.length;
  console.log(JSON.stringify(out));
})();""")
    assert found["afterReach0"] == [["reach0"], 0]
    assert found["profileStarted"] == [["reach0", "profile moved-1"], 1]
    assert found["duringProfile"] == [["reach0", "profile moved-1"], 1]
    assert found["afterProfile"] == [["reach0", "profile moved-1", "reach1"], 1]
    assert found["end"][0] == ["reach0", "profile moved-1", "reach1"] and found["end"][1] == 0 and found["end"][2] == 1
    assert found["end"][3] == [[0, 1], [1, 2]]
    assert found["heldSent"] == 0 and found["heldSent2"] == 1


# ---- headless Edge (from PowerShell) -------------------------------------------------------------------------
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture)
from test_web import CSP_STUB, EDGE, LOCAL, TOKEN, _lines_of, _server, _violations, web  # noqa: E402

# Loaded before the bundle: /api/reach is not in the app of this branch (the server's side is built apart from the
# page's), so XMLHttpRequest is wrapped: the patch's meta is read from its answer, a request for /api/reach is
# answered here by the contract's format (a ring of valid samples 20 m to 0.9 L from the fixed anchor, over trees
# beyond 0.7 L; held at `REACH.gate` while that is a promise), and every request of the quick lane (the reach, the
# profile) is counted with the number in flight at once (`REACH.max`).
STUB = """
window.REACH = {gate: null, open: null, requests: [], profiles: [], meta: null, active: 0, max: 0, overlaps: 0};
(function () {
  const R = window.REACH, Real = window.XMLHttpRequest, realFetch = window.fetch.bind(window);
  const enter = () => { if (R.active > 0) R.overlaps++; R.active++; R.max = Math.max(R.max, R.active); };
  const leave = () => { R.active--; };
  const inverse = (affine, lon, lat) => {
    const [a0, a1, a2, b0, b1, b2] = affine, det = a1 * b2 - a2 * b1, dx = lon - a0, dy = lat - b0;
    return [(dx * b2 - a2 * dy) / det, (a1 * dy - b1 * dx) / det];
  };
  R.inverse = inverse;
  async function sha256(bytes) {
    const d = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  async function answer(fx, fy, as) {
    const m = R.meta, [a, b] = m.anchors, L = Math.hypot(a.x - b.x, a.y - b.y), mask = new Uint8Array(m.width * m.height);
    let valid = 0, trees = 0;
    for (let i = 0; i < m.height; i++) {
      const y = m.top - (i + 0.5) * m.res;
      if (Math.abs(y - fy) > L) continue;
      for (let j = 0; j < m.width; j++) {
        const x = m.left + (j + 0.5) * m.res, d = Math.hypot(x - fx, y - fy);
        if (d < 20 || d > 0.9 * L) continue;
        mask[i * m.width + j] = d > 0.7 * L ? 4 | 128 : 4;
        valid++;
        if (d > 0.7 * L) trees++;
      }
    }
    const values = new Uint8Array(await new Response(new Blob([mask]).stream().pipeThrough(new CompressionStream("deflate"))).arrayBuffer());
    const meta = {width: m.width, height: m.height, lattice: 1, res: m.res, left: m.left, top: m.top,
                  anchor: {x: fx, y: fy, h: m.anchors[as - 1].h}, as, min_length: 20, max_length: 0.9 * L, valid, trees,
                  quantum: 0.5, sha256: await sha256(values)};
    const head = new TextEncoder().encode(JSON.stringify(meta)), out = new Uint8Array(4 + head.length + values.length);
    new DataView(out.buffer).setUint32(0, head.length, true);
    out.set(head, 4);
    out.set(values, 4 + head.length);
    return out.buffer;
  }
  window.XMLHttpRequest = class extends Real {
    open(method, url, ...rest) { this._url = String(url); this._headers = {}; return super.open(method, url, ...rest); }
    setRequestHeader(name, value) { this._headers[name] = value; return super.setRequestHeader(name, value); }
    send(body) {
      if (this._url.startsWith("/api/patch")) {
        this.addEventListener("load", () => {
          const n = new DataView(this.response).getUint32(0, true);
          R.meta = JSON.parse(new TextDecoder().decode(new Uint8Array(this.response, 4, n)));
        });
        return super.send(body);
      }
      if (!this._url.startsWith("/api/reach")) return super.send(body);
      const query = new URLSearchParams(this._url.split("?")[1]), as = Number(query.get("as"));
      const entry = {url: this._url, headers: this._headers, as, anchor: query.get("anchor"), step: query.get("step"),
                     run: query.get("run"), line: query.get("line")};
      R.requests.push(entry);
      enter();
      (async () => {
        if (R.gate) await R.gate;
        else await new Promise((resolve) => setTimeout(resolve, 100));
        const [lat, lon] = entry.anchor.split(",").map(Number), [fx, fy] = inverse(R.meta.affine, lon, lat);
        const body = await answer(fx, fy, as);
        leave();
        Object.defineProperty(this, "status", {value: 200});
        Object.defineProperty(this, "response", {value: body});
        Object.defineProperty(this, "readyState", {value: 2, configurable: true});
        this.getResponseHeader = () => null;
        if (this.onreadystatechange) this.onreadystatechange();
        if (this.onload) this.onload({loaded: body.byteLength});
      })();
    }
  };
  window.fetch = (url, init) => {
    if (!String(url).startsWith("/api/profile")) return realFetch(url, init);
    enter();
    const entry = {line: new URL(url, location.href).searchParams.get("line")};
    R.profiles.push(entry);
    return realFetch(url, init).finally(leave);
  };
})();
"""

REACH_SCRIPT = """
(async function () {
  const root = document.getElementById("view3d"), R = window.REACH, out = {errors: []};
  const error = console.error.bind(console);
  console.error = (...args) => { out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  // under a virtual time budget headless Edge draws animation frames only while something loads: each poll loads a
  // small file, so a frame the page asked for comes
  let n = 0;
  const until = (test, ms, then) => {
    const started = Date.now();
    const poll = () => {
      if (test()) then(true);
      else if (Date.now() - started > ms) then(false);
      else fetch("stubs.js?poll=" + (++n)).then(() => setTimeout(poll, 100), () => setTimeout(poll, 100));
    };
    poll();
  };
  const waitFor = (test, ms) => new Promise((resolve) => until(test, ms, resolve));
  const sleep = (ms) => new Promise((resolve) => until(() => false, ms, resolve));
  const settle = async (ms) => {  // no frame drawn for a second
    let frames = root.dataset.frames, since = Date.now();
    return waitFor(() => {
      if (root.dataset.frames !== frames) { frames = root.dataset.frames; since = Date.now(); }
      return Date.now() - since >= 1000;
    }, ms);
  };
  const pointer = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  const snapshot = () => {
    const c = document.querySelector("canvas.v3-canvas"), t = document.createElement("canvas");
    t.width = c.width; t.height = c.height;
    const g = t.getContext("2d");
    g.drawImage(c, 0, 0);
    return g.getImageData(0, 0, t.width, t.height).data;
  };
  const diff = (a, b) => {
    let count = 0;
    for (let i = 0; i < a.length; i += 4) {
      if (Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]) > 24) count++;
    }
    return count;
  };
  const handles = () => [...document.querySelectorAll(".v3-handle")];
  const centre = (e) => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
  // drag handle k towards (fraction > 0) or away from (< 0) the other one, from where it stands, in two moves
  const drag = (k, fraction) => {
    const [h1, h2] = handles(), me = k ? h2 : h1, other = k ? h1 : h2;
    const [x0, y0] = centre(me), [ox, oy] = centre(other);
    const x1 = x0 + (ox - x0) * fraction, y1 = y0 + (oy - y0) * fraction;
    pointer("pointerdown", me, x0, y0);
    pointer("pointermove", me, (x0 + x1) / 2, (y0 + y1) / 2);
    pointer("pointermove", me, x1, y1);
    pointer("pointerup", me, x1, y1);
  };
  const gridOf = (lat, lon) => R.inverse(R.meta.affine, lon, lat);
  const anchorsOf = (line) => { const v = line.split(",").map(Number); return [gridOf(v[0], v[1]), gridOf(v[2], v[3])]; };
  const edited = () => root.dataset.edit === "checked" || root.dataset.edit === "error";
  const frac = (p) => [(p[0] - R.meta.left - 0.5 * R.meta.res) % 1, (p[1] - R.meta.top + 0.5 * R.meta.res) % 1];
  try {
    out.ready = await waitFor(() => root.dataset.ready === "1", 25000);
    out.settled = await settle(15000);
    const tool = document.querySelector('[data-tool="valid"]');
    out.tools = [...document.querySelectorAll(".v3-tools .v3-tool")].map((b) => b.dataset.tool);
    out.handles = handles().length;
    if (!tool) { done(); return; }
    out.label = tool.textContent.trim();
    out.pressed0 = tool.getAttribute("aria-pressed");
    out.reach0 = root.dataset.reach;
    out.notes0 = [...document.querySelectorAll(".v3-valid-note")].map((p) => p.classList.contains("v3-hidden"));
    const base = snapshot(), trianglesBase = Number(root.dataset.triangles), p0 = R.profiles.length;  // the found line's own profile is in
    const found = R.meta.anchors, L = Math.hypot(found[0].x - found[1].x, found[0].y - found[1].y);
    out.length = L;
    out.pageLine = decodeURIComponent((location.hash.match(/line=([^&]*)/) || [])[1] || "");

    // 1. the switch on, the first reach held at the server: the pill, the hint, the handle moves freely
    R.gate = new Promise((resolve) => { R.open = resolve; });
    tool.click();
    await waitFor(() => R.requests.length >= 1, 5000);
    out.pressed1 = tool.getAttribute("aria-pressed");
    const pill = document.querySelector(".v3-activity");
    out.pill = [!pill.classList.contains("v3-hidden"), pill.textContent];
    out.notes1 = [...document.querySelectorAll(".v3-valid-note")].map((p) => [p.classList.contains("v3-hidden"), p.textContent.slice(0, 40)]);
    out.first = R.requests[0];
    drag(1, 0.2);
    out.waiting = root.dataset.edit;
    await sleep(1500);   // the debounce is over: the profile waits for the reach in flight
    out.profilesWhileReach = R.profiles.length - p0;
    out.requestsWhileReach = R.requests.length;
    R.open();
    R.gate = null;
    await waitFor(() => edited() && R.requests.length >= 2 && R.active === 0, 25000);
    out.free = {profiles: R.profiles.slice(p0), requests: R.requests.map((r) => [r.as, r.anchor]), reach: root.dataset.reach, edit: root.dataset.edit};
    out.freeFrac = frac(anchorsOf(R.profiles[p0].line)[1]);

    // 2. with the reach of anchor 1 in, a dragged anchor 2 rests on a valid sample's centre
    drag(1, 0.2);
    await waitFor(() => R.profiles.length >= p0 + 2, 10000);
    await waitFor(() => edited() && R.active === 0 && R.requests.length >= 3, 25000);
    const snapped = anchorsOf(R.profiles[p0 + 1].line);
    out.snapped = {frac: frac(snapped[1]), d: Math.hypot(snapped[1][0] - snapped[0][0], snapped[1][1] - snapped[0][1]),
                   moved: R.profiles[p0 + 1].line !== R.profiles[p0].line};
    // 3. dragged away, outside the valid ring: it stays where it was
    drag(1, -0.7);
    await waitFor(() => R.profiles.length >= p0 + 3, 10000);
    await waitFor(() => edited() && R.active === 0, 25000);
    out.stays = R.profiles[p0 + 2].line === R.profiles[p0 + 1].line;
    // 4. back to the found line: both reaches asked again with the found anchors, anchor 1's shows
    const before = R.requests.length;
    document.querySelector(".v3-reset").click();
    out.afterReset = root.dataset.edit;
    await waitFor(() => R.requests.length >= before + 2 && R.active === 0, 25000);
    await settle(15000);
    out.reset = {requests: R.requests.slice(before).map((r) => [r.as, r.anchor]), reach: root.dataset.reach};
    out.lit = {different: diff(base, snapshot()), pixels: base.length / 4, triangles: Number(root.dataset.triangles), base: trianglesBase};
    out.overlaps = [R.overlaps, R.max];
    out.all = R.requests.map((r) => ({as: r.as, step: r.step, run: r.run, line: r.line, header: r.headers["X-Findaline-Reach"]}));

    // 5. the switch off: the overlay is gone and no request is asked; the same with a request in flight
    tool.click();
    await settle(15000);
    out.off = {pressed: tool.getAttribute("aria-pressed"), reach: root.dataset.reach, triangles: Number(root.dataset.triangles),
               different: diff(base, snapshot()), notes: [...document.querySelectorAll(".v3-valid-note")].map((p) => p.classList.contains("v3-hidden"))};
    const count = R.requests.length;
    R.gate = new Promise((resolve) => { R.open = resolve; });
    tool.click();
    await waitFor(() => R.requests.length > count, 5000);
    tool.click();
    await sleep(500);
    R.open();
    R.gate = null;
    await sleep(2500);
    await settle(15000);
    out.offInFlight = {requests: R.requests.length - count, reach: root.dataset.reach, triangles: Number(root.dataset.triangles),
                       pillHidden: document.querySelector(".v3-activity").classList.contains("v3-hidden")};
  } catch (e) {
    out.exception = String((e && e.stack) || e);
  }
  done();
})();
"""


def _reach_page(data, name: str) -> str:
    """The app's /view3d page with the CSP stub and STUB before its bundle and REACH_SCRIPT after it (as test_view3d's
    pages), in runs/<name>/."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB + STUB, encoding="utf-8")
    (folder / "test.js").write_text(REACH_SCRIPT, encoding="utf-8")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    tag = '<script src="/app/view3d.js"></script>'
    assert tag in page
    (folder / "index.html").write_text(page.replace(tag, f'<script src="stubs.js"></script>{tag}<script src="test.js"></script>'),
                                       encoding="utf-8")
    return f"runs/{name}/index.html"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_only_valid_lines(clip_data, tmp_path, monkeypatch, level):
    """The tool `valid` at level full (none at the phone level): the switch asks the reach of each anchor in turn
    (the pill meanwhile, the hint), the profile after a release waits for a reach in flight, the overlay is drawn
    over the terrain when the reach of the staying anchor is in (more triangles in the frame, pixels changed, the
    root's data-reach), a dragged anchor rests on a valid sample's centre and stays where it was beyond the ring, a
    moved anchor's reach is asked after its profile, the found anchors are asked as the page's line gives them, no
    two requests of the quick lane at once, off drops the overlay and the requests in flight."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    page = _reach_page(data, "view3dreach")
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             "--window-size=1200,800", "--virtual-time-budget=240000", "--force-prefers-no-reduced-motion", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=420).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    r = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, json.dumps(r, indent=1))
    assert r["ready"] and r["settled"] and "exception" not in r, r
    assert _violations(dom) == []
    if level == "phone":
        assert "valid" not in r["tools"] and r["handles"] == 0
        return
    assert r["tools"][0] == "valid" and r["label"] == "Only valid lines" and r["pressed0"] == "false" and r["reach0"] == ""
    assert r["notes0"] == [True, True]
    lat1, lon1, lat2, lon2 = (float(v) for v in r["pageLine"].split(","))
    # the switch on: the first reach is the found anchor 1's as the page's line gives it, with the header
    assert r["pressed1"] == "true" and r["pill"] == [True, "Checking valid lines…"]
    assert r["notes1"][0][0] is False and r["notes1"][0][1].startswith("Green: the line fits")
    first = r["first"]
    assert first["as"] == 1 and first["step"] == "1" and first["run"] == meta["id"] and first["line"] == r["pageLine"]
    assert first["anchor"] == f"{lat1:.7f},{lon1:.7f}" and first["headers"] == {"X-Findaline-Reach": "1"}
    # the handle moved freely while no reach was in (not on a sample's centre), the profile waited for the reach
    assert r["waiting"] == "waiting" and r["profilesWhileReach"] == 0 and r["requestsWhileReach"] == 1
    assert max(min(f % 1, 1 - f % 1) for f in r["freeFrac"]) > 0.02, r["freeFrac"]
    assert len(r["free"]["profiles"]) == 1 and r["free"]["reach"] == "1"
    # then the moved anchor 2's reach, asked as the profile's line gives it
    assert [a for a, _ in r["free"]["requests"]] == [1, 2]
    assert r["free"]["requests"][1][1] == ",".join(r["free"]["profiles"][0]["line"].split(",")[2:4])
    # the snapped anchor rests on a sample's centre inside the valid ring; beyond the ring it stays
    s = r["snapped"]
    assert s["moved"] and max(min(f % 1, 1 - f % 1) for f in s["frac"]) < 0.05, s
    assert 20 <= s["d"] <= 0.9 * r["length"] + 0.5, s
    assert r["stays"] is True
    # back to the found line: both reaches asked again, with the found anchors, anchor 1's showing
    assert r["afterReset"] == "" and [a for a, _ in r["reset"]["requests"]] == [1, 2] and r["reset"]["reach"] == "1"
    assert [q[1] for q in r["reset"]["requests"]] == [f"{lat1:.7f},{lon1:.7f}", f"{lat2:.7f},{lon2:.7f}"]
    # the overlay is drawn: more triangles in the frame, many pixels changed against the first frame
    assert r["lit"]["triangles"] > 1.3 * r["lit"]["base"] and r["lit"]["different"] > 1000, r["lit"]
    assert r["overlaps"] == [0, 1], r["overlaps"]
    assert all(q["step"] == "1" and q["header"] == "1" and q["run"] == meta["id"] for q in r["all"])
    # off: the overlay gone, the hint hidden; a request in flight when it went off is dropped
    assert r["off"]["pressed"] == "false" and r["off"]["reach"] == "" and r["off"]["notes"] == [True, True]
    assert r["off"]["triangles"] == r["lit"]["base"] and r["off"]["different"] < 0.02 * r["lit"]["pixels"], r["off"]
    assert r["offInFlight"]["requests"] == 1 and r["offInFlight"]["reach"] == "" and r["offInFlight"]["pillHidden"] is True
    assert r["offInFlight"]["triangles"] == r["lit"]["base"], r["offInFlight"]
    assert not [e for e in r["errors"] if "TypeError" in e or "Failed" in e], r["errors"]
