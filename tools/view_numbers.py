"""
Run by hand: how the numbers of the result view's map pile up (docs/roadmap.md, step 3c's list, item 2; the rule:
docs/line-volume/spec-view.md B.2 item 8). The page places a number (B1 … of the best spots, P1 … of the picks at
the Area level) on the longest free piece of its line, at the first of seven places that is a box (32 × 23 px) away
from every number placed before it, else at the farthest of them, and leaves it out when even that place is nearer
than a quarter of a box (viewer/src/result/SpotMap.ts, `badge` in `draw`). This tool counts, in each state of the
view, how many numbers the view wants to draw, how many it draws, how many it leaves out, and for the rules
"left out when nearer than a third / a half of a box" and "never left out (only for want of a free piece)" how many
would be drawn and how many pairs of drawn numbers would overlap by more than a quarter, a third and a half of a
box's area. It has no pass or fail: the user picks the rule from the numbers.

How (no hook added to the page, and the page's rule is not changed): in each state, two frames after it settled,
one script reads the live canvas (window.FINDALINE_VIEW.map, whose private members the browser tests read too:
`ends`, `freeParts`, `freeBox`, `marks`) and returns, for each number the view wants to draw in the page's order,
its kind, half sizes and every place the page would try (the free pieces × the seven fractions; none: no free
piece). Python then runs the page's greedy again for each rule, from scratch (which numbers are kept changes where
the later ones land). A state is measured only when the greedy at a quarter gives exactly the page's own numbers
(labels and places: `today_matches`); else it is recorded as not measured, with the difference.
- "Lines from here" (the fan): its own numbers sit at 0.82 of their line's first free piece, and the page leaves
  none out for want of distance (today's rule there: B numbers at a quarter among themselves, the fan's never). The
  other rules here are a stated definition: a fan number, after the B numbers, is left out when its one place is
  nearer than the rule's distance to a number placed before it; the rule "quarter" applies the page's quarter to
  the fan's numbers too.
- Overlap: the intersection of two numbers' boxes (each shape's bounding box: B 25 × 21 px, B10 and over 30 × 21,
  P 38 × 27, L 35 × 21; SpotMap.markSize) over the smaller box's own area; the JSON keeps the pixels too.
- The states: for each run, each device (tools/ui_shots.py's DEVICES and profiles: desktop 1400 × 900, iPhone 13
  in WebKit, Pixel 7 in Chromium), at the view's first view and `--zooms` whole zoom levels in from it (default 1
  and 2: the zoom button is half a level; `--around centre`, the default: around the middle of the part of the map
  a person sees; `--around best`: with the run's best spot's shown line put there), each of `--best`
  (default 10, 30, 100) under Auto, and the fan at Best 10: "Lines from here" opened (through the view's model, as
  the browser tests do) at the first anchor of the first spot in view, in the list's order, whose fan has at least
  two rows. Where Auto shows the Area level (Best does nothing there: P numbers only) the state is recorded once,
  and the Spots level held is measured as well, as labelled extras ("held").
- A phone's sheet stays low, as the view opens; the numbers' places are counted in the map's own pixels.

Runs: `--runs` names run folders (a path holding run.json) or runs by name, looked for in <data>/runs/ and then in
the reference folder (--reference-dir, default <data>/local/reference-runs), as tools/perf_reach.py's find_run.
Each run's store files and run.json are COPIED into a scratch data folder (--data-dir, kept; else a temporary one,
removed): nothing is written to a run's own folder. A run without a store holding the view's columns cannot open
in the view and is reported as left out, with the reason. Runs are named by their folder's name only (`--label
NAME=LABEL` for a shorter one; a folder named after its place's coordinates, a search without a name, by its label
or "run N" alone); the output holds no coordinates (places of numbers are the map box's pixels; a phone's pictures
start under its top bar, which names the run) and no seconds.

`--sheets`: per run and device, for the map state that left out the most numbers today and for the fan state with
the most numbers, a picture of the page as drawn, and one per rule: the page's map with its own numbers taken out
(the canvas told that no line has a free piece, the legend's listeners paused so the legend keeps its rows) and the
rule's numbers drawn over it in the page's own shapes and font; the four rules side by side at equal size in
<out>/sheets/<run>-<device>-<state>.png. The pictures load the base map's tiles (OpenTopoMap, OpenStreetMap).

    uv sync --group ui; uv run playwright install chromium webkit; cd viewer; npm ci; node build.mjs   (once)
    uv run tools/view_numbers.py --out <folder> --runs <run> [<run> ...] [--data <data folder>]
                                 [--reference-dir <folder>] [--devices desktop,iphone,pixel] [--best 10,30,100]
                                 [--zooms 1,2] [--around centre|best] [--sheets] [--data-dir <scratch>]

Writes <out>/view_numbers.json and view_numbers.md (and pictures/, sheets/). Exit code 1 when a state was not
measured. Run it under tools/test_lock.py (shared lane: it counts, it times nothing).
"""

import argparse
import contextlib
import gc
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

