"""The page's side of "Lines from a point" (docs/3d-view-contract.md, "Round 2", point 9; viewer/src/view3d/options.ts,
fan.ts, optionlist.ts, point.ts, and what edit.ts, overlay.ts and reach.ts gained for it): in Node the candidates of a
hand-made mask, the representatives against an independent greedy grouping and `groupLines`, the trees-last rule,
FAN_MAX, the list's sorting, the click's test and the lane's third slot; in headless Edge (from PowerShell) the tool on
the page of the local app, with /api/reach answered by the stub of tests/test_view3d_reach.py. main.ts is the
coordinator's: the Edge tests bundle the page themselves with the two lines that wire `createPoint` (a main.ts that
calls it already is taken as it is)."""

import json
import math
import os
import re
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_view3d_reach import (  # noqa: E402,F401
    LANE_PREAMBLE, STUB, encode, reach_literal, run_entry, small_mask)
from test_viewer import VIEWER, pytestmark, run_ts  # noqa: E402,F401 (the skip without Node)
from test_view3d import EDGE_SECONDS, VIRTUAL_BUDGET, _with_until  # noqa: E402 (the shared frame-counted waits)

ENTRY = "export * from './options'; export * from './reach'; export * from './optionlist'; export * from './fan'; " \
        "export {groupLines} from '../grouping';"


def random_mask(seed=3, shape=(50, 60)):
    rng = np.random.default_rng(seed)
    mask = np.zeros(shape, dtype=np.uint8)
    valid = rng.random(shape) < 0.45
    mask[valid] = rng.integers(1, 12, valid.sum())
    over = valid & (rng.random(shape) < 0.3)
    mask[over] |= 0x80
    return mask


def js_reach(mask, **meta):
    full = {"anchor": {"x": 1030.5, "y": 1975.5, "h": 400.0}}
    full.update(meta)
    return reach_literal(mask, **full)


def test_candidates_of_a_hand_made_mask(tmp_path):
    """candidates: one line from the fixed point to each valid sample's centre, in the mask's order (row by row),
    with the clearance in metres (steps of the quantum), the class (the high bit) and the distance; above the cap the
    samples of the largest clearance (ties by order), still in the mask's order; the lattice's centres."""
    mask = random_mask()
    mask[0, 0] = 127 | 0x80                                          # the corner sample, capped clearance, over trees
    found = run_entry(tmp_path, ENTRY, f"""
const reach = {js_reach(mask, lattice=2, res=0.5)};
const all = m.candidates(reach), capped = m.candidates(reach, 100), none = m.candidates({{meta: reach.meta, mask: new Uint8Array(50 * 60)}});
console.log(JSON.stringify({{all, capped, none}}));""")
    meta = {"lattice": 2, "res": 0.5, "left": 1000.0, "top": 2000.0}

    def centre(i, j):
        return (meta["left"] + (j * 2 + 0.5) * 0.5, meta["top"] - (i * 2 + 0.5) * 0.5)

    valid = [(i, j) for i in range(50) for j in range(60) if mask[i, j]]
    assert [(c["i"], c["j"]) for c in found["all"]] == valid and found["none"] == []
    for c in found["all"]:
        b = int(mask[c["i"], c["j"]])
        x, y = centre(c["i"], c["j"])
        assert (c["x1"], c["y1"]) == (1030.5, 1975.5) and (c["x2"], c["y2"]) == (x, y)
        assert c["clr"] == (b & 0x7F) * 0.5 and c["over"] == bool(b & 0x80) and c["hmax"] == 0
        assert c["len"] == pytest.approx(math.hypot(x - 1030.5, y - 1975.5), abs=1e-9)
    # the cap: the 100 of the largest clearance, ties by the samples' order
    ranked = sorted(valid, key=lambda ij: (-(int(mask[ij]) & 0x7F), ij))[:100]
    assert [(c["i"], c["j"]) for c in found["capped"]] == sorted(ranked)
    assert min(c["clr"] for c in found["capped"]) >= max(c["clr"] for c in found["all"] if (c["i"], c["j"]) not in ranked) - 1e-9
    assert any(c["clr"] == 63.5 and c["over"] for c in found["all"])


def greedy(lines, d):
    """An independent version of the grouping on lines that all start at one point: the lines clear of trees first,
    each pass best clearance first (then the longest), a group = the free lines whose both ends lie within d of the
    representative's, as they are or flipped."""
    d2 = d * d
    reps = []
    for over in (False, True):
        order = sorted([k for k, l in enumerate(lines) if l["over"] == over], key=lambda k: (-lines[k]["clr"], -lines[k]["len"]))
        used = set()
        for a in order:
            if a in used:
                continue
            reps.append(a)
            A = lines[a]
            for b in order:
                if b in used:
                    continue
                B = lines[b]
                sq = lambda p, q, r, s: (r - p) ** 2 + (s - q) ** 2  # noqa: E731
                same = sq(A["x1"], A["y1"], B["x1"], B["y1"]) <= d2 and sq(A["x2"], A["y2"], B["x2"], B["y2"]) <= d2
                flipped = sq(A["x2"], A["y2"], B["x1"], B["y1"]) <= d2 and sq(A["x1"], A["y1"], B["x2"], B["y2"]) <= d2
                if same or flipped:
                    used.add(b)
    return reps


