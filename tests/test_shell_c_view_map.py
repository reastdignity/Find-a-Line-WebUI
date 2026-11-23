"""The result view's map (viewer/src/result/SpotMap.ts, view/MapBar.tsx, view/SpotColumns.tsx; step 3b of
docs/line-volume/spec-view.md part B) in Playwright's Edge over the app's server, offline, on a run of the Żabi Koń
clip in the target rig with the square rule and the access mark (clip_runs.view_clip: 7 934 lines in 164 spots).
The mock-up's own checks, ported (B.7): the spots in view and the best of them against a count in the map's own
pixels, the numbers (whole on the map, under no control, on their line, apart from each other), the presses (a
number's shape of each kind pressed and held, a line, an empty point, a right click and a press held for "Lines from
here", an anchor's circle, several spots under a finger and the table of spots), the 5 000 limit, the legend against
the shapes drawn, the squares, a phone's sheet and legend (no control covers another), the flag, a run without the
view's columns, storage blocked. Every wait is an event with a deadline (one exception: _tap). Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
from test_web import EDGE, _playwright, _server  # noqa: E402
sys.path.insert(0, os.path.join(REPO, "tools"))
import today_page  # noqa: E402  (the pin of today's page, whatever SpotColumns.tsx VIEW_DEFAULT is)
DEFAULT = today_page.view_default()  # is the result view the default (VIEW_DEFAULT; false until gate 2)

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
WAIT = 30000  # ms: the deadline of every wait for the page
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
SMALL_PHONE = {**PHONE, "viewport": {"width": 390, "height": 664}}  # tools/ui_shots.py's iPhone: the least room
SIDE_PHONE = {**PHONE, "viewport": {"width": 667, "height": 375}}  # a phone on its side: no room for the legend at all
OLD = "2026-10-26_090000_Old_00000000000000a1"  # the same run as one saved before the view's columns
FLAG = "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}"
LIMIT = 5000

with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    WORDS = json.load(_f)


@pytest.fixture(scope="module")
def view_clip(tmp_path_factory):
    import pyarrow as pa
    import clip_runs
    run = clip_runs.view_clip(tmp_path_factory, "view-map")
    # the view's columns come from the search (step 3a, mapping.view_columns): a checkout without it cannot show the view
    if "spot" not in pa.ipc.open_file(str(run / "lines.arrow")).schema.names:
        pytest.skip("this checkout's search does not write the result view's columns (step 3a)")
    return run


@pytest.fixture
def site(tmp_path, view_clip):
    """A data folder with the clip's run (BIG) and the same run with a store saved before the view's columns (OLD:
    tests/old_runs.py drop_view), served by the app; yields the address of the app's page."""
    import old_runs
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, OLD, "Old clip")
    old_runs.drop_view(folder / "runs" / OLD)
    page_path = stub_page(folder, "viewtest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


BOXES = "2026-10-30_100000_Boxes_00000000000000e3"  # the clip's run with an uncertain shore and coarser terrain


def _with_boxes(run):
    """The run's head given an uncertain shore (a segment of each kind) and coarser terrain (one region over the south
    half) over its lines' box, so both controls stand on the map, as a coastal run's would (tests/test_access_view.py's
    own, for this file's fixture)."""
    import pyarrow as pa
    import linestore
    from test_web import store_with
    with pa.OSFile(str(run / linestore.LINES_FILE), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    lat, lon = ([v / 10 ** int(table.schema.field(name).metadata[b"decimals"]) for v in table.column(name).to_pylist()]
                for name in ("lat1", "lon1"))
    s, n, w, e = min(lat), max(lat), min(lon), max(lon)
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2

    def ring(a, b, c, d):
        return [[a, b], [c, b], [c, d], [a, d], [a, b]]
    shore = {"rim_min": 5, "totals": {"surface_m": 420, "sea_m": 260, "surface_px": 60, "sea_px": 40},
             "segments": [{"kind": "surface", "px": 60, "m": 420, "ring": ring(w, s, mid_lon, mid_lat)},
                          {"kind": "sea", "px": 40, "m": 260, "ring": ring(mid_lon, mid_lat, e, n)}]}
    sources = {"land_km2": 0.3, "fallback_share": 0.3, "totals": {"fallback_km2": 0.09, "listed_km2": 0.09},
               "layers": [{"role": "source", "name": "Own", "resolution": 1.0, "share": 0.7},
                          {"role": "fallback", "name": "Coarse", "resolution": 10.0, "share": 0.3}],
               "regions": [{"layer": 1, "km2": 0.09, "rings": [ring(w, s, e, mid_lat)]}]}
    store_with(run, head={"shore": shore, "terrain_sources": sources})


@pytest.fixture
def boxes_site(tmp_path, view_clip):
    """A data folder with the clip's run given both boxes (BOXES), served by the app; the app page's address."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BOXES, "Clip with the boxes")
    _with_boxes(folder / "runs" / BOXES)
    page_path = stub_page(folder, "viewboxes")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


# The page's helpers of the checks: everything is counted in the map's own pixels from the lines' latitudes and
# longitudes (the page counts in grid metres through its fit)
HELPERS = r"""
window.T = {
  v() { return window.FINDALINE_VIEW; }, m() { return window.FINDALINE_MAP; },
  frames() { return new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0)))); },
  box() { return this.m().getContainer().getBoundingClientRect(); },
  // the part of the map's box a person sees: above a phone's sheet, above a desktop's profile card (the canvas's
  // covered term, step 3c)
  free() { const b = this.box(), sheet = document.querySelector(".u-sheet"), card = document.querySelector(".c-col-map > .r-card");
    let bottom = b.height;
    if (sheet) bottom = Math.min(bottom, sheet.getBoundingClientRect().top - b.top);
    if (card) bottom = Math.min(bottom, Math.round(card.getBoundingClientRect().top - b.top));
    return [0, 0, b.width, bottom]; },
  // a line's ends in the map's box, px (not rounded to whole pixels as Leaflet's own points are: a line that ends
  // within half a pixel of the view's edge would be counted on the wrong side of it)
  ends(row) { const c = this.v().view.model.data.columns, m = this.m(), origin = m.getPixelOrigin(), pane = m._getMapPanePos();
    const at = (lat, lon) => { const p = m.project([lat, lon]); return [p.x - origin.x + pane.x, p.y - origin.y + pane.y]; };
    return [...at(c.lat1.at(row), c.lon1.at(row)), ...at(c.lat2.at(row), c.lon2.at(row))]; },
  crosses([ax, ay, bx, by], [x0, y0, x1, y1]) { let t0 = 0, t1 = 1; const dx = bx - ax, dy = by - ay, p = [-dx, dx, -dy, dy], q = [ax - x0, x1 - ax, ay - y0, y1 - ay];
    for (let k = 0; k < 4; k++) { if (p[k] === 0) { if (q[k] < 0) return false; continue; } const r = q[k] / p[k];
      if (p[k] < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; } }
    return t1 > t0; },
  // does the run's search area's outline cross the part a person sees (the head's GeoJSON as Leaflet projects it)
  areaCrosses() { const m = this.m(), f = this.free(), rings = [], at = ([lon, lat]) => { const p = m.latLngToContainerPoint([lat, lon]); return [p.x, p.y]; };
    const walk = (o) => { if (!o) return; if (o.type === "Polygon") rings.push(...o.coordinates); else if (o.type === "MultiPolygon") o.coordinates.forEach((p) => rings.push(...p));
      else if (o.type === "Feature") walk(o.geometry); else if (o.type === "FeatureCollection") o.features.forEach((x) => walk(x.geometry)); else if (o.type === "GeometryCollection") o.geometries.forEach(walk); };
    walk(this.v().view.model.data.area);
    return rings.some((r) => r.some((p, k) => k > 0 && this.crosses([...at(r[k - 1]), ...at(p)], f))); },
  away(px, py, [ax, ay, bx, by]) { const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
    const f = l2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0; return Math.hypot(px - ax - f * dx, py - ay - f * dy); },
  // every control over the map, by its own class (not by the page's own list of them, `data-map-control`): Leaflet's
  // control containers, the bar's boxes, the frame's hint, the message, a phone's top bar, a desktop's profile card
  CONTROLS: ".v-map .leaflet-control, .v-levels, .v-best, .v-about-button, .v-status, .v-fold, .v-help-button, .v-help, .v-legend, .v-hint-slot > *, .v-toast, .c-phone-top > *, .c-col-map > .r-card",
  controls() { return [...document.querySelectorAll(this.CONTROLS)].map((e) => e.getBoundingClientRect()).filter((r) => r.width && r.height); },
  // the numbers of one kind on the map now: the middle of each in the viewport, its line and that line's spot
  numbersOf(kind) { const {view, map} = this.v();
    return map.drawn().numbers.filter((n) => n.label[0] === kind).map((n) => { const row = this.rowOf(n.label);
      return {label: n.label, x: (n.box.left + n.box.right) / 2, y: (n.box.top + n.box.bottom) / 2, row, spot: view.spotOf(row)}; }); },
  // "Lines from here" opened through the model at the first anchor of a spot's shown line, such that the map then
  // draws a number of the fan's own (L): that spot, else null
  fanWithL() { const {view, map} = this.v(), c = view.model.data.columns;
    for (const spot of Array.from(view.inView.spots)) { const row = view.shownOf(spot);
      view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1});
      if (map.drawn().numbers.some((n) => n.label[0] === "L")) return spot;
      view.closeFan(); }
    return null; },
  // a spot in view selected whose shown line has both anchors on the part of the map a person sees, r px clear of
  // every control: the spot, its line, and each anchor's point in the viewport with its place in the grid
  anchors(r) { const {view} = this.v(), box = this.box(), f = this.free(), controls = this.controls(), v = view.values;
    const free = (x, y) => x > f[0] + r && y > f[1] + r && x < f[2] - r && y < f[3] - r &&
      !controls.some((c) => x + box.left > c.left - r && x + box.left < c.right + r && y + box.top > c.top - r && y + box.top < c.bottom + r);
    for (const spot of Array.from(view.inView.spots)) { const row = view.shownOf(spot), e = this.ends(row);
      if (Math.hypot(e[2] - e[0], e[3] - e[1]) < 3 * r || !free(e[0], e[1]) || !free(e[2], e[3])) continue;
      view.select(spot);
      return {spot, row, ends: [{x: e[0] + box.left, y: e[1] + box.top, xy: [v.x1[row], v.y1[row]]}, {x: e[2] + box.left, y: e[3] + box.top, xy: [v.x2[row], v.y2[row]]}]}; }
    return null; },
  // the boxes of the map's controls by name (those on the page now), for "no control covers another"
  boxes() { const named = {status: ".v-status", legend: ".v-legend", fold: ".v-fold", help: ".v-help-button", levels: ".v-levels", best: ".v-best",
      info: ".v-about-button", coarse: ".v-map .u-coarse-ctl, .v-map .leaflet-control.u-coarse",
      zoom: ".v-map .leaflet-control-zoom", layers: ".v-map .leaflet-control-layers", chip: ".v-map .u-shore-ctl:not(.u-coarse-ctl)", scale: ".v-map .leaflet-control-scale",
      credits: ".v-map .leaflet-control-attribution", toast: ".v-toast", top: ".c-phone-top > *", hint: ".v-hint-slot > *",
      back: ".v-status .v-back-auto"}, out = {};
    for (const [name, selector] of Object.entries(named)) { const e = document.querySelector(selector), r = e && e.getBoundingClientRect();
      // the map's message on a phone is the first line of the status line's box (the pilot's arrangement): a part of it
      if (name === "toast" && e && e.closest(".v-status")) continue;
      if (r && r.width && r.height && getComputedStyle(e).visibility !== "hidden") out[name] = [r.left, r.top, r.right, r.bottom].map((v) => Math.round(v * 10) / 10); }
    return out; },
  // the line of a number on the map: B of a best spot, P of a pick, L of the fan, A of the selected line
  rowOf(label) { const {view} = this.v(), k = Number(label.slice(1));
    return label[0] === "B" ? view.shownOf(view.inView.best[k - 1]) : label[0] === "P" ? view.picks()[k - 1].row
      : label[0] === "L" ? view.fan.rows.find((r) => r.label === label).row : view.selected.row; },
  state() { const {view, map} = this.v(), v = view.inView, f = this.free(), box = this.box(), controls = this.controls(), d = map.drawn();
    const numbers = d.numbers.map((n) => { const b = n.box, cx = (b.left + b.right) / 2 - box.left, cy = (b.top + b.bottom) / 2 - box.top;
      const e = this.ends(this.rowOf(n.label)), end = Number(n.label.slice(1)) === 1 ? [e[0], e[1]] : [e[2], e[3]];
      return {label: n.label, x: cx, y: cy, w: b.width, h: b.height,
              off: n.label[0] === "A" ? Math.hypot(cx - end[0], cy - end[1]) : this.away(cx, cy, e),
              whole: b.left >= box.left + f[0] + 1 && b.right <= box.left + f[2] - 1 && b.top >= box.top + f[1] + 1 && b.bottom <= box.top + f[3] - 1,
              under: controls.some((c) => b.left < c.right + 1 && b.right > c.left - 1 && b.top < c.bottom + 1 && b.bottom > c.top - 1)}; });
    const sel = view.selected, fan = view.fan;
    return {level: view.level, auto: view.auto, best: view.best, m: v.m, spots: Array.from(v.spots), bestSpots: Array.from(v.best),
      inPixels: Array.from(view.order).filter((s) => this.crosses(this.ends(view.shownOf(s)), f)),
      numbered: v.numbered, refused: v.refused, thin: v.strokes, strokes: d.strokes, numbers, picks: view.picks().length,
      legend: [...document.querySelectorAll(".v-legend [data-kind]")].map((e) => e.dataset.kind), shapes: Object.keys(map.legend().shapes),
      runs: (map.legend().runs || []).length,
      status: document.querySelector(".v-status-text")?.textContent ?? null, bar: document.querySelector(".v-status")?.textContent ?? null,
      marked: !!document.querySelector(".v-status.v-refused"), mpp: view.mpp, zoom: this.m().getZoom(), size: [box.width, box.height], free: f,
      selected: sel && [sel.spot, sel.row], shown: sel && view.shownOf(sel.spot), fan: fan && {lines: fan.lines, rows: fan.rows.map((r) => [r.label, r.row]), xy: fan.xy},
      toast: document.querySelector(".v-toast")?.textContent ?? null, animating: !!this.m()._animatingZoom, target: this.m().getContainer().classList.contains("v-target"),
      counts: view.counts, made: view.model.madeLines, misses: view.fanMisses}; },
  // every passing line that crosses the view, counted in pixels (the Lines level with All)
  linesInView() { const {view} = this.v(), f = this.free(); let n = 0;
    for (let row = 0; row < view.count; row++) if (view.passes(row) && this.crosses(this.ends(row), f)) n++; return n; },
  // a point of the map on a line where a press takes exactly the spots `want` and no number's shape; null: none
  pointOn(row, want, finger) { const e = this.ends(row), {map} = this.v(), f = this.free(), controls = this.controls(), box = this.box();
    const marks = map.drawn().numbers.map((n) => n.box);
    for (let t = 0.08; t < 0.95; t += 0.03) { const x = Math.round(e[0] + (e[2] - e[0]) * t), y = Math.round(e[1] + (e[3] - e[1]) * t);
      if (x < f[0] + 24 || y < f[1] + 24 || x > f[2] - 24 || y > f[3] - 24) continue;
      const vx = x + box.left, vy = y + box.top, r = finger ? 24 : 4;
      if (controls.concat(marks).some((c) => vx > c.left - r && vx < c.right + r && vy > c.top - r && vy < c.bottom + r)) continue;
      const near = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]].map(([dx, dy]) => map.pickAt(x + dx, y + dy, !!finger).slice().sort().join());
      if (near.every((got) => got === want.slice().sort().join())) return {x: vx, y: vy, mx: x, my: y}; }
    return null; },
  // a point where a press reaches several spots (no number's shape within 24 px, no control within `gap` px), along
  // the lines in view
  crowded(finger, gap = 24) { const {view, map} = this.v(), f = this.free(), controls = this.controls(), box = this.box(), marks = map.drawn().numbers.map((n) => n.box);
    for (const spot of view.inView.spots) { const e = this.ends(view.shownOf(spot));
      for (let t = 0.1; t < 0.95; t += 0.05) { const x = Math.round(e[0] + (e[2] - e[0]) * t), y = Math.round(e[1] + (e[3] - e[1]) * t);
        if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
        const vx = x + box.left, vy = y + box.top;
        if (marks.some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
        if (controls.some((c) => vx > c.left - gap && vx < c.right + gap && vy > c.top - gap && vy < c.bottom + gap)) continue;
        const found = map.pickAt(x, y, !!finger);
        if (found.length > 1 && [[1, 0], [-1, 0], [0, 1], [0, -1]].every(([dx, dy]) => map.pickAt(x + dx, y + dy, !!finger).join() === found.join()))
          return {x: vx, y: vy, spots: found, at: this.m().containerPointToLatLng([x, y])}; } }
    return null; },
  // is a point of the viewport clear of every control and number by r px, and r px inside the part a person sees
  clear(vx, vy, r) { const box = this.box(), f = this.free(), marks = this.v().map.drawn().numbers.map((n) => n.box);
    if (vx - box.left < f[0] + r || vy - box.top < f[1] + r || vx - box.left > f[2] - r || vy - box.top > f[3] - r) return false;
    return !this.controls().concat(marks).some((c) => vx > c.left - r && vx < c.right + r && vy > c.top - r && vy < c.bottom + r); },
  // the first anchor of the shown line of one of `spots` that a press can reach on the map
  anchor(spots, r) { const {view} = this.v(), box = this.box(), c = view.model.data.columns;
    for (const spot of spots) { const row = view.shownOf(spot), e = this.ends(row);
      if (this.clear(e[0] + box.left, e[1] + box.top, r)) return {x: e[0] + box.left, y: e[1] + box.top, spot, row, lat: c.lat1.at(row), lng: c.lon1.at(row)}; }
    return null; },
  // a point of the map farther than 12 m from every passing line's ends (no line starts within 10 m of it)
  far() { const {view} = this.v(), box = this.box(), f = this.free(), {x1, y1, x2, y2} = view.values, leaflet = this.m();
    for (let y = f[3] - 30; y > f[1] + 30; y -= 13) for (let x = f[0] + 30; x < f[2] - 30; x += 19) {
      if (!this.clear(x + box.left, y + box.top, 20)) continue;
      const at = leaflet.containerPointToLatLng([x, y]), [gx, gy] = view.fit.toGrid(at.lat, at.lng);
      let near = false;
      for (let row = 0; row < view.count && !near; row++) near = view.passes(row) && (Math.hypot(x1[row] - gx, y1[row] - gy) < 12 || Math.hypot(x2[row] - gx, y2[row] - gy) < 12);
      if (!near) return {x: x + box.left, y: y + box.top}; }
    return null; },
  // an empty point of the map: no line in reach, no control, no number
  empty(finger) { const {map} = this.v(), f = this.free(), controls = this.controls(), box = this.box(), marks = map.drawn().numbers.map((n) => n.box);
    for (let y = f[3] - 40; y > f[1] + 40; y -= 17) for (let x = f[0] + 40; x < f[2] - 40; x += 23) { const vx = x + box.left, vy = y + box.top;
      if (controls.concat(marks).some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
      if (map.pickAt(x, y, !!finger).length === 0) return {x: vx, y: vy, mx: x, my: y}; }
    return null; },
};
"""


# A phone held sideways sees the notice "Turn your phone upright" over the whole page (the user's gate-2 answer 4 a):
# shown, with its words, over the page's middle; and the style that hides it, for a test that goes on with the
# layout under it (kept for a phone whose page is not locked, as one turned while the notice is up)
UPRIGHT_SHOWN = """() => { const n = document.querySelector('.v-upright'), hit = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
  return !!n && getComputedStyle(n).display !== 'none' && n.textContent.trim() === %s && !!hit && n.contains(hit); }""" % json.dumps(WORDS["ui.view.upright"])
# (a rule added through the CSSOM to the page's own sheet: the page's CSP refuses a <style> element; and the page's
# parts made inert behind the notice made reachable again, also when the page turns and the notice comes back)
UPRIGHT_HIDDEN = "() => { const sheet = [...document.styleSheets].find((x) => { try { return !!x.cssRules; } catch (e) { return false; } }); sheet.insertRule('.ui .v-result .v-upright { display: none !important; }', sheet.cssRules.length); const lift = () => document.querySelectorAll('.v-result > [inert]').forEach((e) => e.removeAttribute('inert')); lift(); new MutationObserver(lift).observe(document.body, {subtree: true, attributes: true, attributeFilter: ['inert']}); }"


def _upright_then_hidden(page):
    """The notice shown over the page (4 a), then hidden for the checks of the layout under it."""
    assert page.evaluate(UPRIGHT_SHOWN), "a phone on its side: no notice to turn it upright"
    page.evaluate(UPRIGHT_HIDDEN)
    page.evaluate("() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))")


def _open(browser, url: str, context: dict, flag: bool | None = True, script: str = "", requests: list | None = None):
    """The run's page with the page's helpers; with `flag` the result view is asked for and awaited; False: today's
    page pinned (tools/today_page.py); None: neither (the browser's default). `requests`, when given, gets the address
    of every request the page's context sends, from before the first (Playwright's request event: a second load of an
    address in one document is one more, which the page's resource timing does not list)."""
    ctx = browser.new_context(**context)
    if requests is not None:
        ctx.on("request", lambda request: requests.append(request.url))
    ctx.add_init_script(HELPERS + (FLAG if flag else today_page.SCRIPT if flag is False else "") + script)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    if flag:
        page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
    return page


def _tap(page, x: float, y: float):
    """A finger's tap that is a tap of its own: the browser counts a touch within its double-click time of the one before
    as a double click (measured in Edge: a click of detail 2 and a dblclick, which zooms the map by half a level), so
    the tap waits until that time has passed since the touch before it. This is the file's one wait for a time and
    it stays: the time is the browser's own, no event of the page ends it, and it can only slow a test down."""
    page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
    page.touchscreen.tap(x, y)
    page.evaluate("() => { window.TOUCHED = performance.now(); }")


def _tap_on(page, selector: str):
    """A finger's tap on an element, counted as the touch before the next _tap (see there)."""
    page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
    page.tap(selector)
    page.evaluate("() => { window.TOUCHED = performance.now(); }")


def _state(page, change: str = "") -> dict:
    """The page's state two frames after `change` (a script's body run in the page)."""
    if change:
        page.evaluate("() => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP; %s }" % change)
    page.evaluate("() => T.frames()")
    return page.evaluate("() => T.state()")


def _crowded(page, finger: bool, gap: int = 24):
    """A point of the map where a press reaches several spots, `gap` px clear of every control: in the view as it
    is, else with the map moved to one spot's shown line after another (the page's state settled each time)."""
    found = page.evaluate("([finger, gap]) => T.crowded(finger, gap)", [finger, gap])
    for spot in page.evaluate("() => Array.from(window.FINDALINE_VIEW.view.order)"):
        if found:
            break
        _state(page, f"const row = view.shownOf({spot}), c = view.model.data.columns; "
                     "leaflet.panTo([(c.lat1.at(row) + c.lat2.at(row)) / 2, (c.lon1.at(row) + c.lon2.at(row)) / 2], {animate: false});")
        found = page.evaluate("([finger, gap]) => T.crowded(finger, gap)", [finger, gap])
    return found


def _shape_presses(page, press, hold, reach: int):
    """A press and a hold on a number's shape of each kind (`press(x, y)`: a click, a tap; `hold(x, y, until)`: a
    right click, a finger held until the page's function holds): B, P and L select their line (a hold too: a
    number's shape is a press on it, never a point to ask "Lines from here" at); A1 and A2 open the lines from that
    anchor, the spot stays selected. `reach`: px an anchor keeps clear of the controls."""
    chosen = "() => window.FINDALINE_VIEW.view.selected !== null && window.FINDALINE_VIEW.view.fan === null"
    opened = "() => window.FINDALINE_VIEW.view.fan !== null && !window.FINDALINE_MAP._animatingZoom"
    misses = page.evaluate("() => window.FINDALINE_VIEW.view.fanMisses")  # no press here asks at an empty point

    def act(how, n, until):
        if how is press:
            press(n["x"], n["y"])
            page.wait_for_function(until, timeout=WAIT)
        else:
            hold(n["x"], n["y"], until)
        return _state(page)
    for level, kind in (("spots", "B"), ("area", "P")):
        for how in (press, hold):
            _state(page, f"view.closeFan(); view.select(null); view.setLevel('{level}');")
            numbers = page.evaluate("([kind]) => T.numbersOf(kind)", [kind])
            assert numbers, f"no {kind} number on the map"
            n = numbers[-1]
            now = act(how, n, chosen)
            assert now["selected"] == [n["spot"], n["row"]] and now["misses"] == misses, (kind, n, now["selected"])
    for how in (press, hold):
        _state(page, "view.closeFan(); view.select(null); view.setLevel('spots');")
        assert page.evaluate("() => T.fanWithL()") is not None, "no fan with a number of its own"
        fan = _state(page)
        numbers = page.evaluate("() => T.numbersOf('L')")
        assert numbers and fan["fan"], fan["fan"]
        n = numbers[0]
        now = act(how, n, chosen)  # the line of the fan is selected, the fan closes
        assert now["selected"] == [n["spot"], n["row"]] and now["fan"] is None, (n, now["selected"])
    for end, how in ((1, press), (2, hold), (2, press), (1, hold)):
        _state(page, "view.closeFan(); view.select(null); view.setLevel('spots');")
        line = page.evaluate("([r]) => T.anchors(r)", [reach])
        assert line, "no line in view has both anchors free on the map"
        _state(page)
        now = act(how, line["ends"][end - 1], opened)
        assert now["selected"] == [line["spot"], line["row"]] and now["fan"]["xy"] == line["ends"][end - 1]["xy"], (end, now["fan"])
        assert now["fan"]["lines"] >= 1 and now["misses"] == misses
    _state(page, "view.closeFan(); view.select(null);")


def _numbers_hold(s: dict, labels: set):
    """The numbers on the map: each whole on the part a person sees, under no control, on its line (3 px), no two
    within 4 px; their labels among `labels`, each once."""
    names = [n["label"] for n in s["numbers"]]
    assert len(set(names)) == len(names) and set(names) <= labels, (names, sorted(labels))
    for n in s["numbers"]:
        assert n["off"] <= 3, n
        if n["label"][0] != "A":
            assert n["whole"] and not n["under"], n
    centres = [(n["x"], n["y"]) for n in s["numbers"]]
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 4 for k, a in enumerate(centres) for b in centres[k + 1:])


def _legend_holds(s: dict):
    """The legend lists exactly the shapes and colours on the map now (at Area the squares stand for the lines'
    colours), then what is drawn besides the spots (a favourite's halo, the search area's outline, each other run of
    Compare), then the access mark's three states only while an anchor of the selected line is in view (the canvas's
    `ends`: the user's L b, 2026-11-20)."""
    kinds = ("sq", "P") if s["level"] == "area" else ("clear", "over", "P", "B", "pale", "A", "L", "here")
    shapes = s["shapes"]
    want = [k for k in kinds if k in shapes] + [k for k in ("fav", "area") if k in shapes] + ["run"] * s["runs"]
    assert s["legend"] == want + (["access-2", "access-1", "access-0"] if "ends" in shapes else []), (s["legend"], shapes)


def _in_view_holds(s: dict):
    """The spots in view are those whose shown line crosses the part of the map a person sees (counted in pixels),
    in the list's order; "of M in view" is their count."""
    assert s["spots"] == s["inPixels"] and s["m"] == len(s["spots"]) > 0, (s["m"], len(s["inPixels"]))
    n = s["m"] if s["best"] == "all" else min(s["best"], s["m"])
    assert s["bestSpots"] == s["spots"][:n]


def test_levels_in_view_numbers(site):
    """A small result opens without the area (Auto: the Lines level); each level held at the first view: the spots
    in view, the best N, the strokes by the page's own count, the numbers, the status line, the legend; Best 30,
    100 and All; Auto follows the zoom; one notch of the wheel is half a zoom step."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP)
            first = _state(page)
            # 164 spots on 240 m: the first view shows under 0.6 m per pixel, so Auto starts at Lines, Best 10
            assert (first["level"], first["auto"], first["best"]) == ("lines", True, 10) and first["mpp"] < 0.6
            assert first["counts"]["spots"] == first["m"] > 100 and first["counts"]["total"] == 7934
            assert first["bar"] == WORDS["ui.view.map.status_lines"].replace("{{n}}", "10").replace("{{m}}", str(first["m"]))
            _in_view_holds(first)
            _legend_holds(first)
            # (each line counted once: a best spot's shown line is one of its lines not beaten, drawn thin and bold)
            assert first["strokes"] == first["m"] - 10 + first["thin"] and 10 < first["thin"] <= LIMIT and first["refused"] == 0
            _numbers_hold(first, {f"B{k}" for k in range(1, 11)})
            assert len(first["numbers"]) >= 5  # most of the ten best have a free piece of their line
            spots = _state(page, "view.setLevel('spots');")
            assert (spots["level"], spots["auto"], spots["strokes"], spots["thin"]) == ("spots", False, spots["m"], 0)
            assert spots["bar"] == (WORDS["ui.view.map.status_spots"].replace("{{n}}", "10").replace("{{m}}", str(spots["m"])) +
                                    WORDS["ui.view.map.held"] + WORDS["ui.view.map.back_auto"])
            _in_view_holds(spots)
            _legend_holds(spots)
            _numbers_hold(spots, {f"B{k}" for k in range(1, 11)})
            assert {"B", "pale"} <= set(spots["shapes"])
            for best in (30, 100):
                more = _state(page, f"view.setBest({best});")
                _in_view_holds(more)
                _numbers_hold(more, {f"B{k}" for k in range(1, best + 1)})
                assert more["numbered"] and len(more["numbers"]) > len(spots["numbers"]) and more["strokes"] == more["m"]
            every = _state(page, "view.setBest('all');")
            _in_view_holds(every)
            _legend_holds(every)
            assert every["numbers"] == [] and not every["numbered"] and not {"B", "pale"} & set(every["shapes"])
            assert every["status"] == WORDS["ui.view.map.status_spots_all"].replace("{{m}}", str(every["m"]))
            area = _state(page, "view.setBest(10); view.setLevel('area');")
            assert (area["level"], area["strokes"], area["status"]) == ("area", area["picks"], WORDS["ui.view.map.status_area_held"])
            _legend_holds(area)
            _numbers_hold(area, {f"P{k}" for k in range(1, area["picks"] + 1)})
            assert {"sq", "P"} <= set(area["shapes"]) and 1 <= area["picks"] <= 5 and area["numbers"]
            # "Back to Auto", then Auto follows the zoom: Area above 2 m per pixel, Spots between, Lines below 0.6
            page.click(".v-back-auto")
            assert _state(page)["auto"] is True
            far = _state(page, "leaflet.setZoom(map.zoomOf(2.6), {animate: false});")
            assert (far["level"], far["auto"], far["status"]) == ("area", True, WORDS["ui.view.map.status_area"]) and far["mpp"] > 2
            assert page.evaluate("() => document.querySelector('.v-best select').disabled") is True
            middle = _state(page, "leaflet.setZoom(map.zoomOf(1), {animate: false});")
            assert middle["level"] == "spots" and 0.6 < middle["mpp"] < 2
            _in_view_holds(middle)
            close = _state(page, "leaflet.setZoom(map.zoomOf(0.3), {animate: false});")
            assert close["level"] == "lines" and close["mpp"] < 0.56
            _in_view_holds(close)
            _numbers_hold(close, {f"B{k}" for k in range(1, 11)})
            # the map zooms in quarter steps, one notch of the wheel half a step
            zoom = close["zoom"]
            assert zoom * 4 == int(zoom * 4)
            page.mouse.move(600, 500)
            page.mouse.wheel(0, -100)
            page.wait_for_function(f"() => window.FINDALINE_MAP.getZoom() !== {zoom} && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            assert _state(page)["zoom"] - zoom == 0.5
            # no grouping in the page: no such measure, and no Line made for a line that is only drawn
            names = page.evaluate("() => [...new Set(performance.getEntriesByType('measure').map((e) => e.name))]")
            assert "fal:view:first" in names and "fal:view:draw" in names and not {"fal:run:group", "fal:run:filter"} & set(names)
            assert close["made"] == 0 and page.errors == []
        finally:
            browser.close()


def test_limit_legend_squares(site):
    """Above 5 000 thin lines the Lines level draws only the pale lines and says so, marked (the search area's outline
    stays: the legend's `area` while it crosses the view, none off it); with the best 100 it draws again. The squares' legend: the select of four values, five classes; a press on a square zooms to it and
    Auto lands on Spots."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP)
            refused = _state(page, "view.setTopOnly(false); view.setBest('all');")
            lines = page.evaluate("() => T.linesInView()")
            assert refused["level"] == "lines" and refused["refused"] == refused["thin"] == lines > LIMIT
            assert refused["strokes"] == refused["m"] and refused["numbers"] == [] and refused["marked"] is True
            count = f"{lines // 1000}{chr(160)}{lines % 1000:03d}"
            assert refused["status"] == WORDS["ui.view.map.status_refused"].replace("{{n}}", count).replace("{{lower}}", "100")
            _legend_holds(refused)
            # no bold line and no number; the search area's outline is drawn at every level (B1's 68dd2e83): `area`
            # exactly while it crosses the part a person sees (strict both ways: here in view, off it at the end)
            assert set(refused["shapes"]) - {"area"} <= {"pale", "clear", "over"}, refused["shapes"]
            assert page.evaluate("() => T.areaCrosses()") is True and "area" in refused["shapes"], refused["shapes"]
            # the legend's rows in this known state, fixed (not rebuilt from the canvas's shapes): the lines' colours (the
            # pale lines are drawn in them), the pale lines, the area
            assert refused["legend"] == ["clear", "over", "pale", "area"], refused["legend"]
            fewer =_state(page, "view.setBest(100);")
            assert fewer["refused"] == 0 and 100 < fewer["thin"] <= LIMIT and fewer["marked"] is False
            assert fewer["m"] > 100 and fewer["strokes"] == fewer["m"] - 100 + fewer["thin"] and fewer["numbered"] and len(fewer["numbers"]) > 10
            _numbers_hold(fewer, {f"B{k}" for k in range(1, 101)})
            # Area under Auto: the legend's select and classes, the note; another value gives other breaks
            area = _state(page, "view.setBest(10); view.setTopOnly(true); leaflet.setZoom(map.zoomOf(2.6), {animate: false});")
            assert (area["level"], area["auto"]) == ("area", True)
            legend = page.evaluate("""() => ({options: [...document.querySelectorAll('.v-by option')].map((o) => o.textContent),
                classes: [...document.querySelectorAll('.v-class')].map((c) => c.textContent), note: document.querySelector('.v-lg-note')?.textContent,
                by: window.FINDALINE_VIEW.map.legend().by, breaks: window.FINDALINE_VIEW.map.legend().breaks})""")
            assert legend["options"] == [WORDS[f"ui.view.map.by_{k}"] for k in ("spots", "lines", "clr", "len")]
            assert legend["note"] == WORDS["ui.view.map.squares_note"] and legend["by"] == "spots"
            assert legend["breaks"] == sorted(set(legend["breaks"])) and all(b == int(b) for b in legend["breaks"])
            assert 2 <= len(legend["classes"]) <= 5 and legend["classes"][-1] == f"{legend['breaks'][3]}+"
            page.select_option(".v-by", "len")
            page.evaluate("() => T.frames()")
            metres = page.evaluate("() => ({by: window.FINDALINE_VIEW.map.legend().by, breaks: window.FINDALINE_VIEW.map.legend().breaks, "
                                   "classes: [...document.querySelectorAll('.v-class')].map((c) => c.textContent)})")
            assert metres["by"] == "len" and metres["breaks"] != legend["breaks"] and metres["classes"][0].startswith("under ")
            # a press on a square (no pick's line there) zooms to it; under Auto to at most 0.96 m per pixel: Spots
            square = page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, g = map.grid, leaflet = window.FINDALINE_MAP, box = T.box();
              for (let k = 0; k < g.cells.length; k++) { const i = g.cells[k] % g.nx, j = (g.cells[k] - i) / g.nx;
                const at = leaflet.latLngToContainerPoint(view.fit.toLatLng(g.x0 + (i + 0.5) * g.side, g.y0 + (j + 0.5) * g.side));
                if (map.pickAt(at.x, at.y, false).length === 0 && at.y > 60 && at.y < box.height - 120) return {x: at.x + box.left, y: at.y + box.top, cells: g.cells.length, side: g.side}; }
              return null; }""")
            assert square and square["cells"] >= 2 and square["side"] in (100, 200)
            page.mouse.click(square["x"], square["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.level !== 'area' && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            zoomed = _state(page)
            assert zoomed["level"] == "spots" and 0.96 * 0.999 <= zoomed["mpp"] < 2 and zoomed["selected"] is None
            # the map moved off the search area (twice its width east): no `area` in the legend's state
            off = _state(page, "const b = map.areaBounds(), w = b.getEast() - b.getWest(); "
                               "leaflet.setView([b.getCenter().lat, b.getEast() + 2 * w], leaflet.getZoom(), {animate: false});")
            assert page.evaluate("() => T.areaCrosses()") is False and "area" not in off["shapes"], off["shapes"]
            assert page.errors == []
        finally:
            browser.close()


def test_presses_with_a_mouse(site):
    """A number's shape selects its spot's bold line; a line; an empty point ends the selection; the hover; a right
    click opens "Lines from here" (none near: the map says so and an open fan stays); a fan's line selects it and
    closes the fan; A1 opens the lines from that anchor; an empty point closes the fan and keeps the spot, a second
    ends the selection; Esc closes the fan, then the selection; several spots under the mouse select none (the
    table of spots is the panels')."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP)
            s = _state(page, "view.setLevel('spots');")
            box = page.evaluate("() => { const b = T.box(); return [b.left, b.top]; }")
            number = s["numbers"][0]
            spot = s["bestSpots"][int(number["label"][1:]) - 1]
            page.mouse.click(box[0] + number["x"], box[1] + number["y"])
            page.wait_for_selector(".c-col-map > .r-card", timeout=WAIT)
            # the profile's card opened: the foot is the short one, the legend behind "Legend" (the user's 4 a)
            assert page.evaluate("() => [!!document.querySelector('.v-legend'), document.querySelector('.v-fold')?.getAttribute('aria-expanded')]") == [False, "false"]
            page.click(".v-fold")
            page.wait_for_selector(".v-legend", timeout=WAIT)
            chosen = _state(page)
            assert chosen["selected"] == [spot, chosen["shown"]] and chosen["made"] == 1
            # the legend's rows with this selection, fixed (not rebuilt from the canvas's shapes): the lines' colours,
            # the best, the pale others, the selected line's anchors, the search area, the access marks (its anchors in
            # view: L b)
            assert chosen["legend"] == ["clear", "over", "B", "pale", "A", "area", "access-2", "access-1", "access-0"], chosen["legend"]
            _legend_holds(chosen)
            assert {n["label"] for n in chosen["numbers"]} >= {"A1", "A2"} and "A" in chosen["shapes"]
            _numbers_hold(chosen, {f"B{k}" for k in range(1, 11)} | {"A1", "A2"})
            assert page.evaluate("() => document.querySelectorAll('.v-anchor-mark').length") == 2  # the access mark on the corners
            page.keyboard.press("Escape")
            assert _state(page)["selected"] is None
            # a bold line where only its spot is in reach
            second = next((s2, at) for s2 in s["bestSpots"]
                          if (at := page.evaluate("([spot]) => T.pointOn(window.FINDALINE_VIEW.view.shownOf(spot), [spot], false)", [s2])))
            page.mouse.move(second[1]["x"], second[1]["y"])
            page.wait_for_function("() => window.FINDALINE_MAP.getContainer().classList.contains('v-target')", timeout=WAIT)
            assert page.evaluate("() => window.FINDALINE_VIEW.map.mapHovered") == page.evaluate(
                "([spot]) => window.FINDALINE_VIEW.view.shownOf(spot)", [second[0]])
            page.mouse.click(second[1]["x"], second[1]["y"])
            assert _state(page)["selected"][0] == second[0]
            empty = page.evaluate("() => T.empty(false)")
            page.mouse.click(empty["x"], empty["y"])
            none = _state(page)
            assert none["selected"] is None and none["target"] is False
            # a right click at the first anchor of the best spot's line: "Lines from here"; no menu of the browser
            anchor = page.evaluate("([spots]) => T.anchor(spots, 6)", [s["bestSpots"]])
            assert anchor, "no anchor of a best spot's line is free on the map"
            page.evaluate("() => { window.MENUS = []; document.addEventListener('contextmenu', (e) => MENUS.push(e.defaultPrevented)); }")
            page.mouse.click(anchor["x"], anchor["y"], button="right")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.fan !== null && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            fan = _state(page)
            assert fan["fan"]["lines"] >= 1 and fan["selected"] is None and "here" in fan["shapes"] and fan["misses"] == 0
            assert page.evaluate("() => window.MENUS") == [True]
            _legend_holds(fan)
            _numbers_hold(fan, {label for label, _ in fan["fan"]["rows"]} | {f"B{k}" for k in range(1, 11)})
            assert anchor["row"] in [row for _, row in fan["fan"]["rows"]] or fan["fan"]["lines"] > len(fan["fan"]["rows"])
            assert fan["numbers"] and len(fan["fan"]["rows"]) <= 40
            # no line within 10 m: the map says so, the open fan stays
            far = page.evaluate("() => T.far()")
            assert far, "no point of the map lies 12 m from every line"
            page.mouse.click(far["x"], far["y"], button="right")
            page.wait_for_selector(".v-toast", timeout=WAIT)
            missed = _state(page)
            assert missed["toast"] == WORDS["ui.view.map.fan_none"].replace("{{m}}", "10") and missed["misses"] == 1
            assert missed["fan"]["rows"] == fan["fan"]["rows"]
            # a line of the fan selects that line and closes the fan
            label, row = fan["fan"]["rows"][-1]
            at = page.evaluate("([row]) => { const e = T.ends(row), b = T.box(), m = window.FINDALINE_VIEW.map.drawn().numbers.map((n) => n.box);"
                               " for (let t = 0.3; t < 0.9; t += 0.02) { const x = e[0] + (e[2] - e[0]) * t + b.left, y = e[1] + (e[3] - e[1]) * t + b.top;"
                               " if (!m.some((c) => x > c.left - 4 && x < c.right + 4 && y > c.top - 4 && y < c.bottom + 4)) return {x, y}; } return null; }", [row])
            page.mouse.click(at["x"], at["y"])
            picked = _state(page)
            assert picked["fan"] is None and picked["selected"] is not None
            assert picked["selected"][1] in [r for _, r in fan["fan"]["rows"]]  # the nearest fan line under the press
            # A1 of the selected line opens the lines from that anchor (the spot stays selected)
            a1 = next(n for n in picked["numbers"] if n["label"] == "A1")
            page.mouse.click(box[0] + a1["x"], box[1] + a1["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.fan !== null && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            from_anchor = _state(page)
            assert from_anchor["selected"] == picked["selected"] and from_anchor["fan"]["lines"] >= 1
            ends = page.evaluate("([row]) => { const v = window.FINDALINE_VIEW.view.values; return [v.x1[row], v.y1[row]]; }", [picked["selected"][1]])
            assert from_anchor["fan"]["xy"] == ends
            # an empty point closes the fan and keeps the spot; a second one ends the selection
            for want_fan, want_selected in ((False, True), (False, False)):
                empty = page.evaluate("() => T.empty(false)")
                page.mouse.click(empty["x"], empty["y"])
                now = _state(page)
                assert (now["fan"] is not None, now["selected"] is not None) == (want_fan, want_selected)
            # Esc: the fan first, then the selection
            both = _state(page, f"view.select({spot}); const row = view.shownOf({spot}), c = view.model.data.columns; "
                                "view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1});")
            assert both["fan"] and both["selected"]
            page.keyboard.press("Escape")
            after = _state(page)
            assert after["fan"] is None and after["selected"] is not None
            page.keyboard.press("Escape")
            assert _state(page)["selected"] is None
            # several spots about as near under the mouse: none is selected, the table of spots is asked for (the frame
            # says for how many: `data-choosing`); Esc closes it
            crowded = _crowded(page, False)
            assert crowded and len(crowded["spots"]) > 1
            page.mouse.click(crowded["x"], crowded["y"])
            page.wait_for_function("() => !!document.querySelector('.v-map').dataset.choosing", timeout=WAIT)
            asked = int(page.evaluate("() => document.querySelector('.v-map').dataset.choosing"))
            assert len(crowded["spots"]) <= asked <= 6 and _state(page)["selected"] is None
            page.keyboard.press("Escape")
            page.wait_for_function("() => !document.querySelector('.v-map').dataset.choosing", timeout=WAIT)
            # a press and a right click on a number's shape of each kind
            _state(page, "map.fitArea({top: 50, right: 10, bottom: 80, left: 10});")
            page.evaluate("() => { window.MENUS = []; }")

            def right(x, y, until):
                page.mouse.click(x, y, button="right")
                page.wait_for_function(until, timeout=WAIT)
            _shape_presses(page, lambda x, y: page.mouse.click(x, y), right, 8)
            menus = page.evaluate("() => window.MENUS")
            assert len(menus) == 5 and all(menus)  # every right click: no menu of the browser
            assert page.errors == []
        finally:
            browser.close()


def test_phone_touch(site):
    """A phone: the view opens with the sheet low; the spots in view are those above the sheet, at each stop; a
    tap on a number selects; a press held 600 ms opens "Lines from here" and the finger's lift changes nothing more;
    a tap on several spots zooms in one level around the point, says so and flashes; once the map shows 0.25 m per
    pixel a tap zooms no further and the table of spots is asked for; a tap and a hold on a number's shape of each
    kind."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", PHONE)
            # the view opens with the sheet low (it takes its height after the first draw: the view's rectangle is
            # then taken again)
            settled = "() => { const s = T.state(); return %s && s.spots.length === s.inPixels.length; }"
            page.wait_for_function(settled % "s.free[3] > s.size[1] * 0.75 && s.free[3] < s.size[1]", timeout=WAIT)
            start = _state(page)
            assert abs(start["size"][1] - start["free"][3] - 132) <= 1  # the sheet's lowest stop
            _in_view_holds(start)
            _legend_holds(start)
            _numbers_hold(start, {f"B{k}" for k in range(1, 11)})
            fold = page.evaluate("() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), document.querySelectorAll('.v-lg-line').length]")
            # the legend unfolded while the sheet is low, its rows fixed for this known state (not rebuilt from the
            # canvas's shapes): the lines and numbers on a line, the search area's outline on the second; no access mark
            # (nothing selected: L b)
            assert start["legend"] == ["clear", "over", "B", "pale", "area"], start["legend"]
            assert fold == ["true", 2], (fold, start["shapes"])
            # the sheet raised to half: the view's rectangle is taken again, fewer spots are in view
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function(settled % "s.free[3] < s.size[1] * 0.6", timeout=WAIT)
            half = _state(page, "view.setLevel('spots');")
            assert half["free"][3] < half["size"][1] * 0.6 and 0 < half["m"] < start["m"]
            _in_view_holds(half)
            _numbers_hold(half, {f"B{k}" for k in range(1, 11)})
            # the legend: folded by itself at half; the person's unfold holds there; lowered, the legend is unfolded by
            # itself; the person's fold holds there, and ends when the sheet next changes its stop
            legend = "() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), !!document.querySelector('.v-legend')]"
            assert page.evaluate(legend) == ["false", False]
            for key, want in ((None, ["true", True]), ("ArrowDown", ["true", True]), (None, ["false", False]), ("ArrowUp", ["false", False]),
                              ("ArrowDown", ["true", True])):
                if key:
                    page.focus(".u-sheet-handle")
                    page.keyboard.press(key)
                    page.wait_for_function(settled % ("s.free[3] > s.size[1] * 0.75" if key == "ArrowDown" else "s.free[3] < s.size[1] * 0.6"), timeout=WAIT)
                else:
                    _tap_on(page, ".v-fold")
                page.wait_for_function(f"() => JSON.stringify(({legend})()) === '{json.dumps(want, separators=(',', ':'))}'", timeout=WAIT)
                if want[1]:
                    _legend_holds(_state(page))
            low = _state(page)
            assert low["free"][3] > half["free"][3] + 100
            _in_view_holds(low)
            _numbers_hold(low, {f"B{k}" for k in range(1, 11)})
            box = page.evaluate("() => { const b = T.box(); return [b.left, b.top]; }")
            assert low["numbers"], low["free"]
            number = low["numbers"][0]
            _tap(page, box[0] + number["x"], box[1] + number["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.selected !== null", timeout=WAIT)
            tapped = _state(page)
            assert tapped["selected"][0] == low["bestSpots"][int(number["label"][1:]) - 1]
            _state(page, "view.select(null);")
            # a press held on a line's anchor: the fan opens while the finger is down; lifting it changes nothing
            at = page.evaluate("([spots]) => T.anchor(spots, 24)", [low["spots"]])
            assert at, "no anchor of a line in view is free on the map"
            cdp = page.context.new_cdp_session(page)
            point = [{"x": at["x"], "y": at["y"], "id": 1}]
            page.evaluate("() => { window.HELD = performance.now(); window.MENUS = 0; document.addEventListener('contextmenu', () => window.MENUS++, true); }")
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": point})
            page.wait_for_function("() => window.FINDALINE_VIEW.view.fan !== null", timeout=WAIT)
            waited, menus = page.evaluate("() => [performance.now() - window.HELD, window.MENUS]")
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            page.evaluate("() => { window.TOUCHED = performance.now(); }")
            held = _state(page)
            # the page's own timer of 600 ms, or the browser's own long-press event where it comes first (it is taken once)
            assert (waited >= 550 or menus >= 1) and held["selected"] is None and held["fan"]["lines"] >= 1 and held["misses"] == 0, (waited, menus)
            assert at["row"] in [row for _, row in held["fan"]["rows"]] or held["fan"]["lines"] > len(held["fan"]["rows"])
            print(f"hold: the fan opened {waited:.0f} ms after the touch began; contextmenu events of the browser: {menus}")
            _state(page, "view.closeFan();")
            # several spots under the finger: one level in around the point, the toast, until 0.25 m per pixel
            crowded = page.evaluate("() => T.crowded(true)")
            assert crowded and len(crowded["spots"]) > 1
            before = _state(page)
            assert before["mpp"] > 0.25 * 1.01
            step = min(1, page.evaluate("() => window.FINDALINE_MAP.getMaxZoom()") - before["zoom"])  # one level, or to the map's last
            _tap(page, crowded["x"], crowded["y"])
            page.wait_for_function(f"() => window.FINDALINE_MAP.getZoom() === {before['zoom'] + step} && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            closer = _state(page)
            assert step > 0 and closer["toast"] == WORDS["ui.view.map.crowded"] and closer["selected"] is None
            assert closer["mpp"] == pytest.approx(before["mpp"] / 2 ** step, rel=0.01)
            # the tapped point stayed under the finger
            moved = page.evaluate("([lat, lng]) => { const p = window.FINDALINE_MAP.latLngToContainerPoint([lat, lng]), b = T.box(); return [p.x + b.left, p.y + b.top]; }",
                                  [crowded["at"]["lat"], crowded["at"]["lng"]])
            assert abs(moved[0] - crowded["x"]) <= 2 and abs(moved[1] - crowded["y"]) <= 2
            _in_view_holds(closer)
            # one quarter step closer than the last zoom above 0.25 m per pixel: a tap on several spots zooms no
            # further, the table of spots is asked for (the frame says for how many); a move of the map closes it
            _state(page, "leaflet.setZoom(map.zoomOf(0.25) + 0.25, {animate: false});")
            last = _crowded(page, True)
            assert last and len(last["spots"]) > 1, "no point with several spots under a finger at 0.25 m per pixel"
            zoom = page.evaluate("() => window.FINDALINE_MAP.getZoom()")
            _tap(page, last["x"], last["y"])
            page.wait_for_function("() => !!document.querySelector('.v-map').dataset.choosing", timeout=WAIT)
            end = _state(page)
            asked = int(page.evaluate("() => document.querySelector('.v-map').dataset.choosing"))
            assert end["zoom"] == zoom and not end["animating"] and end["mpp"] <= 0.25 * 1.001 and end["selected"] is None
            assert len(last["spots"]) <= asked <= 6
            _state(page, "leaflet.panBy([12, 0], {animate: false});")
            assert page.evaluate("() => document.querySelector('.v-map').dataset.choosing") is None
            # a tap and a hold on a number's shape of each kind
            _state(page, "view.setLevel('auto'); map.fitArea({top: 120, right: 10, bottom: 220, left: 10});")

            def held(x, y, until):
                page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1}]})
                page.wait_for_function(until, timeout=WAIT)
                before = page.evaluate("() => { const {view} = window.FINDALINE_VIEW; return [view.selected && view.selected.row, view.fan && view.fan.lines]; }")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                page.evaluate("() => { window.TOUCHED = performance.now(); }")
                page.evaluate("() => T.frames()")
                # the finger's lift changes nothing more
                assert page.evaluate("() => { const {view} = window.FINDALINE_VIEW; return [view.selected && view.selected.row, view.fan && view.fan.lines]; }") == before
            _shape_presses(page, lambda x, y: _tap(page, x, y), held, 24)
            assert page.errors == []
        finally:
            browser.close()


# A stand-in for the shore's chip (shoreLayer.ts: a Leaflet control at the map's top left, folded on a phone), which the
# clip's run in the mountains does not have: the same classes, so the page's own styles size it
CHIP = """() => { const holder = document.createElement("div");
  holder.className = "leaflet-control u-shore-ctl u-shore-folded";
  const chip = holder.appendChild(document.createElement("button"));
  chip.type = "button"; chip.className = "u-shore-chip";
  const swatches = chip.appendChild(document.createElement("span"));
  swatches.className = "u-shore-chip-sw";
  for (const kind of ["surface", "sea"]) swatches.appendChild(document.createElement("span")).className = "u-shore-swatch u-shore-" + kind;
  chip.appendChild(document.createElement("b")).textContent = "Uncertain shore";
  const metres = chip.appendChild(document.createElement("span"));
  metres.className = "u-shore-chip-m"; metres.textContent = "1.6 km";
  document.querySelector(".v-map .leaflet-top.leaflet-left").appendChild(holder); }"""

# A stand-in for the coarser terrain's box alone (coarserLayer.ts coarserControl's box, as a desktop shows it: no chip),
# for the sizes of its help (tests/test_view_frame.py): the same classes and help button (shoreLayer.ts helpButton, the
# kit's "info" icon), its title and one fallback's row in the catalogue's words. A run with the real controls:
# boxes_site
COARSE = """() => { const box = document.createElement("div");
  box.className = "leaflet-control u-shore u-coarse";
  const head = box.appendChild(document.createElement("div"));
  head.className = "u-shore-head";
  head.appendChild(document.createElement("b")).textContent = %s;
  const help = head.appendChild(document.createElement("button"));
  help.type = "button"; help.className = "u-ib u-plain u-shore-help"; help.setAttribute("aria-label", %s);
  help.innerHTML = '<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>';
  const row = box.appendChild(document.createElement("div"));
  row.className = "u-shore-row";
  row.appendChild(document.createElement("span")).className = "u-coarse-swatch";
  row.appendChild(document.createElement("span")).textContent = %s;
  document.querySelector(".v-map .leaflet-top.leaflet-left").appendChild(box); }""" % (
    json.dumps(WORDS["ui.coarse.title"]), json.dumps(WORDS["ui.coarse.help_button"]),
    json.dumps(WORDS["ui.coarse.km2"].replace("{{km2}}", "0.4").replace("{{res}}", "30").replace("{{name}}", "Copernicus GLO-30")))


# The panels' hint hidden by its ×: on a phone its button then stands on the map, in the row of buttons beside "Legend"
# (the frame's slot), the worst case of the pilot's arrangement (2026-11-18)
HINT = "() => document.querySelector('.vl-hint-x').click()"
HINT_SHOWN = "() => !!document.querySelector('.v-hint-slot .vl-hint-open')"


def _over_holds(page, selector: str, state: str) -> dict:
    """A panel the person opened over the map (the access mark's key; the legend where the foot has no room): it lies
    above every other control it crosses (a press there reaches the panel), within the part of the map a person
    sees (under the top bar, above the sheet), and leaves the bar's own buttons free."""
    r = page.evaluate("""([selector]) => { const panel = document.querySelector(selector), whole = panel.getBoundingClientRect(), crossed = [];
        // the part of the panel that shows: it scrolls inside the box of the panels (.v-over)
        const clip = panel.closest(".v-over").getBoundingClientRect();
        const box = {left: Math.max(whole.left, clip.left), top: Math.max(whole.top, clip.top), right: Math.min(whole.right, clip.right), bottom: Math.min(whole.bottom, clip.bottom)};
        const under = (x, y) => document.elementFromPoint(x, y);
        for (const e of document.querySelectorAll(T.CONTROLS)) {
          if (e === panel || panel.contains(e) || e.contains(panel) || e.closest(".c-phone-top")) continue;
          const r = e.getBoundingClientRect(), x0 = Math.max(r.left, box.left), x1 = Math.min(r.right, box.right), y0 = Math.max(r.top, box.top), y1 = Math.min(r.bottom, box.bottom);
          if (x1 - x0 > 2 && y1 - y0 > 2) crossed.push([e.className, !!under((x0 + x1) / 2, (y0 + y1) / 2)?.closest(selector)]); }
        const free = [...document.querySelectorAll(".v-fold, .v-help-button button")].map((e) => { const r = e.getBoundingClientRect();
          return e.contains(under(r.left + r.width / 2, r.top + r.height / 2)); });
        return {box: [box.left, box.top, box.right, box.bottom], crossed, free, top: document.querySelector(".c-phone-top > *").getBoundingClientRect().bottom,
                sheet: document.querySelector(".u-sheet").getBoundingClientRect().top, width: innerWidth}; }""", [selector])
    assert r["box"][1] >= r["top"] and r["box"][3] <= r["sheet"] + 0.5 and r["box"][0] >= 0 and r["box"][2] <= r["width"], (state, r)
    assert all(above for _, above in r["crossed"]) and r["free"] and all(r["free"]), (state, r)
    return r


def _apart(page, state: str, known: tuple = ()) -> dict:
    """No control of the map covers another (their boxes, by name: T.boxes), and each stands above a phone's sheet.
    `known`: pairs (names in order) excepted by the caller, each with its reason there."""
    boxes, sheet = page.evaluate("() => [T.boxes(), document.querySelector('.u-sheet')?.getBoundingClientRect().top ?? 1e9]")
    names, wrong = sorted(boxes), []
    for k, a in enumerate(names):
        if boxes[a][3] > sheet + 0.5:
            wrong.append((a, boxes[a], "under the sheet", sheet))
        for b in names[k + 1:]:
            if (a, b) == ("back", "status") or (a, b) in known:  # "Back to Auto" is a part of the status line's sentence:
                continue  # its target (44 px on a touch screen) reaches past the box, and no other control may lie there
            p, q = boxes[a], boxes[b]
            if min(p[2], q[2]) - max(p[0], q[0]) > 0.5 and min(p[3], q[3]) - max(p[1], q[1]) > 0.5:
                wrong.append((a, p, b, q))
    assert not wrong, (state, wrong)
    # every caller is a touch screen: "Back to Auto", where the status line has it, is a finger's 44 px target
    assert "back" not in boxes or boxes["back"][3] - boxes["back"][1] >= 43.5, (state, boxes["back"])
    return boxes


def test_phone_controls_apart(boxes_site):
    """A small phone (390 x 664) with the uncertain shore's chip and the coarser terrain's chip on the map (a run with
    both in its head; the coarser box folds into a chip on a phone since step 3c: the user's choice of 2026-11-20) and
    the hint hidden (its button in the bar's row of buttons: the pilot's worst case). At the sheet's low
    stop and at half, no control of the map covers another (the status line, the legend, its fold, the map's "i", the
    hint's button, the switch, Best, the zoom buttons, the layers button (the kit's icon), the shore's chip, the
    coarser terrain's chip, the scale, the credits, the top bar with the
    run's actions; the message is the status line's first line, a part of its box; the map's help, opened, lies above
    them as a panel), but for one known pair at half with a level held (CHIPS_HALF_HELD: the coarser chip and the
    status line's two lines; the user's answer of 2026-11-20, a known bug for now), and each stands above
    the sheet: at Area, Spots, Lines, Lines with All refused, and after a tap on several spots (the message up). The
    legend is unfolded by itself while the sheet is low and folded at half, where this phone has no room for it: a
    press on "Legend" there lowers the sheet and unfolds it. An opened layers list lies above the bar. A tap on a
    square fits it into the part of the map free of the bar and the sheet."""
    from playwright.sync_api import sync_playwright
    settled = "() => { const s = T.state(); return %s && s.spots.length === s.inPixels.length; }"
    fit = "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10});"
    states = (("area", "view.setTopOnly(true); view.setBest(10); view.setLevel('area');"), ("spots", "view.setLevel('spots');"),
              ("lines", "view.setLevel('lines');"), ("refused", "view.setTopOnly(false); view.setBest('all');"))
    legend = "() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), !!document.querySelector('.v-legend')]"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{boxes_site}#run={BOXES}", SMALL_PHONE)
            page.wait_for_function(settled % "s.free[3] > s.size[1] * 0.75 && s.free[3] < s.size[1]", timeout=WAIT)
            page.evaluate(HINT)
            page.wait_for_function(HINT_SHOWN, timeout=WAIT)
            # the layers button with the kit's "layers" icon (layersControl.ts), not Leaflet's picture
            assert page.evaluate("() => { const t = document.querySelector('.v-map .leaflet-control-layers-toggle'); "
                                 "return !!t.querySelector('svg.u-ic') && getComputedStyle(t).backgroundImage === 'none'; }")
            seen = {}
            for stop in ("low", "half"):
                if stop == "half":
                    page.focus(".u-sheet-handle")
                    page.keyboard.press("ArrowUp")
                    page.wait_for_function(settled % "s.free[3] < s.size[1] * 0.6", timeout=WAIT)
                for name, script in states:
                    s = _state(page, fit + script)
                    boxes = seen[stop, name] = _apart(page, f"{stop} {name}", known=CHIPS_HALF_HELD if stop == "half" else ())
                    assert {"status", "fold", "help", "hint", "levels", "best", "zoom", "layers", "chip", "coarse", "scale"} <= set(boxes), (stop, name, sorted(boxes))
                    # the legend by itself: unfolded while the sheet is low, folded at half
                    assert page.evaluate(legend) == (["true", True] if stop == "low" else ["false", False]), (stop, name)
                    assert ("legend" in boxes) == (stop == "low")
                    if name == "refused":
                        assert s["marked"] is True and s["refused"] > LIMIT, (stop, s["refused"])
                    elif name == "area":
                        # the squares' legend on a phone: the select with its text whole, the five classes as one ramp
                        if stop == "low":
                            ramp = page.evaluate("""() => { const by = document.querySelector(".v-by"), r = document.querySelector(".v-ramp");
                                const probe = document.body.appendChild(document.createElement("span"));
                                probe.textContent = by.selectedOptions[0].textContent;
                                probe.style.font = getComputedStyle(by).font; probe.style.whiteSpace = "nowrap"; probe.style.position = "absolute";
                                const text = probe.getBoundingClientRect().width;
                                probe.remove();
                                return {lines: document.querySelectorAll(".v-lg-line").length, whole: text > 100 && by.clientWidth >= text,
                                        swatches: r.querySelectorAll(".v-lay").length, name: r.getAttribute("aria-label"), text: r.textContent,
                                        height: document.querySelector(".v-legend").getBoundingClientRect().height}; }""")
                            # its two lines: the 44 px select of a touch screen (R2) with the ramp, then the pick's mark
                            # (1:1) and the access marks, which wrap once at the pilot's 13 px (112 px measured
                            # 2026-11-18; before R2 and the pilot: under 70); _apart keeps it clear of every control
                            assert ramp["lines"] == 2 and ramp["whole"] and ramp["swatches"] == 5 and ramp["height"] < 120, ramp
                            assert ramp["text"].startswith("1") and ramp["text"].endswith("+") and "," in ramp["name"], ramp
                # the map's help, opened by its "i" on the access mark's key (the user's 7 b): a panel above the
                # controls, the others still apart
                _state(page, fit + "view.setTopOnly(true); view.setBest(10); view.setLevel('spots');")
                _tap_on(page, ".v-help-button button")
                page.wait_for_selector(".v-over > .v-help", timeout=WAIT)
                page.evaluate("() => T.frames()")
                _apart(page, f"{stop}, the map's help open", known=CHIPS_HALF_HELD if stop == "half" else ())
                key = _over_holds(page, ".v-over > .v-help", f"{stop}, the map's help")
                assert key["box"][3] - key["box"][1] > 40, key
                # its "i" says it is open, in words and in the kit's on-state (the soft accent)
                look = "() => { const b = document.querySelector('.v-help-button button'), s = getComputedStyle(b); return [b.getAttribute('aria-expanded'), s.backgroundColor]; }"
                soft = page.evaluate("() => { const e = document.createElement('i'); e.style.background = 'var(--accent-soft)'; document.querySelector('.v-result').append(e); "
                                     "const c = getComputedStyle(e).backgroundColor; e.remove(); return c; }")
                assert page.evaluate(look) == ["true", soft], (page.evaluate(look), soft)
                _tap_on(page, ".v-help-button button")
                page.wait_for_selector(".v-help", state="detached", timeout=WAIT)
                assert page.evaluate(look)[0] == "false" and page.evaluate(look)[1] != soft
                # a tap on several spots: the map says so; the message covers no control
                _state(page, fit + "view.setTopOnly(true); view.setBest(10); view.setLevel('spots');")
                # (at half this phone's map has no point 24 px from every control; nearer than about 10 px to the
                # credits' links the browser's touch adjustment gives the tap to a link: measured 2026-11-18, a tap
                # 2 or 4 px from the credits' box went to its "Leaflet" link, at 6 and 8 px to "Legend" beside it)
                crowded = _crowded(page, True, 12)
                assert crowded and len(crowded["spots"]) > 1, stop
                _tap(page, crowded["x"], crowded["y"])
                page.wait_for_selector(".v-toast", timeout=WAIT)
                page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
                page.evaluate("() => T.frames()")
                boxes = seen[stop, "tap"] = _apart(page, f"{stop} tap", known=CHIPS_HALF_HELD if stop == "half" else ())
                # the message stands in the status line's box, its first line (the pilot's arrangement of 2026-11-18)
                assert "status" in boxes and page.evaluate("() => [document.querySelector('.v-toast').textContent, "
                                                           "document.querySelector('.v-status').firstElementChild.classList.contains('v-toast')]") == \
                    [WORDS["ui.view.map.crowded"], True]
                page.wait_for_selector(".v-toast", state="detached", timeout=WAIT)
            # at half this phone's map has no room for the whole legend (41 px under the zoom row, the legend's two lines
            # need about 70): a press on "Legend" lowers the sheet and unfolds the legend there; nothing covers another;
            # raised again, the legend is folded by itself
            _state(page, fit + "view.setLevel('spots');")
            assert page.evaluate("() => document.querySelector('.v-fold').disabled") is False and page.evaluate(legend) == ["false", False]
            _tap_on(page, ".v-fold")
            page.wait_for_function(settled % "s.free[3] > s.size[1] * 0.75", timeout=WAIT)
            page.wait_for_function(f"() => JSON.stringify(({legend})()) === '[\"true\",true]'", timeout=WAIT)
            lowered = _apart(page, "lowered by a press on Legend")
            assert "legend" in lowered and _state(page)["selected"] is None
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function(settled % "s.free[3] < s.size[1] * 0.6", timeout=WAIT)
            _state(page, fit + "view.setLevel('spots');")
            assert page.evaluate(legend) == ["false", False]
            _apart(page, "half again", known=CHIPS_HALF_HELD)
            # an opened layers list lies above the bar: where it crosses the bar's boxes, a press reaches the list (the
            # clip's list is short: made as long as a run's with an orthophoto and overlays, it crosses the bar's foot)
            _tap_on(page, ".leaflet-control-layers-toggle")
            page.wait_for_selector(".leaflet-control-layers-expanded", timeout=WAIT)
            over = page.evaluate("""() => { const control = document.querySelector(".leaflet-control-layers");
                control.style.minHeight = "190px";
                const list = control.getBoundingClientRect(), found = [];
                for (const e of document.querySelectorAll(".v-status, .v-legend, .v-fold, .v-toast")) { const r = e.getBoundingClientRect();
                  const x0 = Math.max(r.left, list.left), x1 = Math.min(r.right, list.right), y0 = Math.max(r.top, list.top), y1 = Math.min(r.bottom, list.bottom);
                  if (x1 - x0 > 2 && y1 - y0 > 2) found.push([e.className, !!document.elementFromPoint((x0 + x1) / 2, (y0 + y1) / 2)?.closest(".leaflet-control-layers")]); }
                return found; }""")
            assert over and all(above for _, above in over), over
            page.evaluate("() => { const control = document.querySelector('.leaflet-control-layers'); control.style.minHeight = ''; "
                          "control.classList.remove('leaflet-control-layers-expanded'); }")
            # at half, Area under Auto: a tap on a square fits it into the map's part free of the bar and the sheet
            area = _state(page, fit + "view.setLevel('auto'); leaflet.setZoom(map.zoomOf(2.6), {animate: false});")
            assert (area["level"], area["auto"]) == ("area", True)
            _apart(page, "half, Area under Auto")
            square = page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, g = map.grid, leaflet = window.FINDALINE_MAP, box = T.box();
              for (let k = 0; k < g.cells.length; k++) { const i = g.cells[k] % g.nx, j = (g.cells[k] - i) / g.nx;
                const at = leaflet.latLngToContainerPoint(view.fit.toLatLng(g.x0 + (i + 0.5) * g.side, g.y0 + (j + 0.5) * g.side));
                if (map.pickAt(at.x, at.y, true).length === 0 && T.clear(at.x + box.left, at.y + box.top, 12))
                  return {x: at.x + box.left, y: at.y + box.top, side: g.side, x0: g.x0 + i * g.side, y0: g.y0 + j * g.side}; }
              return null; }""")
            assert square, "no square of the map is free for a tap"
            _tap(page, square["x"], square["y"])
            try:
                page.wait_for_function("() => window.FINDALINE_VIEW.view.level !== 'area' && !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
            except Exception:
                now = _state(page)
                raise AssertionError(("the tap on a square did not leave Area", square, area["zoom"], area["mpp"],
                                      {k: now[k] for k in ("level", "auto", "zoom", "mpp", "selected", "toast", "animating")}))
            zoomed = _state(page)
            placed = page.evaluate("""([x0, y0, side]) => { const {view} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP, box = T.box();
              const corners = [[x0, y0], [x0 + side, y0], [x0 + side, y0 + side], [x0, y0 + side]].map(([x, y]) => leaflet.latLngToContainerPoint(view.fit.toLatLng(x, y)));
              const xs = corners.map((c) => c.x), ys = corners.map((c) => c.y);
              return {left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys), free: T.free(),
                      bar: document.querySelector(".v-levels").getBoundingClientRect().bottom - box.top,
                      foot: document.querySelector(".v-status").getBoundingClientRect().top - box.top}; }""",
                                   [square["x0"], square["y0"], square["side"]])
            assert zoomed["level"] == "spots" and zoomed["mpp"] >= 0.96 * 0.999
            # the whole square between the switch and the status line, above the sheet (a fit to the map's whole box
            # would put its middle on the sheet's edge)
            assert placed["left"] >= 0 and placed["right"] <= placed["free"][2] and placed["bottom"] <= placed["free"][3], placed
            assert placed["top"] >= placed["bar"] and placed["bottom"] <= placed["foot"] + 30, placed
            print("phone 390 x 664, the controls' boxes: " + json.dumps({f"{stop} {name}": boxes for (stop, name), boxes in seen.items()
                                                                          if name in ("spots", "refused", "tap")}))
            assert page.errors == []
        finally:
            browser.close()


# Both chips on the small phone at half with a level held: the coarser chip wraps under the zoom row (no room for two
# chips beside the zoom) and the status line's two lines and its "Back to Auto" reach it (measured 2026-11-20: chip
# [8,172,219,216], status [8,200,281,248], back from 209). The user's answer of 2026-11-20: a known bug for now
# (docs/known-bugs.md). Excepted only there: one chip alone, Auto, the low stop and the Pixel stay checked
CHIPS_HALF_HELD = (("back", "coarse"), ("coarse", "status"))


def test_phone_chips(boxes_site):
    """Both phones (390 x 664, the Pixel's 412 x 839) with the uncertain shore's and the coarser terrain's controls:
    each starts folded into its chip (the user's choice of 2026-11-20 for the coarser box: the shore's rules), and no
    control covers another at the sheet's low stop and at half, Auto or a level held (Spots, Area), but for the one known
    pair (CHIPS_HALF_HELD: 390 x 664, half, a level held, both chips); with the coarser chip alone (the shore's control
    taken off the map) nothing is excepted. A chip's press opens its box (aria-expanded, the chip gone, the box's fold
    button the focus after a key's press), the fold button folds it again and gives the focus back to the chip; the
    coarser chip says "Coarser terrain" (the overlay's name) and the km² in view."""
    from playwright.sync_api import sync_playwright
    settled = "() => { const s = T.state(); return %s && s.spots.length === s.inPixels.length; }"
    fit = "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10});"
    chips = """() => [...document.querySelectorAll('.v-map .u-shore-ctl')].map((h) => { const c = h.querySelector('.u-shore-chip'), b = h.querySelector('.u-shore');
      return {coarse: h.classList.contains('u-coarse-ctl'), folded: h.classList.contains('u-shore-folded'), expanded: c.getAttribute('aria-expanded'),
              controls: c.getAttribute('aria-controls') === b.id, chip: getComputedStyle(c).display !== 'none', box: getComputedStyle(b).display !== 'none',
              text: c.textContent.trim(), name: c.getAttribute('aria-label')}; })"""
    pixel = {"viewport": {"width": 412, "height": 839}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("390 x 664", SMALL_PHONE), ("412 x 839", pixel)):
                page = _open(browser, f"{boxes_site}#run={BOXES}", context)
                page.wait_for_function(settled % "s.free[3] > s.size[1] * 0.75 && s.free[3] < s.size[1]", timeout=WAIT)
                for stop in ("low", "half"):
                    if stop == "half":
                        page.focus(".u-sheet-handle")
                        page.keyboard.press("ArrowUp")
                        page.wait_for_function(settled % "s.free[3] < s.size[1] * 0.6", timeout=WAIT)
                    for level in ("auto", "spots", "area"):
                        _state(page, fit + f"view.setLevel('{level}');")
                        known = CHIPS_HALF_HELD if (name, stop) == ("390 x 664", "half") and level != "auto" else ()
                        boxes = _apart(page, f"{name} {stop} {level}", known=known)
                        assert {"chip", "coarse", "zoom", "layers", "status"} <= set(boxes), (name, stop, level, sorted(boxes))
                got = page.evaluate(chips)
                assert [c["coarse"] for c in got] == [False, True] and all(c["folded"] and c["chip"] and not c["box"] and c["expanded"] == "false" and c["controls"] for c in got), got
                coarse = got[1]
                assert coarse["text"].startswith(WORDS["ui.coarse.layer"]) and coarse["text"].endswith("km²"), coarse
                assert coarse["name"] == WORDS["ui.coarse.unfold"].replace("{{total}}", coarse["text"][len(WORDS["ui.coarse.layer"]):].strip()), coarse
                # each opened by its chip (a key's press: the focus moves to the box's fold button), folded again by it
                for k, sel in enumerate((".v-map .u-shore-ctl:not(.u-coarse-ctl)", ".v-map .u-coarse-ctl")):
                    page.focus(f"{sel} .u-shore-chip")
                    page.keyboard.press("Enter")
                    page.wait_for_function(f"() => !document.querySelector({json.dumps(sel)}).classList.contains('u-shore-folded')", timeout=WAIT)
                    opened = page.evaluate(chips)[k]
                    assert opened["expanded"] == "true" and not opened["chip"] and opened["box"], (name, opened)
                    assert page.evaluate(f"() => document.activeElement === document.querySelector({json.dumps(sel + ' .u-shore-fold')})"), name
                    page.keyboard.press("Enter")
                    page.wait_for_function(f"() => document.querySelector({json.dumps(sel)}).classList.contains('u-shore-folded')", timeout=WAIT)
                    assert page.evaluate(f"() => document.activeElement === document.querySelector({json.dumps(sel + ' .u-shore-chip')})"), name
                # the coarser chip alone (a run with coarser terrain and no uncertain shore): it stands beside the zoom
                # and nothing is excepted, at half and at the low stop
                page.evaluate("() => document.querySelector('.v-map .u-shore-ctl:not(.u-coarse-ctl)').remove()")
                for stop in ("half", "low"):
                    if stop == "low":
                        page.focus(".u-sheet-handle")
                        page.keyboard.press("ArrowDown")
                        page.wait_for_function(settled % "s.free[3] > s.size[1] * 0.75", timeout=WAIT)
                    for level in ("auto", "spots", "area"):
                        _state(page, fit + f"view.setLevel('{level}');")
                        boxes = _apart(page, f"{name} {stop} {level}, the coarser chip alone")
                        assert "coarse" in boxes and boxes["coarse"][1] == boxes["zoom"][1], (name, stop, level, boxes)
                assert page.errors == [], (name, page.errors)
                page.context.close()
        finally:
            browser.close()


def test_phone_on_its_side(site):
    """A phone on its side (667 x 375, the phone's layout), with the shore's chip (the test's stand-in): the zoom and
    the layers stand in the level switch's row, right of Best (the user's Q2 a of 2026-11-18), the chip after the zoom
    or on the next row. No control covers another at the low stop, nor at half, but for one known pair (with a level
    held, the status line's longer sentence and its "Back to Auto" under the chip: at half, and since the user's W1
    words at the low stop too; the user's P c of 2026-11-20, docs/known-bugs.md). The map has no room for a
    line of the legend even with the sheet low: the legend is folded by itself; a press on "Legend" opens it as a panel
    above the map's other controls, within the map's height, and says so (aria-expanded); the same button, Esc (which
    ends nothing else) and a press on the map close it; at half the press lowers the sheet and opens the panel."""
    from playwright.sync_api import sync_playwright
    legend = "() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), !!document.querySelector('.v-legend'), !!document.querySelector('.v-over > .v-legend')]"
    is_ = "() => JSON.stringify((%s)()) === '%s'"
    opened, closed = is_ % (legend, '["true",true,true]'), is_ % (legend, '["false",false,false]')
    low = "() => { const s = T.state(); return s.free[3] > s.size[1] * 0.62 && s.free[3] < s.size[1]; }"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", SIDE_PHONE)
            _upright_then_hidden(page)  # (4 a: the notice; the layout under it, kept)
            page.wait_for_function(low, timeout=WAIT)
            page.evaluate(CHIP)  # the shore's chip: this run has no uncertain shore
            first = _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            assert first["selected"] is not None and page.evaluate("() => document.querySelector('.v-fold').disabled") is False
            page.wait_for_function(closed, timeout=WAIT)  # folded by itself: no room
            page.evaluate("() => T.frames()")
            # a level held: the status line's longer sentence since the user's W1 ("Kept while you zoom."), and its
            # "Back to Auto", reach under the shore's chip at the low stop too (the user's P c of 2026-11-20: the phone
            # held sideways stays a known bug; docs/known-bugs.md); every other control stays apart
            side = _apart(page, "on its side, low", known=(("back", "chip"), ("chip", "status")))
            # the zoom and the layers up in the switch's row, the zoom right of Best; the chip after the zoom or below it
            assert side["zoom"][0] >= side["best"][2] and side["zoom"][3] <= side["levels"][3] + 0.5, side
            assert side["layers"][3] <= side["levels"][3] + 0.5 and side["chip"][0] >= side["zoom"][0], side
            _tap_on(page, ".v-fold")
            page.wait_for_function(opened, timeout=WAIT)
            page.evaluate("() => T.frames()")
            panel = _over_holds(page, ".v-over > .v-legend", "the legend as a panel")
            assert panel["crossed"], panel  # it does lie over other controls here: there is no room beside them
            assert page.evaluate("() => { const e = document.querySelector('.v-over'); return e.scrollHeight <= e.clientHeight + 1 || getComputedStyle(e).overflowY === 'auto'; }")
            _tap_on(page, ".v-fold")  # the same button closes it
            page.wait_for_function(closed, timeout=WAIT)
            _tap_on(page, ".v-fold")
            page.wait_for_function(opened, timeout=WAIT)
            page.keyboard.press("Escape")  # Esc closes the panel, and nothing else: the selection stays
            page.wait_for_function(closed, timeout=WAIT)
            assert _state(page)["selected"] == first["selected"]
            _tap_on(page, ".v-fold")
            page.wait_for_function(opened, timeout=WAIT)
            # a press on the map closes it (a point of the map under no control and not under the panel, 12 px clear:
            # nearer to the credits' links the browser's touch adjustment gives the tap to a link; measured
            # 2026-11-18 on this phone: 2 or 4 px from the credits' box to its "Leaflet" link, 6 and 8 px to the "i")
            at = page.evaluate("""() => { const b = T.box(), f = T.free(), boxes = T.controls().concat([document.querySelector(".v-over").getBoundingClientRect()]);
              for (let y = f[3] - 12; y > f[1] + 12; y -= 7) for (let x = f[2] - 12; x > f[0] + 12; x -= 11) { const vx = x + b.left, vy = y + b.top;
                if (!boxes.some((c) => vx > c.left - 12 && vx < c.right + 12 && vy > c.top - 12 && vy < c.bottom + 12) && document.elementFromPoint(vx, vy)?.closest(".c-leaflet")) return {x: vx, y: vy}; }
              return null; }""")
            assert at, "no point of the map is free of the controls"
            _tap(page, at["x"], at["y"])
            page.wait_for_function(closed, timeout=WAIT)
            # at half: no control covers another under Auto; with a level held one pair is known (docs/known-bugs.md:
            # the status line's longer sentence, "... Held by you. Back to Auto", reaches under the shore's chip, which
            # fits in neither row of a map 135 px high)
            _state(page, "view.select(null); view.setLevel('auto');")
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => T.free()[3] < T.box().height * 0.6", timeout=WAIT)
            page.wait_for_function(closed, timeout=WAIT)
            page.evaluate("() => T.frames()")
            half = _apart(page, "on its side, half, Auto")
            # MapBar's `inline`: in that low a map the status line stands beside the row of buttons, their bottoms level
            assert page.evaluate("() => !!document.querySelector('.v-foot.v-foot-inline')"), half
            assert half["status"][0] >= half["help"][2] and abs(half["status"][3] - half["fold"][3]) <= 1, half
            _state(page, "view.setLevel('area');")
            page.evaluate("() => T.frames()")
            _apart(page, "on its side, half, Area held", known=(("back", "chip"), ("chip", "status")))
            # and the press on "Legend" there lowers the sheet and opens the panel
            _state(page, "view.setLevel('spots');")
            page.wait_for_function(closed, timeout=WAIT)
            _tap_on(page, ".v-fold")
            page.wait_for_function(low, timeout=WAIT)
            page.wait_for_function(opened, timeout=WAIT)
            page.evaluate("() => T.frames()")
            _over_holds(page, ".v-over > .v-legend", "the legend as a panel after the sheet was lowered")
            assert page.errors == []
        finally:
            browser.close()


TABLET = {**PHONE, "viewport": {"width": 1180, "height": 820}, "device_scale_factor": 2}  # on its side: the columns, a finger


def test_tablet_controls_apart(site):
    """A tablet on its side (1180 x 820: the desktop's columns with a finger's 44 px controls): no control of the map
    covers another at Area and at Spots (the switch is 52 px high there: Leaflet's zoom and layers stand under it)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", TABLET)
            for level in ("area", "spots"):
                _state(page, "map.fitArea({top: 70, right: 10, bottom: 80, left: 10}); "
                             f"view.setTopOnly(true); view.setBest(10); view.setLevel('{level}');")
                page.evaluate("() => T.frames()")
                boxes = _apart(page, f"a tablet, {level}")
                assert boxes["zoom"][1] >= boxes["levels"][3] + 8 - 0.5, boxes
            # the credits and the scale at R1's floor for them, 10 px (Leaflet's own 0.75rem: 9.75 px)
            sizes = page.evaluate("() => ['.v-map .leaflet-control-attribution', '.v-map .leaflet-control-scale-line']"
                                  ".map((s) => parseFloat(getComputedStyle(document.querySelector(s)).fontSize))")
            assert min(sizes) >= 10, sizes
            assert page.errors == []
        finally:
            browser.close()


PIXEL = {"viewport": {"width": 412, "height": 839}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}


def test_legend_unfolds_in_place_at_half(site):
    """The Pixel 7 (412 x 839) with the sheet at half, under Auto: the legend, folded by itself at half, fits whole in
    the room there, so a press on "Legend" unfolds it in place, not as a panel, and the sheet stays at half (Q1's rule
    lowers the sheet only where the whole legend does not fit: the q1 table's Pixel cells); nothing covers another."""
    from playwright.sync_api import sync_playwright
    legend = ("() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), !!document.querySelector('.v-legend'), "
              "!!document.querySelector('.v-over > .v-legend')]")
    # the sheet's top once it rests (the same in three frames running: its move takes 0.22 s)
    sheet = """() => new Promise((ok) => { let last = null, same = 0; const f = () => {
      const top = Math.round(document.querySelector('.u-sheet').getBoundingClientRect().top);
      same = top === last ? same + 1 : 0; last = top; if (same >= 2) ok(top); else requestAnimationFrame(f); }; f(); })"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", PIXEL)
            _state(page, "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10}); "
                         "view.setTopOnly(true); view.setBest(10); view.setLevel('auto');")
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.wait_for_function("() => T.free()[3] < T.box().height * 0.6", timeout=WAIT)
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            page.wait_for_function(f"() => JSON.stringify(({legend})()) === '[\"false\",false,false]'", timeout=WAIT)
            at = page.evaluate(sheet)
            _tap_on(page, ".v-fold")
            page.wait_for_function(f"() => JSON.stringify(({legend})()) === '[\"true\",true,false]'", timeout=WAIT)
            page.evaluate("() => T.frames()")
            whole = page.evaluate("() => { const e = document.querySelector('.v-legend'); return e.scrollHeight <= e.clientHeight + 1; }")
            assert page.evaluate(sheet) == at and whole, (at, page.evaluate(sheet), whole)
            _apart(page, "the Pixel at half, the legend unfolded")
            assert page.errors == []
        finally:
            browser.close()


def test_flash_takes_the_map_accent(site):
    """In the dark theme the crowded tap's flash (SpotMap's accent) is --accent-map, the light theme's accent, while the
    page's own accent is the dark one: the map's tiles stay light (the planner's decision of 2026-11-18)."""
    from playwright.sync_api import sync_playwright
    with open(os.path.join(REPO, "viewer", "src", "ui", "tokens.css"), encoding="utf-8") as f:
        accents = re.findall(r"--accent:\s*(#[0-9a-fA-F]{6})", f.read())  # the light block's, then the dark blocks'
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", {**DESKTOP, "color_scheme": "dark"})
            got = page.evaluate("() => [window.FINDALINE_VIEW.map.accent(), "
                                "getComputedStyle(window.FINDALINE_MAP.getContainer()).getPropertyValue('--accent').trim()]")
            assert got == [accents[0], accents[1]] and accents[0] != accents[1], (got, accents)
            assert page.errors == []
        finally:
            browser.close()


def test_pick_row_kept_in_the_legend(site):
    """At Area on the small phone (390 x 664, the sheet low) with P1's line just above the bar's foot: the legend keeps
    its "P1 pick" row whether the diamond found room or not, and the foot's top does not move between the canvas's
    passes (the user's decision of 2026-11-18: before, the row came and went with the diamond, the foot's height with
    it, and the canvas, placing its numbers again at most twice, stopped with the diamond left out though there was
    room)."""
    from playwright.sync_api import sync_playwright
    put = """([gap]) => { const {view} = window.FINDALINE_VIEW, m = window.FINDALINE_MAP, c = view.model.data.columns, row = view.picks()[0].row;
      const box = m.getContainer().getBoundingClientRect(), foot = document.querySelector('.v-foot').getBoundingClientRect();
      const p = m.latLngToContainerPoint([(c.lat1.at(row) + c.lat2.at(row)) / 2, (c.lon1.at(row) + c.lon2.at(row)) / 2]);
      m.panBy([0, Math.round(p.y - (foot.top - box.top - gap))], {animate: false}); }"""
    seen = "() => [Math.round(document.querySelector('.v-foot').getBoundingClientRect().top), !!document.querySelector('.v-legend')?.textContent.includes('P1'), window.FINDALINE_VIEW.map.legend().shapes.P === true]"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", SMALL_PHONE)
            _state(page, "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10}); "
                         "view.setTopOnly(true); view.setBest(10); view.setLevel('area');")
            for gap in (4, 12, 20, 28):  # the line's middle this many px above the foot's top: the band where it toggled
                page.evaluate(put, [gap])
                passes = []
                for _ in range(4):
                    page.evaluate("() => T.frames()")
                    passes.append(page.evaluate(seen))
                assert all(s == passes[0] for s in passes) and passes[0][1:] == [True, True], (gap, passes)
            assert page.errors == []
        finally:
            browser.close()


# The squares' values at Area as the canvas drew them (SpotMap drawn().values), each found again in its square from
# its box's middle (the run's grid through the view's fit) and checked against every control of the map by its own
# class (T.controls) and every number's shape: a value drawn crosses none of them (1 px kept: the canvas keeps PAD,
# 2 px, from the controls' boxes rounded outwards); one in its square's middle stands exactly there; one moved or left
# out had its middle taken (within PAD and that rounding, 3.5 px) and a moved one lies inside its square; every
# square a person sees has one value, of its own number. `cell`: the grid's cell of one square, its value returned;
# `byNumber`: the kinds of the numbers (P, L, A) whose box lies within 2 px of a value's middle.
VALUES = r"""([cell]) => { const {view, map} = window.FINDALINE_VIEW, m = window.FINDALINE_MAP, g = map.grid, box = T.box(), f = T.free(), d = map.drawn();
  const others = T.controls().concat(d.numbers.map((n) => n.box)), wrong = [], cells = new Map(), byNumber = new Set();
  const cross = (b, r, pad) => b.left < r.right + pad && b.right > r.left - pad && b.top < r.bottom + pad && b.bottom > r.top - pad;
  const corners = (i, j) => [[0, 0], [1, 0], [1, 1], [0, 1]].map(([u, w]) => { const p = m.latLngToContainerPoint(view.fit.toLatLng(g.x0 + (i + u) * g.side, g.y0 + (j + w) * g.side));
    return [p.x + box.left, p.y + box.top]; });
  let moved = 0, left = 0, mine = null;
  for (const v of d.values) {
    const b = v.box, x = (b.left + b.right) / 2, y = (b.top + b.bottom) / 2, at = m.containerPointToLatLng([x - box.left, y - box.top]);
    const [gx, gy] = view.fit.toGrid(at.lat, at.lng), i = Math.floor((gx - g.x0) / g.side), j = Math.floor((gy - g.y0) / g.side), k = g.cells.indexOf(j * g.nx + i);
    if (k < 0 || cells.has(k)) { wrong.push(["no square of its own", v.text, k]); continue; }
    cells.set(k, v);
    if (g.cells[k] === cell) mine = {text: v.text, moved: v.moved, left: v.left};
    const c = corners(i, j), cx = (c[0][0] + c[2][0]) / 2, cy = (c[0][1] + c[2][1]) / 2, xs = c.map((p) => p[0]).sort((p, q) => p - q), ys = c.map((p) => p[1]).sort((p, q) => p - q);
    const middle = new DOMRect(cx - b.width / 2, cy - b.height / 2, b.width, b.height), taken = others.some((r) => cross(middle, r, 3.5));
    d.numbers.forEach((n) => { if (cross(middle, n.box, 2)) byNumber.add(n.label[0]); });
    if (v.text !== String(Math.round(g.values[k]))) wrong.push(["not its square's number", v.text, g.values[k]]);
    if (v.left) { left++; if (!taken) wrong.push(["left out with its middle free", v.text]); continue; }
    if (others.some((r) => cross(b, r, 1))) wrong.push(["under a control or a number", v.text, [b.left, b.top, b.right, b.bottom]]);
    if (v.moved) {
      moved++;
      if (!taken) wrong.push(["moved with its middle free", v.text]);
      if (b.left < xs[1] - 0.5 || b.right > xs[2] + 0.5 || b.top < ys[1] - 0.5 || b.bottom > ys[2] + 0.5) wrong.push(["moved out of its square", v.text]);
    } else if (Math.abs(x - cx) > 0.5 || Math.abs(y - cy) > 0.5) wrong.push(["not in its square's middle", v.text, x - cx, y - cy]);
  }
  const labelled = g.side / view.mpp >= 26;
  g.cells.forEach((n, k) => { const i = n % g.nx, j = (n - i) / g.nx, c = corners(i, j), cx = (c[0][0] + c[2][0]) / 2 - box.left, cy = (c[0][1] + c[2][1]) / 2 - box.top;
    if (cx > f[0] && cx < f[2] && cy > f[1] && cy < f[3] && labelled !== cells.has(k)) wrong.push(["a square a person sees without its value", k]); });
  return {values: d.values.length, moved, left, wrong, mine, labelled, byNumber: [...byNumber].sort()}; }"""


def test_area_values_clear(site):
    """At Area a square's value lies under no control of the map and no pick's number (the design review's list of
    step 3c, item 3): in its square's middle where that is clear, as before; else moved inside its square; else left
    out, the square staying. On the desktop and on the small phone with the shore's chip (the test's stand-in), the
    map held at Area as it opens, then moved so that one square's middle lies on each control's middle in turn: that
    value is moved or left out, and every other one holds the rule (VALUES)."""
    from playwright.sync_api import sync_playwright
    fit = "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10});"
    area = "view.setTopOnly(true); view.setBest(10); view.setLevel('area');"
    # one square's middle onto a point of the viewport (the square of the grid's first cell with a value)
    onto = """([x, y]) => { const {view, map} = window.FINDALINE_VIEW, m = window.FINDALINE_MAP, g = map.grid, box = T.box(), i = g.cells[0] % g.nx, j = (g.cells[0] - i) / g.nx;
      const p = m.latLngToContainerPoint(view.fit.toLatLng(g.x0 + (i + 0.5) * g.side, g.y0 + (j + 0.5) * g.side));
      m.panBy([Math.round(p.x + box.left - x), Math.round(p.y + box.top - y)], {animate: false}); return g.cells[0]; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", SMALL_PHONE)):
                page = _open(browser, f"{site}#run={BIG}", context)
                if context is SMALL_PHONE:
                    page.wait_for_function("() => { const s = T.state(); return s.free[3] > s.size[1] * 0.75 && s.free[3] < s.size[1]; }", timeout=WAIT)
                    page.evaluate(CHIP)
                s = _state(page, fit + area)
                assert s["level"] == "area" and not s["auto"], (name, s["level"])
                first = page.evaluate(VALUES, [-1])
                assert first["labelled"] and first["values"] > 1 and not first["wrong"], (name, first)
                assert s["numbers"], (name, "no pick's number on the map")
                print(f"{name}, Area as it opens: {first['values']} values, {first['moved']} moved, {first['left']} left out")
                boxes, sheet = page.evaluate("() => [T.boxes(), document.querySelector('.u-sheet')?.getBoundingClientRect().top ?? 1e9]")
                frame = page.evaluate("() => { const b = T.box(); return [b.left, b.top, b.right, b.bottom]; }")
                tried = []
                for control, (x0, y0, x1, y1) in sorted(boxes.items()):
                    x, y = (x0 + x1) / 2, (y0 + y1) / 2
                    if not (frame[0] < x < frame[2] and frame[1] < y < min(frame[3], sheet)):
                        continue  # (a control outside the map's part a person sees: none here, kept for a change of the frame)
                    cell = page.evaluate(onto, [x, y])
                    page.evaluate("() => T.frames()")
                    got = page.evaluate(VALUES, [cell])
                    assert got["labelled"] and not got["wrong"], (name, control, got)
                    assert got["mine"] and (got["mine"]["moved"] or got["mine"]["left"]), (name, control, got)
                    tried.append(control)
                    print(f"{name}, a square's middle on {control}: {got['values']} values, {got['moved']} moved, "
                          f"{got['left']} left out")
                assert {"status", "levels", "best", "zoom", "layers", "scale"} <= set(tried), (name, tried)
                if context is SMALL_PHONE:
                    assert {"chip", "fold", "legend", "top"} <= set(tried), (name, tried)
                assert page.errors == [], (name, page.errors)
                page.context.close()
        finally:
            browser.close()


def test_area_values_clear_of_the_fan_and_selection(site):
    """At Area held the squares' values keep clear of the numbers drawn after the squares too: "Lines from here"
    opened at P1's first anchor (the fan's L1 … and P1 drawn by the fan), then P1's line selected (A1 and A2 on its
    anchors). On the desktop and the small phone with the shore's chip: every value holds VALUES' rule (none under a
    control or a number), and in each of the two states a number of that kind took some value's middle (else the
    state would test nothing)."""
    from playwright.sync_api import sync_playwright
    fit = "map.fitArea({top: 115, right: 10, bottom: T.box().height - T.free()[3] + 80, left: 10});"
    area = "view.setTopOnly(true); view.setBest(10); view.setLevel('area');"
    fan = ("const row = view.picks()[0].row, c = view.model.data.columns; "
           "view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1});")
    select = "view.closeFan(); const pick = view.picks()[0]; view.select(pick.spot, pick.row);"
    took = {"fan": set(), "selected": set()}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name, context in (("desktop", DESKTOP), ("phone", SMALL_PHONE)):
                page = _open(browser, f"{site}#run={BIG}", context)
                if context is SMALL_PHONE:
                    page.wait_for_function("() => { const s = T.state(); return s.free[3] > s.size[1] * 0.75 && s.free[3] < s.size[1]; }", timeout=WAIT)
                    page.evaluate(CHIP)
                _state(page, fit + area)
                for state, script, kinds in (("fan", fan, {"L", "P"}), ("selected", select, {"A"})):
                    page.evaluate("() => { const {view} = window.FINDALINE_VIEW; %s }" % script)
                    page.wait_for_function("() => !window.FINDALINE_MAP._animatingZoom", timeout=WAIT)
                    s = _state(page)
                    labels = {n["label"][0] for n in s["numbers"]}
                    assert s["level"] == "area" and not s["auto"] and kinds & labels, (name, state, s["level"], sorted(labels))
                    assert (s["fan"] is not None) == (state == "fan") and (s["selected"] is not None) == (state == "selected"), (name, state)
                    got = page.evaluate(VALUES, [-1])
                    assert got["labelled"] and not got["wrong"], (name, state, got)
                    took[state] |= set(got["byNumber"]) & kinds
                    print(f"{name}, {state}: numbers {sorted(n['label'] for n in s['numbers'])}; {got['values']} values, "
                          f"{got['moved']} moved, {got['left']} left out; middles taken by {got['byNumber']}")
                assert page.errors == [], (name, page.errors)
                page.context.close()
        finally:
            browser.close()
    assert "L" in took["fan"] and took["selected"] == {"A"}, took  # (an L is the fan's own: a P may be a pick's)


LANDSCAPES =((844, 390), (852, 393), (915, 412), (932, 430))  # phones held sideways, 768 px wide or more: the columns
# A run's long data credits (this run has none; the ui_shots clip's run to 8 lines in the columns): credits.ts's own
# markup (layers.ts creditsHtml with its "Data credits" button) put into the map's attribution
LONG_CREDITS = """() => { const words = 'Source: Glowny Urzad Geodezji i Kartografii, the numerical terrain model (CC BY 4.0) | FABDEM V1-2 (CC BY-NC-SA 4.0) | ';
  window.FINDALINE_MAP.attributionControl.addAttribution('<button type="button" class="u-credits-toggle" aria-expanded="false">Data credits</button>'
    + '<span class="u-credits">Data: ' + words.repeat(6) + 'Processed by the app. Notices</span>'); }"""


def test_landscape_phone_columns_fold_the_legend(site):
    """A phone held sideways that is 768 px wide or more (844 x 390 to 932 x 430: the columns with a finger's
    44 px controls), at Auto and at Area: the unfolded legend would reach the map's top controls, so it is folded
    behind "Legend" (the phone's logic, the user's decision of 2026-11-18), and the zoom's + and − stand side by side
    as on a phone (the planner's: in a column of 88 px it lay under the status line and the hint, as on main); a
    finger's tap at each level button's middle presses that button (the status line covered them before); "Legend"
    opens the legend; no control covers another. With a run's long data credits too (a stand-in of 8 lines' length:
    the design review's D1, where the status line lay on the switch): they fold behind "Data credits", as on a phone,
    and all of the above holds (the window turned from a wide one first, as a phone is: the foot's choice counts the
    credits unfolded, so folding them does not undo it)."""
    from playwright.sync_api import sync_playwright
    hit = """([k]) => { const b = document.querySelector(`.v-levels button[data-level="${k}"]`), r = b.getBoundingClientRect(),
      x = r.left + r.width / 2, y = r.top + r.height / 2, e = document.elementFromPoint(x, y); return {x, y, hit: !!e && b.contains(e)}; }"""
    pressed = "([k]) => document.querySelector(`.v-levels button[data-level=\"${k}\"]`).getAttribute('aria-pressed') === 'true'"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for (w, h), level, long in [(size, level, long) for size in LANDSCAPES for level in ("auto", "area") for long in (False, True)]:
                    state = f"{w} x {h}, {level}{', long credits' if long else ''}"
                    page = _open(browser, f"{site}#run={BIG}", {**PHONE, "viewport": {"width": w, "height": h}})
                    _upright_then_hidden(page)  # (4 a: the notice; the layout under it, kept)
                    if long:
                        page.evaluate(LONG_CREDITS)
                        page.set_viewport_size({"width": 1400, "height": 900})  # a phone turned: the credits drawn whole first
                        page.evaluate("() => T.frames()")
                        page.set_viewport_size({"width": w, "height": h})
                    _state(page, "map.fitArea({top: 70, right: 10, bottom: 80, left: 10}); "
                                 f"view.setTopOnly(true); view.setBest(10); view.setLevel('{level}');")
                    page.evaluate("() => T.frames()")
                    fold = page.evaluate("() => [!!document.querySelector('.c-result-phone'), !!document.querySelector('.v-legend'), "
                                         "document.querySelector('.v-fold')?.getAttribute('aria-expanded') ?? null]")
                    assert fold == [False, False, "false"], (state, fold)  # the columns, the legend folded behind its button
                    if long:  # the credits folded behind their button, as on a phone
                        credits = page.evaluate("() => { const t = document.querySelector('.v-map .u-credits-toggle'), c = document.querySelector('.v-map .u-credits'); "
                                                "return [!!document.querySelector('.v-map.v-compact'), getComputedStyle(t).display !== 'none', getComputedStyle(c).display === 'none']; }")
                        assert credits == [True, True, True], (state, credits)
                    boxes = _apart(page, state)
                    assert boxes["zoom"][2] - boxes["zoom"][0] > boxes["zoom"][3] - boxes["zoom"][1], (state, boxes["zoom"])  # across
                    for k in ("auto", "area", "spots", "lines"):
                        at = page.evaluate(hit, [k])
                        assert at["hit"], (state, k, at)
                        _tap(page, at["x"], at["y"])
                        page.wait_for_function(pressed, arg=[k], timeout=WAIT)
                    _tap_on(page, ".v-fold")
                    page.wait_for_function("() => !!document.querySelector('.v-legend') && "
                                           "document.querySelector('.v-fold').getAttribute('aria-expanded') === 'true'", timeout=WAIT)
                    assert page.errors == [], state
                    page.close()
        finally:
            browser.close()


def test_focus_rings(site):
    """The keyboard's focus shows on "Legend" and on the level Auto chose: the kit's ring (--focus: 2 px of the accent
    2 px off the control) beside the shadow "Legend" carries by itself (their own shadow replaced the ring: the design
    review's finding 16); the level Auto chose is underlined by a drawn bar (the pilot's), not by a shadow."""
    from playwright.sync_api import sync_playwright
    shadow = "([selector]) => getComputedStyle(document.querySelector(selector)).boxShadow"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", PHONE)
            assert _state(page)["auto"] is True
            page.keyboard.press("Tab")  # the keyboard is in use: a focused control shows its ring
            for selector in (".v-fold", ".v-levels button.v-now"):
                page.evaluate("() => document.activeElement && document.activeElement.blur()")
                own = page.evaluate(shadow, [selector])
                focused = page.evaluate("([selector]) => { const e = document.querySelector(selector); e.focus(); "
                                        "return [document.activeElement === e, e.matches(':focus-visible')]; }", [selector])
                ring = page.evaluate(shadow, [selector])
                assert focused == [True, True], selector
                # the ring is a shadow of no offset: a gap of 2 px, then 4 px of the accent, drawn beside the control's own
                assert "0px 0px 0px 4px" not in own and "0px 0px 0px 4px" in ring, (selector, own, ring)
                if selector == ".v-fold":
                    assert own != "none" and ring.startswith(own) and len(ring) > len(own), (selector, own, ring)
                else:
                    bar = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.v-levels button.v-now'), '::after'); "
                                        "return [s.content, s.height, s.backgroundColor]; }")
                    assert own == "none" and bar[0] == '""' and bar[1] == "2px", (own, bar)
            # the zoom buttons: their bar clips them to its corners, so the ring is drawn inside the button (the design
            # review's S1: the outer ring was cut away whole)
            for selector in (".v-map .leaflet-control-zoom-in", ".v-map .leaflet-control-zoom-out"):
                focused = page.evaluate("([selector]) => { const e = document.querySelector(selector); e.focus(); "
                                        "return [document.activeElement === e, e.matches(':focus-visible')]; }", [selector])
                ring = page.evaluate(shadow, [selector])
                assert focused == [True, True] and "inset" in ring and "0px 0px 0px 2px" in ring, (selector, ring)
            assert page.errors == []
        finally:
            browser.close()


def test_flag_old_run_and_blocked_storage(site):
    """Without the flag a run opens in the default (DEFAULT: today's page until gate 2); `?view=b` opens the view and
    is remembered, `?view=today` ends it; a run without the view's columns opens today's page also with the flag, and
    the console says why; with the browser's storage blocked `?view=b` still opens the view for that load and it works."""
    from playwright.sync_api import sync_playwright
    which = "() => [!!window.FINDALINE_VIEW, !!window.FINDALINE_RESULT]"
    ready = "() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=None)
            page.wait_for_function(ready, timeout=WAIT)
            assert page.evaluate(which) == [DEFAULT, not DEFAULT]
            for address, want in ((f"{site}&view=b#run={BIG}", [True, False]), (f"{site}#run={BIG}", [True, False]),
                                  (f"{site}&view=today#run={BIG}", [False, True]), (f"{site}#run={BIG}", [False, True])):
                page.goto("about:blank")
                page.goto(address)
                page.wait_for_function(ready, timeout=WAIT)
                assert page.evaluate(which) == want, address
            # today's page has the run's actions (the view too since step 3c: below)
            assert page.evaluate("() => !!document.querySelector('.r-actions')") is True
            page.close()
            # a run saved before the view's columns (a store without them): today's page, the console says why
            page = browser.new_context(**DESKTOP).new_page()
            page.add_init_script(HELPERS + FLAG)
            said = []
            page.on("console", lambda m: said.append(m.text))
            page.goto(f"{site}#run={OLD}")
            page.wait_for_function(ready, timeout=WAIT)
            assert page.evaluate(which) == [False, True]
            assert any("result view cannot show the run" in text and "no columns" in text for text in said), said
            page.close()
            # storage blocked: the address alone opens the view for this load; it works, nothing is remembered
            blocked = "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"
            page = browser.new_context(**DESKTOP).new_page()
            page.add_init_script(blocked + HELPERS)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.goto(f"{site}&view=b#run={BIG}")
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
            s = _state(page, "view.setLevel('spots'); view.select(view.order[0]);")
            assert s["level"] == "spots" and s["selected"] is not None and page.evaluate("() => !!document.querySelector('.c-result-top .r-actions')")
            _in_view_holds(s)
            page.goto("about:blank")
            page.goto(f"{site}#run={BIG}")
            page.wait_for_function(ready, timeout=WAIT)
            assert page.evaluate(which) == [DEFAULT, not DEFAULT] and errors == []
        finally:
            browser.close()