BOX = (32.0, 23.0)  # px: the box a number keeps from the others (SpotMap.ts badge)
FRACTIONS = (0.5, 0.36, 0.64, 0.24, 0.76, 0.14, 0.86)  # of a free piece, tried in this order (badge)
FAN_AT = 0.82  # of the first free piece toward the far end: a fan number's one place
TODAY = "today"
# A rule: the distance (in boxes) under which a B or P number is left out, and the fan numbers' (None: never)
RULES = {
    "today": (0.25, None),     # the page: a quarter of a box; the fan's own numbers never left out
    "quarter": (0.25, 0.25),   # a quarter, the fan's numbers too (differs from today only in the fan)
    "third": (1 / 3, 1 / 3),
    "half": (0.5, 0.5),
    "never": (None, None),     # only a number without a free piece is left out
}
SHEET_RULES = ("today", "third", "half", "never")  # the four pictures of a sheet (the user's choice)
OVERLAPS = ((">1/4", 0.25), (">1/3", 1 / 3), (">1/2", 0.5))
DEVICE_NAMES = ("desktop", "iphone", "pixel")
WAIT_MS = 30000
SETTLE_ROUNDS = 40
STORE_COPY = ("lines.arrow", "profiles.arrow", "run.json", "ATTRIBUTION.txt")  # what the view reads of a run
REFERENCE_DIR = os.path.join("local", "reference-runs")
TOKEN = "view-numbers"
FLAG = "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}"
TEMP_PREFIX = "ui-shots-numbers-"  # tools/clean_temp.py removes the ui-shots-* folders of runs that did not end
# A run folder named after its place's coordinates ("..._50-15624-19-75569_..."): never written into an output
COORDINATES = re.compile(r"\d+-\d{3,}-\d+-\d{3,}")


# ------------------------------------------------------------------------------------------------- the placement

def place(numbers: list, rule: str) -> list:
    """The page's greedy (SpotMap.ts badge) under `rule` (RULES), from scratch: each number of `numbers` (in the
    page's order: dicts with `label`, `kind`, `w`, `h`, `cand` [[x, y], ...] in the tried order, `fan`) gets
    `status` "drawn" (with `x`, `y`), "no room" (no free piece: no place to try) or "left out" (its best place
    nearer than the rule's distance to a number placed before), and `apart` (in boxes). A fan number has one
    place and is checked against every number placed before it; with a rule of None it is never left out."""
    badge_min, fan_min = RULES[rule]
    placed, out = [], []
    for n in numbers:
        result = {"label": n["label"], "kind": n["kind"], "w": n["w"], "h": n["h"], "fan": n["fan"]}
        if not n["cand"]:
            out.append({**result, "status": "no room", "apart": None})
            continue
        at, apart = None, -1.0
        for x, y in n["cand"]:
            near = 1e9
            for q in placed:
                near = min(near, max(abs(q[0] - x) / BOX[0], abs(q[1] - y) / BOX[1]))
            if near > apart:
                apart, at = near, (x, y)
            if apart >= 1:
                break
        least = fan_min if n["fan"] else badge_min
        if least is not None and apart < least:
            out.append({**result, "status": "left out", "apart": apart})
            continue
        placed.append(at)
        out.append({**result, "status": "drawn", "x": at[0], "y": at[1], "apart": apart})
    return out


def overlap_area(a: dict, b: dict) -> float:
    """The intersection of two drawn numbers' boxes, px²."""
    ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"] - a["w"], b["x"] - b["w"])
    iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"] - a["h"], b["y"] - b["h"])
    return max(0.0, ix) * max(0.0, iy)


def overlaps(placed: list) -> dict:
    """The pairs of drawn numbers whose boxes overlap: their count over each share of OVERLAPS (of the smaller box's
    own area), any overlap at all, and each pair (labels, px², the share of the smaller box, of the 32 × 23 box)."""
    drawn = [n for n in placed if n["status"] == "drawn"]
    pairs = []
    for i, a in enumerate(drawn):
        for b in drawn[i + 1:]:
            area = overlap_area(a, b)
            if area > 0:
                smaller = min(4 * a["w"] * a["h"], 4 * b["w"] * b["h"])
                pairs.append({"a": a["label"], "b": b["label"], "px2": round(area, 1), "of_smaller": round(area / smaller, 4),
                              "of_box": round(area / (BOX[0] * BOX[1]), 4)})
    counts = {name: sum(1 for p in pairs if p["of_smaller"] > share) for name, share in OVERLAPS}
    return {"any": len(pairs), **counts, "pairs": pairs}


def summary_of(numbers: list, rule: str) -> dict:
    """A rule's counts in a state: drawn, left out, no room, and the overlaps of the drawn ones."""
    placed = place(numbers, rule)
    status = [n["status"] for n in placed]
    return {"drawn": status.count("drawn"), "left_out": status.count("left out"), "no_room": status.count("no room"),
            "overlaps": overlaps(placed), "placed": placed}


def today_matches(numbers: list, marks: list, tolerance: float = 1e-6):
    """Does the greedy at today's rule give exactly the page's own numbers (labels in order, places within
    `tolerance` px)? (True, "") or (False, the first difference)."""
    drawn = [n for n in place(numbers, TODAY) if n["status"] == "drawn"]
    if [n["label"] for n in drawn] != [m["label"] for m in marks]:
        return False, f"labels {[n['label'] for n in drawn]} against the page's {[m['label'] for m in marks]}"
    for n, m in zip(drawn, marks):
        if abs(n["x"] - m["x"]) > tolerance or abs(n["y"] - m["y"]) > tolerance:
            return False, f"{n['label']} placed apart from the page's by {abs(n['x'] - m['x']):.3g}, {abs(n['y'] - m['y']):.3g} px"
    return True, ""


# ------------------------------------------------------------------------------------------------- the page