@pytest.mark.parametrize("distance", [3.0, 6.5, 20.0])
def test_representatives_are_the_groups_first_lines(tmp_path, distance):
    """representatives: the first line of each of groupLines' groups over the same candidates (clear lines before
    lines over trees), as an independent greedy grouping gives them, with the group's size and the heights."""
    mask = random_mask()
    found = run_entry(tmp_path, ENTRY, f"""
const reach = {js_reach(mask)}, d = {distance};
const lines = m.candidates(reach), groups = m.groupLines(lines, d, "clearance");
const reps = m.representatives(reach, {{distance: d, max: 1000, heightAt: (x, y) => y > 1990 ? null : x * 0.1, h1: 5}});
console.log(JSON.stringify({{lines, groups: groups.map((g) => [g.rep.i, g.rep.j, g.members.length]),
  reps: reps.map((o) => [o.i, o.j, o.members, o.rank, null, o.h, o.dh, o.x2, o.y2, o.over])}}));""")
    lines = found["lines"]
    expected = greedy(lines, distance)
    assert [(lines[k]["i"], lines[k]["j"]) for k in expected] == [(g[0], g[1]) for g in found["groups"]]
    assert [(r[0], r[1], r[2]) for r in found["reps"]] == [tuple(g) for g in found["groups"]]
    assert [r[3] for r in found["reps"]] == list(range(len(found["reps"])))
    assert sum(r[2] for r in found["reps"]) == len(lines)         # every candidate is in exactly one group
    # lines clear of trees first
    flags = [r[9] for r in found["reps"]]
    assert flags == sorted(flags) and flags[0] is False and flags[-1] is True
    for r in found["reps"]:
        x2, y2 = r[7], r[8]
        assert (r[5] is None) == (y2 > 1990)
        if r[5] is not None:
            assert r[5] == pytest.approx(x2 * 0.1) and r[6] == pytest.approx(x2 * 0.1 - 5)
        else:
            assert r[6] is None


def test_lines_over_trees_come_last_and_the_fan_is_capped(tmp_path):
    """Lines over trees come after every line clear of trees even where they clear more; the fan holds FAN_MAX at
    most (and `max` where given), keeping the first of the order."""
    mask = np.zeros((60, 80), dtype=np.uint8)
    mask[:, :40] = 4 | 0x80                                          # the west half over trees, clearing more
    mask[:, 40:] = 2
    found = run_entry(tmp_path, ENTRY, f"""
const reach = {js_reach(mask)};
const few = m.representatives(reach, {{distance: 2}}), some = m.representatives(reach, {{distance: 2, max: 7}});
const wide = m.representatives(reach, {{distance: 500}});
console.log(JSON.stringify({{max: m.FAN_MAX, few: few.map((o) => [o.over, o.clr, o.rank]), some: some.length,
  wide: wide.map((o) => [o.over, o.clr, o.members])}}));""")
    assert found["max"] == 40 and len(found["few"]) == 40 and found["some"] == 7
    assert [f[0] for f in found["few"]] == [False] * 40 and all(f[1] == 1.0 for f in found["few"])
    # one big group per pass: the clear one first
    assert [w[0] for w in found["wide"]] == [False, True] and found["wide"][0][2] == 60 * 40 and found["wide"][1][2] == 60 * 40


def test_the_list_sorts_by_a_column(tmp_path):
    """sortOptions: by length, clearance, height difference (a missing value last either way), over trees (clear
    lines first), ties in the fan's order, the original untouched; groupingDistance, isClick, signedMetres."""
    found = run_entry(tmp_path, ENTRY, """
const o = (rank, len, clr, dh, over) => ({rank, len, clr, dh, over, x1: 0, y1: 0, x2: 0, y2: 0, hmax: 0, i: 0, j: 0, members: 1, h: 0});
const list = [o(0, 30, 2, 1.5, false), o(1, 50, 2, null, true), o(2, 40, 1, -2, false), o(3, 50, 3, 0.25, true), o(4, 20, 1, 4, false)];
const ranks = (key, desc) => m.sortOptions(list, key, desc).map((x) => x.rank);
console.log(JSON.stringify({
  rank: ranks("rank"), length: ranks("length"), lengthDesc: ranks("length", true), clear: ranks("clear"), clearDesc: ranks("clear", true),
  dh: ranks("dh"), dhDesc: ranks("dh", true), trees: ranks("trees"), treesDesc: ranks("trees", true), untouched: list.map((x) => x.rank),
  distance: [m.groupingDistance({res: 1}), m.groupingDistance({res: 25}), m.groupingDistance({res: 1, group_distance: 42}),
             m.groupingDistance({res: 1, group_distance: 0}), m.groupingDistance({res: 20, step: 2}), m.groupingDistance({res: 30, step: 2})],
  click: [m.isClick(10, 10, 10, 10), m.isClick(10, 10, 13, 14), m.isClick(10, 10, 14, 14), m.isClick(0, 0, 3, 3, 2)],
  slop: m.CLICK_SLOP_PX, signed: [1.04, -0.04, 3.25, -12.34, 0, -0.06].map(m.signedMetres)}));""")
    assert found["rank"] == [0, 1, 2, 3, 4] and found["untouched"] == [0, 1, 2, 3, 4]
    assert found["length"] == [4, 0, 2, 1, 3] and found["lengthDesc"] == [1, 3, 2, 0, 4]
    assert found["clear"] == [2, 4, 0, 1, 3] and found["clearDesc"] == [3, 0, 1, 2, 4]
    assert found["dh"] == [2, 3, 0, 4, 1] and found["dhDesc"] == [4, 0, 3, 2, 1]
    assert found["trees"] == [0, 2, 4, 1, 3] and found["treesDesc"] == [1, 3, 0, 2, 4]
    assert found["distance"] == [20, 50, 42, 20, 20, 30] and found["click"] == [True, True, False, False] and found["slop"] == 5
    assert found["signed"] == ["+1.0", "0.0", "+3.3", "−12.3", "0.0", "−0.1"]