# What the canvas would place now: per number the view wants to draw, in the page's order, the places it tries; the
# page's own numbers (SpotMap.marks); the state. Layer pixels as the canvas keeps them (`pane` turns them into the
# map box's pixels). The half sizes are SpotMap.markSize's, kept in step (today_matches fails when they differ).
COLLECT_JS = r"""() => {
  const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP;
  const F = %s, AT = %s;
  const half = (kind, text) => [kind === "P" ? 19 : kind === "L" ? 17.5 : kind === "A" ? 10.5 : text.length > 2 ? 15 : 12.5,
                                kind === "P" ? 13.5 : 10.5];
  const p = new Float64Array(4), level = view.level, v = view.inView, fan = view.fan, inFan = new Set();
  if (fan) for (const r of fan.rows) if (r.label[0] !== "L") inFan.add(r.row);
  const badge = (row, text, kind) => {
    map.ends(row, p);
    const ax = p[0], ay = p[1], bx = p[2], by = p[3], [w, h] = half(kind, text), cand = [];
    for (const part of map.freeParts(ax, ay, bx, by, w, h))
      for (const f of F) { const s = part[0] + (part[1] - part[0]) * f; cand.push([ax + (bx - ax) * s, ay + (by - ay) * s]); }
    return {label: text, kind, w, h, cand, fan: false};
  };
  const numbers = [];
  if (level === "area") {
    for (const pick of view.picks()) if (!inFan.has(pick.row)) numbers.push(badge(pick.row, "P" + pick.n, "P"));
  } else if (!(v.refused > 0) && !(level === "lines" && view.best === "all") && v.numbered) {
    for (let r = 0; r < v.best.length; r++) { const row = view.shownOf(v.best[r]); if (!inFan.has(row)) numbers.push(badge(row, "B" + (r + 1), "B")); }
  }
  if (fan) for (const r of fan.rows) {
    map.ends(r.row, p);
    const near = r.near === 1 ? 0 : 2, far = 2 - near, kind = r.label[0] === "L" ? "L" : r.label[0], [w, h] = half(kind, r.label);
    const parts = map.freeParts(p[near], p[near + 1], p[far], p[far + 1], w, h), cand = [];
    if (parts.length) { const s = parts[0][0] + (parts[0][1] - parts[0][0]) * AT;
      cand.push([p[near] + (p[far] - p[near]) * s, p[near + 1] + (p[far + 1] - p[near + 1]) * s]); }
    numbers.push({label: r.label, kind, w, h, cand, fan: true});
  }
  const pane = leaflet._getMapPanePos(), f = map.freeBox();
  return {level, auto: view.auto, best: view.best, mpp: view.mpp, zoom: leaflet.getZoom(), m: v.m, numbered: v.numbered,
          refused: v.refused, fanRows: fan ? fan.rows.length : null, fanLines: fan ? fan.lines : null, numbers,
          marks: map.marks.map((k) => ({label: k.text, kind: k.kind, x: k.x, y: k.y, w: k.w, h: k.h})),
          pane: [pane.x, pane.y], free: [f.left, f.top, f.right, f.bottom], dim: !!(view.selected || fan)};
}""" % (json.dumps(FRACTIONS), FAN_AT)

# Two frames and a turn of the event loop (the canvas places the numbers again after a frame when a control changed
# its size), then what says the state rests: the numbers, the free part, the level and the zoom
FRAMES_JS = "() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))))"
SIGNATURE_JS = r"""() => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP;
  return JSON.stringify([map.marks.map((k) => [k.text, Math.round(k.x * 100), Math.round(k.y * 100)]), map.free.sig, view.level,
    view.best, leaflet.getZoom(), !!leaflet._animatingZoom, view.fan ? view.fan.rows.length : -1,
    document.querySelector('.u-sheet') ? Math.round(document.querySelector('.u-sheet').getBoundingClientRect().top) : 0]); }"""
# The page's short timers pending (tools/ui_shots.py WATCH, an init script of the page): the frame takes the view's
# rectangle again 120 ms after a control's size changed (SpotColumns.tsx useFootClear), and the numbers move then
TIMERS_JS = "() => window.__uiShots ? window.__uiShots.timers : 0"
NO_TIMERS_JS = "() => !(window.__uiShots ? window.__uiShots.timers : 0)"
# The first view's centre and zoom, and where the stops zoom in: around the middle of the part of the map a person
# sees ("centre"), or with the run's best spot's shown line (the list's first) put there ("best")
FIRST_JS = r"""(around) => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, f = map.freeBox();
  const c = view.model.data.columns, row = view.shownOf(view.order[0]);
  window.__vn = {centre: leaflet.getCenter(), zoom: leaflet.getZoom(), around,
                 at: leaflet.containerPointToLatLng([(f.left + f.right) / 2, (f.top + f.bottom) / 2]),
                 best: {lat: (c.lat1.at(row) + c.lat2.at(row)) / 2, lng: (c.lon1.at(row) + c.lon2.at(row)) / 2}};
  return {zoom: leaflet.getZoom(), maxZoom: leaflet.getMaxZoom()}; }"""
# A zoom stop: the first view again, then k levels in (FIRST_JS's `around`); Auto, Best 10, nothing selected
STOP_JS = r"""(k) => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, s = window.__vn;
  view.closeFan(); view.select(null); view.setLevel('auto'); view.setBest(10);
  leaflet.setView(s.centre, s.zoom, {animate: false});
  if (k && s.around === 'best') {
    leaflet.setView(s.best, s.zoom + k, {animate: false});
    const f = map.freeBox(), p = leaflet.latLngToContainerPoint(s.best);
    leaflet.panBy([Math.round(p.x - (f.left + f.right) / 2), Math.round(p.y - (f.top + f.bottom) / 2)], {animate: false});
  } else if (k) leaflet.setZoomAround(s.at, s.zoom + k, {animate: false});
  return leaflet.getZoom() - s.zoom; }"""
# "Lines from here" at the first anchor of the first spot in view (the list's order) whose fan has two rows or more;
# the map put back after each fan too small
FAN_JS = r"""(limit) => { const {view} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, c = view.model.data.columns;
  const centre = leaflet.getCenter(), zoom = leaflet.getZoom(), spots = Array.from(view.inView.spots).slice(0, limit);
  for (let k = 0; k < spots.length; k++) {
    const row = view.shownOf(spots[k]);
    view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1});
    if (view.fan && view.fan.rows.length >= 2) return {tried: k + 1, rows: view.fan.rows.length};
    view.closeFan();
    leaflet.setView(centre, zoom, {animate: false});
  }
  return null; }"""
FAN_TRIES = 60
# The page's map without its numbers (no line has a free piece; the legend's listeners paused so it keeps its rows),
# and back
BARE_JS = r"""(on) => { const {map} = window.FINDALINE_VIEW;
  if (on) { window.__vnListeners = Array.from(map.listeners); map.listeners.clear(); map.freeParts = () => []; }
  else { delete map.freeParts; for (const f of window.__vnListeners || []) map.listeners.add(f); }
  map.paint(true); }"""
# Numbers drawn over the map in the page's shapes, colours and font (SpotMap.ts shapePath, mark: the map box's
# pixels; `alpha` the canvas's dimming while a fan is open); an empty list takes the overlay away
OVERLAY_JS = r"""(nums) => { const leaflet = window.FINDALINE_MAP, box = leaflet.getContainer().getBoundingClientRect();
  let c = document.getElementById('vn-overlay');
  if (!nums.length) { if (c) c.remove(); return; }
  if (!c) { c = document.createElement('canvas'); c.id = 'vn-overlay'; document.body.appendChild(c); }
  const dpr = Math.min(2, window.devicePixelRatio || 1);  // the canvas's own (SpotMap.ts Draw)
  Object.assign(c.style, {position: 'fixed', left: box.left + 'px', top: box.top + 'px', width: box.width + 'px',
                          height: box.height + 'px', zIndex: '2147483647', pointerEvents: 'none'});
  c.width = Math.round(box.width * dpr); c.height = Math.round(box.height * dpr);
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, box.width, box.height);
  for (const n of nums) {
    const x = n.x, y = n.y, w = n.w, h = n.h;
    ctx.globalAlpha = n.alpha; ctx.beginPath();
    if (n.kind === 'P') { ctx.moveTo(x, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x, y + h); ctx.lineTo(x - w, y); ctx.closePath(); }
    else if (n.kind === 'L') { ctx.moveTo(x - w + 6, y - h); ctx.lineTo(x + w - 6, y - h); ctx.lineTo(x + w, y);
      ctx.lineTo(x + w - 6, y + h); ctx.lineTo(x - w + 6, y + h); ctx.lineTo(x - w, y); ctx.closePath(); }
    else if (typeof ctx.roundRect === 'function') ctx.roundRect(x - w, y - h, 2 * w, 2 * h, 4);
    else ctx.rect(x - w, y - h, 2 * w, 2 * h);
    ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.lineWidth = 1.6; ctx.strokeStyle = '#1b2530'; ctx.stroke();
    ctx.fillStyle = '#1b2530'; ctx.font = '600 12px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(n.label, x, y + 0.5);
  }
  ctx.globalAlpha = 1; }"""
TILES_JS = "() => ![...document.querySelectorAll('.leaflet-tile:not(.leaflet-tile-loaded)')].some((t) => t.tagName !== 'IMG' || !t.complete)"


def settle(page, rounds: int = SETTLE_ROUNDS):
    """Wait until the view rests: drawn, no zoom moving, no short timer of the page pending (TIMERS_JS: each wait
    for one ends with its timer), and the same numbers, free part, level, zoom and sheet in two looks two frames
    apart. RuntimeError when it never rests within `rounds` looks."""
    page.wait_for_function("() => !!window.FINDALINE_VIEW && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT_MS)
    last = None
    for _ in range(rounds):
        page.wait_for_function(NO_TIMERS_JS, timeout=WAIT_MS)
        page.evaluate(FRAMES_JS)
        now = page.evaluate(SIGNATURE_JS)
        if now == last and not page.evaluate(TIMERS_JS):
            return
        last = now
    raise RuntimeError("the view did not rest")


def collect(page) -> dict:
    """The state as COLLECT_JS reads it: places in the canvas's layer pixels, as the page computes them (the greedy
    runs on them, so that it meets the page's own arithmetic), and `pane`, which turns them into the map box's
    pixels. Neither the layer's pixels nor `pane` (both depend on where the map is) go into an output."""
    return page.evaluate(COLLECT_JS)


def boxed(placed: list, pane: list) -> list:
    """Placed numbers with their places in the map box's pixels (rounded to 0.01 px), for the output."""
    out = []
    for n in placed:
        n = dict(n)
        if "x" in n:
            n["x"], n["y"] = round(n["x"] + pane[0], 2), round(n["y"] + pane[1], 2)
        out.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in n.items()})
    return out