def test_the_lane_serves_the_point_after_the_anchors_only_when_asked_first(tmp_path):
    """The lane's third slot (the picked point's reach): served in turn with the anchors' two (the slot first() names
    first, then by number), replaced by a newer ask, one request at a time beside the profile guard."""
    found = run_entry(tmp_path, "export * from './reach'; export * from './interact';", LANE_PREAMBLE + """
(async () => {
  const out = {};
  const sent = [], got = [], tasks = {};
  let first = 0;
  const lane = m.reachLane((slot) => { const t = task("reach" + slot, reachOf(slot)); sent.push(slot); tasks[slot] = t; return t.promise; },
    {got: (slot, r) => got.push(slot), failed: (slot, e) => got.push("fail" + slot), busy() {}}, () => first);
  lane.on = true;
  lane.hold(true);
  lane.want(m.POINT_SLOT); lane.want(1);
  lane.hold(false);
  await settle();
  out.second = sent.slice();                                  // slot 1 before the point: by number
  lane.want(m.POINT_SLOT);                                     // the point asked again while the other is in flight
  tasks[1].ok(); await settle();
  out.third = sent.slice();
  tasks[2].ok(); await settle();
  out.got = got.slice();
  first = m.POINT_SLOT;                                        // the point first when first() says so
  sent.length = 0;
  lane.hold(true); lane.want(0); lane.want(m.POINT_SLOT); lane.hold(false); await settle();
  out.first = sent.slice();
  tasks[2].ok(); await settle(); tasks[0].ok(); await settle();
  // the point's reach beside a profile request
  sent.length = 0;
  const p = lane.guard(() => { const t = task("profile", {}); tasks.p = t; return t.promise; });
  lane.want(m.POINT_SLOT); await settle();
  out.during = [sent.slice(), quick.now];
  tasks.p.ok(); await p; await settle();
  out.after = [sent.slice(), quick.now];
  tasks[2].ok(); await settle();
  out.max = quick.max;
  lane.stop();
  out.stopped = lane.on;
  console.log(JSON.stringify(out));
})();""")
    assert found["second"] == [1] and found["third"] == [1, 2] and found["got"] == [1, 2]
    assert found["first"] == [2] and found["during"] == [[], 1] and found["after"] == [[2], 1] and found["max"] == 1
    assert found["stopped"] is False


# ---- headless Edge (from PowerShell) -------------------------------------------------------------------------
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture)
from test_view3d_reach import CSP_STUB, EDGE, LOCAL, TOKEN, _lines_of, _server, _violations, web  # noqa: E402

WIRE = "createPoint(scene, line, edit);"

# The page's bundle with `createPoint` wired after `createViews` (a main.ts that wires it already is built as it is)
BUNDLE = """
const esbuild = require('esbuild'), fs = require('fs'), path = require('path');
const WIRE = %(wire)s, AFTER = 'createViews(scene, line, root, {parent: ui.bar, before: ui.note.nextElementSibling});';
esbuild.build({
  entryPoints: {view3d: 'src/view3d/main.ts'}, bundle: true, minify: false, format: 'iife', target: 'es2020',
  outdir: %(out)s, assetNames: '[name]-[hash]', logLevel: 'warning',
  loader: {'.png': 'dataurl', '.svg': 'text', '.woff2': 'file'},
  plugins: [{name: 'wire', setup(build) {
    build.onLoad({filter: /view3d[\\\\/]main\\.ts$/}, (args) => {
      let text = fs.readFileSync(args.path, 'utf8');
      if (!text.includes('createPoint')) {
        if (!text.includes(AFTER)) throw new Error('createViews call not found in main.ts');
        text = 'import { createPoint } from "./point";\\n' + text.replace(AFTER, AFTER + '\\n    ' + WIRE);
      }
      return {contents: text, loader: 'ts', resolveDir: path.dirname(args.path)};
    });
  }}],
}).catch((e) => { console.error(String(e)); process.exit(1); });
"""