def state_record(raw: dict, recipe: dict) -> dict:
    """A measured state: the recipe that made it, the view's state, every rule's counts, and whether the greedy
    reproduced the page (else not measured)."""
    ok, why = today_matches(raw["numbers"], raw["marks"])
    record = {**recipe, "level": raw["level"], "auto": raw["auto"], "best": raw["best"], "mpp": round(raw["mpp"], 3),
              "zoom": raw["zoom"], "in_view": raw["m"], "numbered": raw["numbered"], "refused": raw["refused"],
              "fan_rows": raw["fanRows"], "fan_lines": raw["fanLines"], "free": [round(v, 1) for v in raw["free"]],
              "wanted": len(raw["numbers"]), "wanted_fan": sum(1 for n in raw["numbers"] if n["fan"]),
              "candidates": [len(n["cand"]) for n in raw["numbers"]], "today_matches": ok}
    if not ok:
        record["error"] = "the greedy at a quarter differs from the page: " + why
        return record
    record["rules"] = {}
    for rule in RULES:
        s = summary_of(raw["numbers"], rule)
        record["rules"][rule] = {"drawn": s["drawn"], "left_out": s["left_out"], "no_room": s["no_room"],
                                 "overlaps": s["overlaps"], "placed": boxed(s["placed"], raw["pane"])}
    return record


def drive(page, recipe: dict):
    """Bring the page to a recipe's state (`stop`: levels in from the first view; `held`: a level held, else Auto;
    `best`; `fan`: "Lines from here" opened as FAN_JS) and let it rest; the fan's search result (or None)."""
    page.evaluate(STOP_JS, recipe["stop"])
    settle(page)
    if recipe.get("held"):
        page.evaluate("(l) => window.FINDALINE_VIEW.view.setLevel(l)", recipe["held"])
    page.evaluate("(b) => window.FINDALINE_VIEW.view.setBest(b)", recipe["best"])
    settle(page)
    found = None
    if recipe.get("fan"):
        found = page.evaluate(FAN_JS, FAN_TRIES)
        settle(page)
    return found


def measure_page(page, stops: list, bests: list, around: str = "centre") -> list:
    """Every state of one opened run on one device (the module's docstring; `around`: where the stops zoom in,
    FIRST_JS): their records."""
    first = page.evaluate(FIRST_JS, around)
    records = []
    for stop in [0] + list(stops):
        recipe = {"stop": stop, "held": None, "best": bests[0], "fan": False}
        reached = page.evaluate(STOP_JS, stop)
        settle(page)
        level = page.evaluate("() => window.FINDALINE_VIEW.view.level")
        if stop and reached < stop - 1e-9:  # the map's last zoom came first
            note = {"zoom_reached": reached}
        else:
            note = {}
        if level == "area":
            records.append({**state_record(collect(page), {**recipe, "case": "map"}), **note})
            for best in bests:
                r = {**recipe, "held": "spots", "best": best}
                drive(page, r)
                records.append({**state_record(collect(page), {**r, "case": "map"}), **note})
        else:
            for best in bests:
                r = {**recipe, "best": best}
                drive(page, r)
                records.append({**state_record(collect(page), {**r, "case": "map"}), **note})
        r = {**recipe, "best": bests[0], "fan": True}
        found = drive(page, r)
        if found is None:
            records.append({**r, "case": "fan", "left_out": f"no spot of the first {FAN_TRIES} in view has a fan of two rows", **note})
        else:
            records.append({**state_record(collect(page), {**r, "case": "fan"}), "fan_tried": found["tried"], **note})
    records.insert(0, {"first_view": first})
    return records


# ------------------------------------------------------------------------------------------------- pictures

def clip_of(page, free: list) -> dict:
    """The part of the map a person sees, in the viewport (CSS px), below a phone's top bar (which names the run:
    a run named after its place's coordinates would show them)."""
    box = page.evaluate("() => { const b = window.FINDALINE_MAP.getContainer().getBoundingClientRect(); "
                        "return [b.left, b.top, Math.max(-Infinity, ...[...document.querySelectorAll('.c-phone-top, .c-phone-top > *')]"
                        ".map((e) => e.getBoundingClientRect()).filter((r) => r.height).map((r) => r.bottom))]; }")
    y = max(box[1] + free[1], box[2])
    return {"x": box[0] + free[0], "y": y, "width": free[2] - free[0], "height": box[1] + free[3] - y}


def pictures(page, recipe: dict, out: str, stem: str) -> dict:
    """The state of `recipe` driven again; the page's own picture, then its map without numbers with each rule of
    SHEET_RULES drawn over it (and "quarter" in a fan state); the paths, and whether the numbers were the same as
    when they were counted."""
    drive(page, recipe)
    try:
        page.wait_for_function(TILES_JS, timeout=WAIT_MS)
    except Exception:  # an empty map is no finding: the pictures are taken all the same
        pass
    raw = collect(page)
    clip = clip_of(page, raw["free"])
    paths = {"page": os.path.join(out, f"{stem}-page.png")}
    page.screenshot(path=paths["page"], clip=clip, scale="css")
    rules = list(SHEET_RULES) + (["quarter"] if recipe.get("fan") else [])
    page.evaluate(BARE_JS, True)
    try:
        settle(page)
        bare = os.path.join(out, f"{stem}-bare.png")
        page.screenshot(path=bare, clip=clip, scale="css")
        paths["bare"] = bare
        for rule in rules:
            placed = [n for n in place(raw["numbers"], rule) if n["status"] == "drawn"]
            px, py = raw["pane"]
            nums = [{"label": n["label"], "kind": n["kind"], "x": n["x"] + px, "y": n["y"] + py, "w": n["w"], "h": n["h"],
                     "alpha": 0.55 if raw["dim"] and not n["fan"] else 1} for n in placed]
            page.evaluate(OVERLAY_JS, nums)
            page.evaluate(FRAMES_JS)
            paths[rule] = os.path.join(out, f"{stem}-{rule}.png")
            page.screenshot(path=paths[rule], clip=clip, scale="css")
        page.evaluate(OVERLAY_JS, [])
    finally:
        page.evaluate(BARE_JS, False)
    settle(page)
    return {"paths": paths, "numbers": [m["label"] for m in collect(page)["marks"]]}


def sheet(paths: dict, captions: dict, rules: list, target: str):
    """The rules' pictures side by side at equal size, each with its caption above."""
    from PIL import Image, ImageDraw, ImageFont
    images = [Image.open(paths[r]).convert("RGB") for r in rules]
    w = max(i.width for i in images)
    h = max(i.height for i in images)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:  # an older Pillow
        font = ImageFont.load_default()
    head, gap = 44, 12
    out = Image.new("RGB", (len(images) * w + (len(images) - 1) * gap, h + head), "white")
    draw = ImageDraw.Draw(out)
    for k, (rule, image) in enumerate(zip(rules, images)):
        x = k * (w + gap)
        out.paste(image, (x, head))
        for line, text in enumerate(captions[rule].split("\n")[:2]):
            draw.text((x + 4, 4 + 18 * line), text, fill="black", font=font)
    out.save(target)


def picture_diff(a: str, b: str) -> dict:
    """How far two pictures of the same size differ: the share of pixels that differ by more than 48 in a channel
    (the page's own picture against the bare map with today's numbers drawn over it)."""
    from PIL import Image, ImageChops
    x, y = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if x.size != y.size:
        return {"size": [x.size, y.size]}
    d = ImageChops.difference(x, y).convert("L").point(lambda v: 255 if v > 48 else 0)
    return {"pixels_apart": round(d.histogram()[255] / (x.width * x.height), 5)}


# ------------------------------------------------------------------------------------------------- the site

def find_run(run: str, data: str | None, reference: str | None) -> str:
    """A run's folder: `run` itself when it holds run.json, else <data>/runs/<run>, else <reference>/<run> (default
    <data>/local/reference-runs). SystemExit naming the places looked at when none holds it."""
    if os.path.isfile(os.path.join(run, "run.json")):
        return os.path.abspath(run)
    places = []
    if data:
        places.append(os.path.join(data, "runs", run))
        places.append(os.path.join(reference or os.path.join(data, REFERENCE_DIR), run))
    elif reference:
        places.append(os.path.join(reference, run))
    for folder in places:
        if os.path.isfile(os.path.join(folder, "run.json")):
            return folder
    raise SystemExit(f"the run {run} is in none of {places or ['(give --data or --reference-dir)']}")


def view_columns(folder: str) -> str | None:
    """Why a run cannot open in the view, or None: a store (run.json's block "store") whose lines.arrow names the
    view's column `spot` (tools/ui_shots.py run_features)."""
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if not meta.get("store"):
        return "the run has no store (saved before the store): the view cannot open it"
    import ui_shots
    if not ui_shots.store_has_view(folder):
        return "the run's store has no columns of the result view"
    return None


def copy_run(folder: str, data: str) -> str:
    """The run's store files and run.json copied into <data>/runs/<its folder's name> (never a link: nothing of
    the run's own folder can be written); its id."""
    run = os.path.basename(os.path.normpath(folder))
    target = os.path.join(data, "runs", run)
    if os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(target)):
        return run
    os.makedirs(target, exist_ok=True)
    for name in STORE_COPY:
        source = os.path.join(folder, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(target, name))
    return run


def ready_folder(data: str):
    """The viewer installed into the data folder's runs/ and its runs.js written (as a run's save does)."""
    import mapping
    import runs as rn
    runs = os.path.join(data, "runs")
    os.makedirs(runs, exist_ok=True)
    mapping.install_viewer(runs)
    rn.write_index(runs)


@contextlib.contextmanager
def serve(data: str):
    """The local app over a data folder on a free port of 127.0.0.1 (no worker); yields its address."""
    import uvicorn
    import web
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web.create_app(data, token=TOKEN, port=port, start_scheduler=False),
                                           host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)


def open_view(context, url: str, run: str):
    """The run's result view in a new page of `context` (the view's flag set): the page, once the view rests."""
    import ui_shots
    page = context.new_page()
    page.add_init_script(FLAG)
    page.add_init_script(ui_shots.WATCH)  # the page's short timers counted (settle)
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(f"{url}/?ui=c#run={run}")
    page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT_MS)
    settle(page)
    return page


def default_launch(pw, engine: str):
    return getattr(pw, engine).launch()