def _point_page(data, name: str, script: str) -> str:
    """The app's /view3d page with the stubs before its bundle (rebuilt with createPoint wired, in runs/<name>/) and
    `script` after it."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB + STUB, encoding="utf-8")
    (folder / "test.js").write_text(script, encoding="utf-8")
    subprocess.run(["node", "-e", BUNDLE % {"wire": json.dumps(WIRE), "out": json.dumps(str(folder))}], cwd=VIEWER, check=True)
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    tag = '<script src="/app/view3d.js"></script>'
    assert tag in page and '<link rel="stylesheet" href="/app/view3d.css">' in page
    page = page.replace('<link rel="stylesheet" href="/app/view3d.css">', '<link rel="stylesheet" href="view3d.css">')
    (folder / "index.html").write_text(page.replace(tag, f'<script src="stubs.js"></script><script src="view3d.js"></script>'
                                                         f'<script src="test.js"></script>'), encoding="utf-8")
    return f"runs/{name}/index.html"


HELPERS = _with_until("""
(function () {
  const R = window.REACH, root = () => document.getElementById("view3d");
  const H = window.H = {out: {errors: [], trace: []}};
  const error = console.error.bind(console);
  console.error = (...args) => { H.out.errors.push(args.map(String).join(" ").slice(0, 300)); error(...args); };
  addEventListener("error", (e) => H.out.errors.push("uncaught: " + String(e.message).slice(0, 300)));
  addEventListener("unhandledrejection", (e) => H.out.errors.push("rejected: " + String(e.reason).slice(0, 300)));
  // synthetic pointers have no capture to take: the orbit controls would stop at setPointerCapture
  for (const name of ["setPointerCapture", "releasePointerCapture"]) Element.prototype[name] = function () {};
  // the waits count the browser's frames (test_view3d.UNTIL_JS), its own requestAnimationFrame taken here
  /* until */
  H.t0 = Date.now();
  H.raf = 0;
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (fn) => raf((time) => { H.raf++; fn(time); });
  H.sum = () => { const d = H.snapshot(); let n = 0; for (let i = 0; i < d.length; i += 97) n += d[i]; return n; };
  H.trace = (label) => H.out.trace.push([label, Number(document.getElementById("view3d").dataset.frames), H.raf, Date.now() - H.t0,
                                         Number(document.getElementById("view3d").dataset.triangles), H.sum()]);
  H.done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(H.out);
    document.body.appendChild(pre);
  };
  H.waitFor = (test, ms) => new Promise((resolve) => until(test, ms, resolve));
  H.sleep = (ms) => new Promise((resolve) => until(() => false, ms, resolve));
  // at least one frame drawn after this call (true), or none within ms (false)
  H.next = (ms) => {
    const r = root(), frames = r.dataset.frames;
    return H.waitFor(() => r.dataset.frames !== frames, ms);
  };
  // the frame a change asked for comes late here (the last state of the canvas is one change behind): wait for the
  // next frame, then for ten polls (each over one of the browser's frames) without one
  H.settle = async (ms) => {
    await H.next(6000);
    return new Promise((resolve) => settledOn(() => root().dataset.frames, ms, resolve));  // ten polls, none drawn
  };
  H.pointer = (type, target, x, y, id = 7) => target.dispatchEvent(new PointerEvent(type, {clientX: x, clientY: y,
    pointerId: id, button: 0, buttons: type === "pointerup" ? 0 : 1, bubbles: true, cancelable: true, isPrimary: true}));
  H.canvas = () => document.querySelector("canvas.v3-canvas");
  H.snapshot = () => {
    const c = H.canvas(), t = document.createElement("canvas");
    t.width = c.width; t.height = c.height;
    const g = t.getContext("2d");
    g.drawImage(c, 0, 0);
    return g.getImageData(0, 0, t.width, t.height).data;
  };
  H.diff = (a, b) => {
    let count = 0;
    for (let i = 0; i < a.length; i += 4) {
      if (Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]) > 24) count++;
    }
    return count;
  };
  // a click on the canvas at a fraction of its size: a press and a release at the same place
  H.click = (fx, fy, id = 7) => {
    const c = H.canvas(), r = c.getBoundingClientRect(), x = r.left + r.width * fx, y = r.top + r.height * fy;
    H.pointer("pointerdown", c, x, y, id);
    H.pointer("pointerup", c, x, y, id);
    return [x, y];
  };
  H.rect = (selector) => {
    const e = document.querySelector(selector);
    if (!e || e.classList.contains("v3-hidden")) return null;
    const r = e.getBoundingClientRect();
    return r.width && r.height ? {left: r.left, top: r.top, right: r.right, bottom: r.bottom} : null;
  };
  // a zero-sized element (the marker) is shown when it is not hidden and has been placed
  H.placed = (selector) => {
    const e = document.querySelector(selector);
    return !!e && !e.classList.contains("v3-hidden") && e.style.transform !== "";
  };
  H.hit = (a, b) => !!a && !!b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  H.rows = () => [...document.querySelectorAll(".v3-opt-row")];
  H.dots = () => [...document.querySelectorAll(".v3-opt-dot")];
  H.lengths = () => H.rows().map((r) => parseFloat(r.children[0].textContent));
  H.ready = async () => {
    H.out.ready = await H.waitFor(() => root().dataset.ready === "1", 25000);
    H.out.settled = await H.settle(15000);
    H.out.tools = [...document.querySelectorAll(".v3-tools .v3-tool")].map((b) => b.dataset.tool);
  };
  H.reachState = () => ({data: root().dataset.reach, point: root().dataset.point, fan: root().dataset.fan,
                         triangles: Number(root().dataset.triangles)});
})();
""")

POINT_SCRIPT = """
(async function () {
  const H = window.H, R = window.REACH, out = H.out, root = document.getElementById("view3d");
  const handles = () => [...document.querySelectorAll(".v3-handle")];
  const gridOf = (lat, lon) => R.inverse(R.meta.affine, lon, lat);
  try {
    await H.ready();
    const tool = document.querySelector('[data-tool="point"]');
    out.handles = handles().length;
    if (!tool) { H.done(); return; }
    const base = H.snapshot(), baseState = H.reachState(), p0 = R.profiles.length;
    out.base = baseState;
    out.total = base.length / 4;
    out.label = tool.textContent.trim();
    out.pressed0 = tool.getAttribute("aria-pressed");
    out.point0 = root.dataset.point;
    out.panel0 = H.rect(".v3-optlist");

    // 1. a click while the tool is off asks nothing; on: the hint, the picking cursor
    H.click(0.62, 0.55);
    await H.sleep(500);
    out.requests0 = R.requests.length;
    tool.click();
    out.pressed1 = tool.getAttribute("aria-pressed");
    out.point1 = root.dataset.point;
    out.hint = (document.querySelector(".v3-optlist-note") || {}).textContent;
    out.panelHint = H.rect(".v3-optlist");
    out.picking = document.querySelector(".v3-stage").classList.contains("v3-picking");

    // 2. a drag turns the camera and asks nothing
    const before = H.snapshot(), c = H.canvas(), r = c.getBoundingClientRect(), x = r.left + r.width * 0.4, y = r.top + r.height * 0.5;
    H.pointer("pointerdown", c, x, y);
    H.pointer("pointermove", c, x + 60, y + 10);
    H.pointer("pointermove", c, x + 140, y + 20);
    H.pointer("pointerup", c, x + 140, y + 20);
    H.trace("dragged");
    await H.settle(15000);
    H.trace("drag settled");
    out.drag = {different: H.diff(before, H.snapshot()), requests: R.requests.length, point: root.dataset.point};
    // a press with a modifier is not a pick either
    c.dispatchEvent(new PointerEvent("pointerdown", {clientX: x, clientY: y, pointerId: 7, button: 0, bubbles: true, isPrimary: true, shiftKey: true}));
    c.dispatchEvent(new PointerEvent("pointerup", {clientX: x, clientY: y, pointerId: 7, button: 0, bubbles: true, isPrimary: true, shiftKey: true}));
    await H.sleep(300);
    out.shift = R.requests.length;

    // 3. a click picks a point: its reach is asked (held at the server meanwhile: the pill, the marker)
    R.gate = new Promise((resolve) => { R.open = resolve; });
    out.click = H.click(0.55, 0.6);
    await H.waitFor(() => R.requests.length >= 1, 8000);
    const pill = document.querySelector(".v3-activity");
    out.pill = [!pill.classList.contains("v3-hidden"), pill.textContent];
    out.first = R.requests[0];
    out.waitingNote = (document.querySelector(".v3-optlist-note") || {}).textContent;
    out.marker = H.placed(".v3-point-marker");
    out.pointWhileWaiting = root.dataset.point;
    R.open();
    R.gate = null;
    await H.waitFor(() => root.dataset.point !== "0" && root.dataset.point !== "", 25000);
    await H.settle(15000);
    H.trace("answered");
    H.trace("answered+settled");
    out.shown = H.reachState();
    out.rowsN = H.rows().length;
    out.dotsN = H.dots().length;
    out.title = (document.querySelector(".v3-optlist-title") || {}).textContent;
    out.over = H.rows().map((row) => row.classList.contains("v3-over"));
    H.trace("snapshot");
    out.pixels = H.diff(base, H.snapshot());
    out.pillHidden = document.querySelector(".v3-activity").classList.contains("v3-hidden");
    out.markerAt = H.placed(".v3-point-marker");

    // 4. the panel clears the tool strip, the pill (when it shows), the credits and the card; it scrolls inside itself
    const panel = H.rect(".v3-optlist"), stage = H.rect(".v3-stage");
    out.geometry = {panel, stage, tools: H.rect(".v3-tools"), credits: H.rect(".v3-credits"), bottom: H.rect(".v3-bottom"), card: H.rect(".v3-card"),
                    pill: H.rect(".v3-activity"), scroll: (() => { const s = document.querySelector(".v3-optlist-scroll"); return [s.scrollHeight, s.clientHeight, getComputedStyle(s).overflowY]; })()};
    out.geometry.hits = ["tools", "credits", "card", "bottom", "pill"].map((k) => H.hit(panel, out.geometry[k]));

    // 5. hovering a row marks its webbing and its dot; leaving takes the marks away
    H.trace("before hover");
    const rows = H.rows(), still = H.snapshot(), k = Math.min(3, rows.length - 1);
    rows[k].dispatchEvent(new PointerEvent("pointerenter", {bubbles: false}));
    await H.settle(15000);
    H.trace("after hover");
    out.hover = {row: rows[k].classList.contains("v3-on"), dots: H.dots().filter((d) => d.classList.contains("v3-on")).map((d) => d.dataset.rank),
                 rank: rows[k].dataset.rank, pixels: H.diff(still, H.snapshot())};
    rows[k].dispatchEvent(new PointerEvent("pointerleave", {bubbles: false}));
    await H.settle(15000);
    out.unhover = {rows: rows.filter((row) => row.classList.contains("v3-on")).length, dots: H.dots().filter((d) => d.classList.contains("v3-on")).length,
                   pixels: H.diff(still, H.snapshot())};
    // a dot marks its row
    const dot = H.dots()[1];
    dot.dispatchEvent(new PointerEvent("pointerenter", {bubbles: false}));
    out.dotHover = {dot: dot.dataset.rank, row: H.rows().filter((row) => row.classList.contains("v3-on")).map((row) => row.dataset.rank)};
    dot.dispatchEvent(new PointerEvent("pointerleave", {bubbles: false}));

    // 6. a click on a column's head sorts the rows; again reverses; the rank order comes back with a new list
    const order = () => H.rows().map((row) => Number(row.dataset.rank));
    out.byRank = order();
    const head = (key) => document.querySelector('.v3-opt-sort[data-sort="' + key + '"]');
    head("length").click();
    out.byLength = {lengths: H.lengths(), aria: head("length").parentElement.getAttribute("aria-sort")};
    head("length").click();
    out.byLengthAsc = {lengths: H.lengths(), aria: head("length").parentElement.getAttribute("aria-sort")};
    head("trees").click();
    out.byTrees = H.rows().map((row) => row.classList.contains("v3-over"));
    head("clear").click();
    out.byClear = H.rows().map((row) => row.children[1].textContent);

    // 7. a click on the terrain again replaces the list; the tool stays on
    const previous = R.requests.length;
    H.click(0.45, 0.62);
    await H.waitFor(() => R.requests.length > previous, 8000);
    await H.waitFor(() => R.active === 0, 25000);
    await H.settle(15000);
    out.second = {requests: R.requests.length - previous, point: root.dataset.point, rows: H.rows().length, dots: H.dots().length, last: R.requests[R.requests.length - 1]};
    out.secondOrder = order();

    // 8. a click on a row makes it the line: the anchors are the point and the target, the tool goes off, the profile is asked
    const rowsNow = H.rows(), pick = rowsNow[Math.min(2, rowsNow.length - 1)], rank = Number(pick.dataset.rank);
    const lengthText = pick.children[0].textContent;
    const reachRequest = R.requests[R.requests.length - 1];
    pick.click();
    await H.waitFor(() => R.profiles.length > p0, 25000);
    out.chosen = {pressed: tool.getAttribute("aria-pressed"), point: root.dataset.point, fan: root.dataset.fan, panel: H.rect(".v3-optlist"),
                  dots: H.dots().length, marker: H.placed(".v3-point-marker"), reach: root.dataset.reach, edit: root.dataset.edit,
                  picking: document.querySelector(".v3-stage").classList.contains("v3-picking"), length: lengthText, rank};
    await H.waitFor(() => root.dataset.edit === "checked" || root.dataset.edit === "error", 25000);
    const line = R.profiles[R.profiles.length - 1].line.split(",").map(Number), a = gridOf(line[0], line[1]), b = gridOf(line[2], line[3]);
    const [lat, lon] = reachRequest.anchor.split(",").map(Number), p = gridOf(lat, lon);
    out.line = {first: Math.hypot(a[0] - p[0], a[1] - p[1]), length: Math.hypot(b[0] - a[0], b[1] - a[1]), profiles: R.profiles.length - p0,
                readout: (document.querySelector(".v3-readout") || {}).textContent};
    await H.settle(15000);
    out.afterChoice = H.reachState();
    out.afterChoicePixels = H.diff(base, H.snapshot());
    out.overlaps = [R.overlaps, R.max];
    out.headers = R.requests.map((q) => [q.as, q.step, q.headers["X-Findaline-Reach"]]);

    // 9. the tool again, then off without a choice (the button, and Escape): everything of it goes
    tool.click();
    H.click(0.55, 0.6);
    await H.waitFor(() => R.active === 0 && root.dataset.point !== "0", 25000);
    out.reopened = {point: root.dataset.point, rows: H.rows().length};
    tool.click();
    await H.settle(15000);
    out.off = {pressed: tool.getAttribute("aria-pressed"), point: root.dataset.point, fan: root.dataset.fan, reach: root.dataset.reach, rows: H.rows().length,
               dots: H.dots().length, panel: H.rect(".v3-optlist"), marker: H.placed(".v3-point-marker"), triangles: Number(root.dataset.triangles)};
    tool.click();
    H.click(0.5, 0.55);
    await H.waitFor(() => R.active === 0 && root.dataset.point !== "0", 25000);
    dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
    out.escape = {pressed: tool.getAttribute("aria-pressed"), point: root.dataset.point, panel: H.rect(".v3-optlist")};
    out.overlaps2 = [R.overlaps, R.max];
  } catch (e) {
    out.exception = String((e && e.stack) || e);
  }
  H.done();
})();
"""


def _run_edge(data, tmp_path, meta, page, level, window="1280,800", budget=VIRTUAL_BUDGET):
    row = _lines_of(data, meta["id"])[0]
    line = ",".join(f"{v:.7f}" for v in row[:4])
    with _server(data, start_scheduler=True) as port:
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             f"--window-size={window}", f"--virtual-time-budget={budget}", "--force-prefers-no-reduced-motion", "--dump-dom",
             f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={line}"],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    r = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    return r, dom


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_lines_from_a_point(clip_data, tmp_path, monkeypatch, level):
    """The tool `point` at level full (none at the phone level): a click picks a point and asks one reach (as=1, the
    point's lat/lon, the header), the pill and a note meanwhile, then data-point is the number of representatives,
    the list has that many rows and the fan that many webbings (dots), the overlay shows the point's reach; a drag
    turns the camera and asks nothing; the panel clears the tool strip, the pill, the credits and the card at
    1280 x 800 and scrolls inside itself; a row marks its webbing and its dot marks its row; a column's head sorts;
    a second click replaces the list; a click on a row sets the line's anchors (the point and the target), switches
    the tool off, removes its overlay, fan and list and asks the profile; off without a choice and Escape remove
    everything; never two quick requests at once; no CSP violation."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    page = _point_page(data, "view3dpoint", HELPERS + POINT_SCRIPT)
    r, dom = _run_edge(data, tmp_path, meta, page, level)
    print(level, json.dumps(r, indent=1))
    assert r["ready"] and r["settled"] and "exception" not in r, r
    assert _violations(dom) == []
    if level == "phone":
        assert "point" not in r["tools"] and r["handles"] == 0
        return
    check_point(r)


def check_point(r):
    assert r["tools"][:2] == ["valid", "point"]
    assert r["label"] == "Lines from a point" and r["pressed0"] == "false" and r["point0"] == "" and r["panel0"] is None
    assert r["requests0"] == 0                                                   # a click with the tool off picks nothing
    assert r["pressed1"] == "true" and r["point1"] == "0" and r["hint"] == "Click a point on the terrain." and r["panelHint"]
    assert r["picking"] is True
    assert r["drag"]["different"] > 1000 and r["drag"]["requests"] == 0 and r["drag"]["point"] == "0"
    assert r["shift"] == 0
    # the click: one reach as the first end of the line, the point's lat/lon with 7 decimals, the header; the wait is shown
    first = r["first"]
    assert first["as"] == 1 and first["step"] == "1" and first["headers"] == {"X-Findaline-Reach": "1"}
    assert re.fullmatch(r"-?\d+\.\d{7},-?\d+\.\d{7}", first["anchor"])
    assert r["pill"] == [True, "Checking valid lines…"] and r["waitingNote"] == "Checking valid lines…" and r["marker"] is True
    assert r["pointWhileWaiting"] == "0"
    # the answer: the representatives (clear lines first), the list, the fan and the overlay
    n = int(r["shown"]["point"])
    assert 2 <= n <= 40, r["shown"]
    assert r["rowsN"] == n and r["dotsN"] == n and r["shown"]["fan"] == str(n)
    assert r["title"] == f"{n} lines from this point" and r["pillHidden"] is True and r["markerAt"] is True
    assert r["over"] == sorted(r["over"]) and r["over"][0] is False
    assert r["shown"]["data"] == "point" and r["shown"]["triangles"] > 1.3 * r["base"]["triangles"] and r["pixels"] > 1000
    g = r["geometry"]
    assert g["panel"] and g["stage"] and g["panel"]["right"] <= g["stage"]["right"] and g["panel"]["bottom"] <= g["stage"]["bottom"]
    assert g["hits"] == [False] * 5, g
    assert g["scroll"][2] in ("auto", "scroll")
    assert g["panel"]["bottom"] <= (g["bottom"]["top"] if g["bottom"] else g["stage"]["bottom"]) + 1
    # hovering
    assert r["hover"]["row"] is True and r["hover"]["dots"] == [r["hover"]["rank"]] and r["hover"]["pixels"] > 30
    assert r["unhover"] == {"rows": 0, "dots": 0, "pixels": r["unhover"]["pixels"]} and r["unhover"]["pixels"] < 30
    assert r["dotHover"]["row"] == [r["dotHover"]["dot"]]
    # sorting
    assert r["byRank"] == list(range(n))
    assert r["byLength"]["lengths"] == sorted(r["byLength"]["lengths"], reverse=True) and r["byLength"]["aria"] == "descending"
    assert r["byLengthAsc"]["lengths"] == sorted(r["byLengthAsc"]["lengths"]) and r["byLengthAsc"]["aria"] == "ascending"
    assert r["byTrees"] == sorted(r["byTrees"])
    clear = [float(re.sub(r"[^0-9.]", "", c)) for c in r["byClear"]]
    assert all(c.startswith("≤ ") and c.endswith(" m") for c in r["byClear"]) and clear == sorted(clear, reverse=True)
    # a second click replaces the list
    s = r["second"]
    assert s["requests"] == 1 and int(s["point"]) == s["rows"] == s["dots"] and r["secondOrder"] == list(range(s["rows"]))
    # a choice: the anchors are the point and the target, the tool goes off, its overlay, fan and list go
    c = r["chosen"]
    assert c["pressed"] == "false" and c["point"] == "" and c["fan"] == "" and c["panel"] is None and c["dots"] == 0
    assert c["marker"] is False and c["reach"] == "" and c["picking"] is False and c["edit"] in ("waiting", "checked")
    assert r["line"]["first"] < 0.05, r["line"]
    assert r["line"]["length"] == pytest.approx(float(c["length"].replace(" m", "")), abs=0.06)
    assert r["line"]["profiles"] == 1
    assert r["afterChoice"]["data"] == "" and r["afterChoice"]["triangles"] < 1.05 * r["base"]["triangles"]   # the moved webbing, no overlay
    # off without a choice, Escape
    assert r["reopened"]["point"] != "" and r["reopened"]["rows"] >= 2
    assert r["off"] == {"pressed": "false", "point": "", "fan": "", "reach": "", "rows": 0, "dots": 0, "panel": None, "marker": False,
                        "triangles": r["off"]["triangles"]}
    assert r["off"]["triangles"] < 1.05 * r["base"]["triangles"]
    assert r["escape"] == {"pressed": "false", "point": "", "panel": None}
    assert r["overlaps"][0] == 0 and r["overlaps"][1] == 1 and r["overlaps2"][0] == 0
    assert all(h[1] == "1" and h[2] == "1" for h in r["headers"])
    assert not [e for e in r["errors"] if "TypeError" in e or "Failed" in e], r["errors"]


SWITCH_SCRIPT = """
(async function () {
  const H = window.H, R = window.REACH, out = H.out, root = document.getElementById("view3d");
  try {
    await H.ready();
    const valid = document.querySelector('[data-tool="valid"]'), point = document.querySelector('[data-tool="point"]');
    const base = H.snapshot(), baseState = H.reachState(), p0 = R.profiles.length;
    out.total = base.length / 4;
    out.base = baseState;
    // the switch on: both reaches asked, anchor 1's overlay shows
    valid.click();
    await H.waitFor(() => R.requests.length >= 2 && R.active === 0, 25000);
    await H.settle(15000);
    out.switchOn = H.reachState();
    out.switchPixels = H.diff(base, H.snapshot());
    // the point tool on: the switch's overlay gives way (nothing shows until a point is picked)
    point.click();
    await H.settle(15000);
    out.pointOn = H.reachState();
    out.pointOnPixels = H.diff(base, H.snapshot());
    // two clicks at once: the second replaces the first (held at the server): one more request after the first, never two at a time
    const count = R.requests.length;
    R.gate = new Promise((resolve) => { R.open = resolve; });
    H.click(0.55, 0.6);
    await H.waitFor(() => R.requests.length > count, 8000);
    H.click(0.45, 0.62);
    H.click(0.6, 0.5);
    await H.sleep(500);
    out.held = R.requests.length - count;
    R.open();
    R.gate = null;
    await H.waitFor(() => R.requests.length >= count + 2 && R.active === 0 && root.dataset.point !== "0", 25000);
    await H.settle(15000);
    out.replaced = {requests: R.requests.slice(count).map((q) => [q.as, q.anchor]), point: root.dataset.point, rows: H.rows().length,
                    reach: root.dataset.reach, markers: document.querySelectorAll(".v3-point-marker").length};
    out.pointShown = H.reachState();
    // the tool off: the switch's overlay returns (its reaches are still there), no new request
    const before = R.requests.length;
    point.click();
    await H.settle(15000);
    out.pointOff = H.reachState();
    out.pointOffPixels = H.diff(base, H.snapshot());
    out.noNewRequests = R.requests.length - before;
    out.pressed = [valid.getAttribute("aria-pressed"), point.getAttribute("aria-pressed")];
    // the point tool on again with the switch on, a choice: the profile is asked, then the reaches of the moved anchors
    point.click();
    H.click(0.55, 0.6);
    await H.waitFor(() => R.active === 0 && root.dataset.point !== "0", 25000);
    const chosen = R.requests.length;
    H.rows()[1].click();
    await H.waitFor(() => R.profiles.length > p0 && root.dataset.edit === "checked", 25000);
    await H.waitFor(() => R.requests.length >= chosen + 2 && R.active === 0, 25000);
    await H.settle(15000);
    out.afterChoice = {state: H.reachState(), requests: R.requests.slice(chosen).map((q) => q.as), profiles: R.profiles.length - p0, edit: root.dataset.edit};
    out.overlaps = [R.overlaps, R.max];
    // the switch off with the point tool on: the point keeps the lane
    point.click();
    H.click(0.5, 0.58);
    await H.waitFor(() => R.active === 0 && root.dataset.point !== "0", 25000);
    valid.click();
    await H.settle(15000);
    out.switchOff = H.reachState();
    point.click();
    await H.settle(15000);
    out.allOff = H.reachState();
  } catch (e) {
    out.exception = String((e && e.stack) || e);
  }
  H.done();
})();
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_view3d_point_beside_only_valid_lines(clip_data, tmp_path, monkeypatch):
    """With "Only valid lines" on the point tool replaces its overlay while on (the switch's returns when the tool goes
    off, without new requests), a second click while a reach is in flight replaces it (the newest is asked after the
    first ends: never two requests at once), a choice moves the anchors so that the switch asks its reaches again after
    the profile, and the switch can go off while the tool keeps the lane."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    page = _point_page(data, "view3dpointswitch", HELPERS + SWITCH_SCRIPT)
    r, dom = _run_edge(data, tmp_path, meta, page, "full")
    print(json.dumps(r, indent=1))
    assert r["ready"] and r["settled"] and "exception" not in r, r
    assert _violations(dom) == []
    assert r["switchOn"]["data"] == "1" and r["switchOn"]["triangles"] > 1.3 * r["base"]["triangles"]
    # the switch's overlay is gone (the canvas is a line taller with its hint shown: the pixels are not comparable)
    assert r["pointOn"]["data"] == "" and r["pointOn"]["triangles"] == r["base"]["triangles"] and r["pointOn"]["point"] == "0"
    # the first click's request in flight, the later clicks wait: only the newest is asked after it
    assert r["held"] == 1
    assert [q[0] for q in r["replaced"]["requests"]] == [1, 1] and r["replaced"]["requests"][0][1] != r["replaced"]["requests"][1][1]
    assert int(r["replaced"]["point"]) == r["replaced"]["rows"] and r["replaced"]["markers"] == 1
    assert r["pointShown"]["data"] == "point"
    assert r["pointOff"]["data"] == "1" and r["pointOff"]["point"] == "" and r["noNewRequests"] == 0 and r["pressed"] == ["true", "false"]
    assert r["pointOff"]["triangles"] > 1.3 * r["base"]["triangles"]
    assert r["afterChoice"]["profiles"] == 1 and r["afterChoice"]["requests"] == [1, 2] and r["afterChoice"]["state"]["data"] == "1"
    assert r["overlaps"][0] == 0 and r["overlaps"][1] == 1
    assert r["switchOff"]["data"] == "point" and r["allOff"]["data"] == "" and r["allOff"]["point"] == "" and r["allOff"]["triangles"] == r["base"]["triangles"]
    assert not [e for e in r["errors"] if "TypeError" in e or "Failed" in e], r["errors"]