def measure_runs(runs: list, out: str, data: str, devices: list, stops: list, bests: list, sheets: bool = False,
                 launch=default_launch, labels: dict | None = None, around: str = "centre") -> dict:
    """Every run of `runs` (folders) on every device: the result (also written to <out>/view_numbers.json and
    .md). `launch(pw, engine)`: the browser of an engine (ui_shots.DEVICES' "chromium" or "webkit")."""
    os.makedirs(out, exist_ok=True)
    result = {"rules": {k: list(v) for k, v in RULES.items()}, "overlaps": [n for n, _ in OVERLAPS], "stops": stops, "around": around,
              "best": bests, "devices": devices, "runs": []}
    shown = []
    for k, folder in enumerate(runs):
        name = os.path.basename(os.path.normpath(folder))
        label = (labels or {}).get(name) or (name if not COORDINATES.search(name) else f"run {k + 1}")
        # a run named after its place's coordinates (a search without a name) is named by its label alone
        entry = {"run": name if not COORDINATES.search(name) else label, "label": label}
        why = view_columns(folder)
        if why:
            entry["left_out"] = why
        else:
            run_id = copy_run(folder, data)  # not in the output: it may name the place
            with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
                meta = json.load(f)
            entry["lines"] = (meta.get("store") or {}).get("lines")
            params = meta.get("params") or {}
            entry["rig"] = {k: params.get(k) for k in ("model", "fall_zone", "end_zone", "anchor_lift", "same_line_side",
                                                        "access", "resolution")}
            shown.append((entry, run_id))
        result["runs"].append(entry)
    if not shown:
        write(out, result)
        return result
    import ui_shots
    from playwright.sync_api import sync_playwright
    ready_folder(data)
    with serve(data) as url, sync_playwright() as pw:
        for device in devices:
            engine = ui_shots.DEVICES[device][0]
            browser = launch(pw, engine)
            try:
                for entry, run_id in shown:
                    context = ui_shots.pass_context(browser, pw, device, "light")
                    try:
                        page = open_view(context, url, run_id)
                        states = measure_page(page, stops, bests, around)
                        entry.setdefault("devices", {})[device] = {"first_view": states[0]["first_view"], "states": states[1:]}
                        if sheets:
                            entry["devices"][device]["pictures"] = pictures_of(page, states[1:], out, entry["label"], device)
                        entry["devices"][device]["page_errors"] = [e.replace(run_id, entry["label"]) for e in page.errors]
                    except Exception as error:
                        line = (str(error).splitlines() or [""])[0][:300].replace(run_id, entry["label"])
                        entry.setdefault("devices", {})[device] = {"error": f"{type(error).__name__}: {line}"}
                    finally:
                        context.close()
                    print(f"{entry['label']} on {device}: done", flush=True)
            finally:
                browser.close()
    write(out, result)
    return result


def of_interest(states: list):
    """The map state that left out the most numbers today (then the most wanted) and the fan state with the most
    numbers: their records (None where there is none)."""
    measured = [s for s in states if s.get("rules")]
    maps = [s for s in measured if s["case"] == "map"]
    fans = [s for s in measured if s["case"] == "fan"]
    best_map = max(maps, key=lambda s: (s["rules"][TODAY]["left_out"], s["wanted"]), default=None)
    best_fan = max(fans, key=lambda s: (s["wanted"], s["rules"]["never"]["overlaps"]["any"]), default=None)
    return best_map, best_fan


def caption(state: dict, rule: str) -> str:
    r = state["rules"][rule]
    o = r["overlaps"]
    name = {"today": "today: left out under 1/4 box", "quarter": "1/4 box, the fan's too", "third": "left out under 1/3 box",
            "half": "left out under 1/2 box", "never": "never left out"}[rule]
    return f"{name}\n{r['drawn']} of {state['wanted']} drawn; overlap pairs >1/4 {o['>1/4']}, >1/3 {o['>1/3']}, >1/2 {o['>1/2']}"


def pictures_of(page, states: list, out: str, label: str, device: str) -> list:
    """The sheets of a run on a device (of_interest's states): their paths and checks."""
    folder, sheets = os.path.join(out, "pictures"), os.path.join(out, "sheets")
    os.makedirs(folder, exist_ok=True)
    os.makedirs(sheets, exist_ok=True)
    made = []
    for state in of_interest(states):
        if state is None:
            continue
        recipe = {k: state[k] for k in ("stop", "held", "best", "fan")}
        stem = (re.sub(r"[^A-Za-z0-9._-]+", "-", label) + f"-{device}-{state['case']}-z{state['stop']}-b{state['best']}"
                + (f"-{state['held']}" if state["held"] else ""))
        shot = pictures(page, recipe, folder, stem)
        rules = list(SHEET_RULES)
        target = os.path.join(sheets, f"{stem}.png")
        sheet(shot["paths"], {r: caption(state, r) for r in RULES}, rules, target)
        same = shot["numbers"] == [n["label"] for n in state["rules"][TODAY]["placed"] if n["status"] == "drawn"]
        made.append({"state": recipe, "case": state["case"], "sheet": os.path.relpath(target, out),
                     "page": os.path.relpath(shot["paths"]["page"], out), "same_numbers_as_counted": same,
                     "today_over_bare_vs_page": picture_diff(shot["paths"]["page"], shot["paths"]["today"])})
    return made


# ------------------------------------------------------------------------------------------------- the report

def cell(state: dict, rule: str) -> str:
    r = state["rules"][rule]
    o = r["overlaps"]
    return f"{r['drawn']} ({o['>1/4']}/{o['>1/3']}/{o['>1/2']})"


def stop_name(state: dict) -> str:
    return "first view" if state["stop"] == 0 else f"+{state['stop']} zoom"


def markdown(result: dict) -> str:
    lines = ["# The view's numbers: how many are drawn, left out, overlapping (tools/view_numbers.py)", "",
             "Counts only, no seconds. A cell: numbers drawn (pairs of drawn numbers overlapping by more than 1/4 / "
             "1/3 / 1/2 of the smaller box's area). \"wanted\": the numbers the view tries to draw (B of the best "
             "spots in view, P of the picks at Area, the fan's rows); \"no room\": without a free piece of their "
             "line (the row keeps the number); \"left out\": by today's rule (nearer than 1/4 box). Rules: today "
             "(1/4 box; the fan's own numbers never), 1/3, 1/2, never (only for want of a free piece). Stops: the "
             f"first view and {', '.join('+' + str(s) for s in result['stops'])} whole zoom levels in ("
             + ("with the run's best spot's shown line in the middle of the map a person sees"
                if result.get("around") == "best" else "around the middle of the map a person sees")
             + "). \"held\": the Spots level held where Auto showed Area.", ""]
    for entry in result["runs"]:
        lines.append(f"## {entry['label']}" + (f" ({entry['run']})" if entry["label"] != entry["run"] else ""))
        if entry.get("left_out"):
            lines += ["", f"Left out: {entry['left_out']}.", ""]
            continue
        lines += ["", f"{entry.get('lines')} lines; rig as recorded: " +
                  ", ".join(f"{k} {v}" for k, v in entry["rig"].items() if v is not None) + ".", ""]
        for device, d in (entry.get("devices") or {}).items():
            if d.get("error"):
                lines += [f"**{device}**: not measured: {d['error']}", ""]
                continue
            lines += [f"**{device}**", "",
                      "| Stop | Case | Level | Best | Spots in view | Wanted | No room | Left out today | Today | 1/3 | 1/2 | Never |",
                      "|---|---|---|---|---:|---:|---:|---:|---|---|---|---|"]
            for s in d["states"]:
                level = s.get("level", "–") + (" (held)" if s.get("held") else "")
                best = s.get("best") if s.get("level") != "area" else "–"
                case = s["case"] + (f" ({s['fan_rows']} rows)" if s["case"] == "fan" and s.get("fan_rows") else "")
                if s.get("left_out"):
                    lines.append(f"| {stop_name(s)} | {case} | – | {best} | – | – | – | – | {s['left_out']} | | | |")
                    continue
                if not s.get("rules"):
                    lines.append(f"| {stop_name(s)} | {case} | {level} | {best} | {s['in_view']} | {s['wanted']} | – | – | not measured: {s.get('error')} | | | |")
                    continue
                today = s["rules"][TODAY]
                fan_q = f"; 1/4 fan too: {cell(s, 'quarter')}" if s["case"] == "fan" else ""
                lines.append(f"| {stop_name(s)} | {case} | {level} | {best} | {s['in_view']} | {s['wanted']} | "
                             f"{today['no_room']} | {today['left_out']} | {cell(s, 'today')}{fan_q} | {cell(s, 'third')} | "
                             f"{cell(s, 'half')} | {cell(s, 'never')} |")
            for p in d.get("pictures") or []:
                lines.append(f"- sheet {p['sheet']} (the page's own picture {p['page']}; numbers as counted: "
                             f"{p['same_numbers_as_counted']}; today's drawn over the bare map against the page: "
                             f"{p['today_over_bare_vs_page']})")
            lines.append("")
    return "\n".join(lines) + "\n"


def write(out: str, result: dict):
    with open(os.path.join(out, "view_numbers.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "view_numbers.md"), "w", encoding="utf-8") as f:
        f.write(markdown(result))


def not_measured(result: dict) -> int:
    """The states (and devices) not measured."""
    n = 0
    for entry in result["runs"]:
        for d in (entry.get("devices") or {}).values():
            n += 1 if d.get("error") else sum(1 for s in d.get("states", []) if not s.get("rules") and not s.get("left_out"))
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="the folder of view_numbers.json, .md, pictures/ and sheets/")
    p.add_argument("--runs", nargs="+", required=True, help="run folders, or runs by name (in --data's runs/, then --reference-dir)")
    p.add_argument("--data", help="the real data folder whose runs/ (and local/reference-runs) are read, never written")
    p.add_argument("--reference-dir", help="where a run is looked for after <data>/runs/ (default <data>/local/reference-runs)")
    p.add_argument("--label", action="append", default=[], help="NAME=LABEL: a run's short name in the report and the files")
    p.add_argument("--devices", default=",".join(DEVICE_NAMES), help="of: " + ", ".join(DEVICE_NAMES))
    p.add_argument("--best", default="10,30,100", help="the Best values measured (the first one is the fan's)")
    p.add_argument("--zooms", default="1,2", help="whole zoom levels in from the first view (besides the first view)")
    p.add_argument("--around", choices=("centre", "best"), default="centre",
                   help="the zoom stops: around the middle of the map a person sees, or the run's best spot put there")
    p.add_argument("--sheets", action="store_true", help="pictures and contact sheets of the states of interest")
    p.add_argument("--data-dir", help="a scratch data folder (kept; default: a temporary one, removed)")
    args = p.parse_args(argv)
    devices = [d for d in args.devices.split(",") if d]
    for device in devices:
        if device not in DEVICE_NAMES:
            p.error(f"unknown device {device!r}")
    bests = [int(b) for b in args.best.split(",") if b]
    stops = [float(z) if "." in z else int(z) for z in args.zooms.split(",") if z]
    labels = dict(item.split("=", 1) for item in args.label)
    folders = [find_run(r, args.data, args.reference_dir) for r in args.runs]
    data = args.data_dir or tempfile.mkdtemp(prefix=TEMP_PREFIX)
    try:
        result = measure_runs(folders, args.out, data, devices, stops, bests, args.sheets, labels=labels, around=args.around)
    finally:
        if not args.data_dir:
            gc.collect()
            shutil.rmtree(data, ignore_errors=True)
    print(os.path.join(args.out, "view_numbers.md"))
    return 1 if not_measured(result) else 0


if __name__ == "__main__":
    sys.exit(main())
