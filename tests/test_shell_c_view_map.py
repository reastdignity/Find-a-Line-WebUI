"""The result view's map (viewer/src/result/SpotMap.ts, view/MapBar.tsx, view/SpotColumns.tsx; step 3b of
docs/line-volume/spec-view.md part B) in Playwright's Edge over the app's server, offline, on a run of the Żabi Koń
clip in the target rig with the square rule and the access mark (clip_runs.view_clip: 7 934 lines in 164 spots).
The mock-up's own checks, ported (B.7): the spots in view and the best of them against a count in the map's own
pixels, the numbers (whole on the map, under no control, on their line, apart from each other), the presses (a
number's shape, a line, an empty point, a right click and a press held for "Lines from here", an anchor's circle,
several spots under a finger), the 5 000 limit, the legend against the shapes drawn, the squares, the flag, a run
without the view's columns, storage blocked. Every wait is an event with a deadline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip, drop_store, stub_page  # noqa: E402
from test_web import EDGE, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
WAIT = 30000  # ms: the deadline of every wait for the page
DESKTOP = {"viewport": {"width": 1400, "height": 900}}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
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
    """A data folder with the clip's run (BIG) and the same run without its store's block (OLD), served by the app;
    yields the address of the app's page."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, OLD, "Old clip")
    drop_store(folder, OLD)
    page_path = stub_page(folder, "viewtest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


# The page's helpers of the checks: everything is counted in the map's own pixels from the lines' latitudes and
# longitudes (the page counts in grid metres through its fit)
HELPERS = r"""
window.T = {
  v() { return window.FINDALINE_VIEW; }, m() { return window.FINDALINE_MAP; },
  frames() { return new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0)))); },
  box() { return this.m().getContainer().getBoundingClientRect(); },
  // the part of the map's box a person sees: above a phone's sheet
  free() { const b = this.box(), sheet = document.querySelector(".u-sheet");
    return [0, 0, b.width, sheet ? Math.min(b.height, sheet.getBoundingClientRect().top - b.top) : b.height]; },
  ends(row) { const c = this.v().view.model.data.columns, m = this.m();
    const a = m.latLngToContainerPoint([c.lat1.at(row), c.lon1.at(row)]), b = m.latLngToContainerPoint([c.lat2.at(row), c.lon2.at(row)]);
    return [a.x, a.y, b.x, b.y]; },
  crosses([ax, ay, bx, by], [x0, y0, x1, y1]) { let t0 = 0, t1 = 1; const dx = bx - ax, dy = by - ay, p = [-dx, dx, -dy, dy], q = [ax - x0, x1 - ax, ay - y0, y1 - ay];
    for (let k = 0; k < 4; k++) { if (p[k] === 0) { if (q[k] < 0) return false; continue; } const r = q[k] / p[k];
      if (p[k] < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; } }
    return t1 > t0; },
  away(px, py, [ax, ay, bx, by]) { const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
    const f = l2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0; return Math.hypot(px - ax - f * dx, py - ay - f * dy); },
  controls() { return [...document.querySelectorAll(".v-map [data-map-control], .v-map .leaflet-control, .c-phone-top > *")]
    .map((e) => e.getBoundingClientRect()).filter((r) => r.width && r.height); },
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
  // a point where a press reaches several spots (no number's shape, no control there), along the lines in view
  crowded(finger) { const {view, map} = this.v(), f = this.free(), controls = this.controls(), box = this.box(), marks = map.drawn().numbers.map((n) => n.box);
    for (const spot of view.inView.spots) { const e = this.ends(view.shownOf(spot));
      for (let t = 0.1; t < 0.95; t += 0.05) { const x = Math.round(e[0] + (e[2] - e[0]) * t), y = Math.round(e[1] + (e[3] - e[1]) * t);
        if (x < f[0] + 30 || y < f[1] + 30 || x > f[2] - 30 || y > f[3] - 30) continue;
        const vx = x + box.left, vy = y + box.top;
        if (controls.concat(marks).some((c) => vx > c.left - 24 && vx < c.right + 24 && vy > c.top - 24 && vy < c.bottom + 24)) continue;
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


def _open(browser, url: str, context: dict, flag: bool = True, script: str = ""):
    """The run's page with the page's helpers; with `flag` the result view is asked for and awaited."""
    ctx = browser.new_context(**context)
    ctx.add_init_script(HELPERS + (FLAG if flag else "") + script)
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
    the tap waits until that time has passed since the touch before it."""
    page.wait_for_function("() => performance.now() - (window.TOUCHED || -1000) > 700", timeout=WAIT)
    page.touchscreen.tap(x, y)
    page.evaluate("() => { window.TOUCHED = performance.now(); }")


def _state(page, change: str = "") -> dict:
    """The page's state two frames after `change` (a script's body run in the page)."""
    if change:
        page.evaluate("() => { const {view, map} = window.FINDALINE_VIEW, leaflet = window.FINDALINE_MAP; %s }" % change)
    page.evaluate("() => T.frames()")
    return page.evaluate("() => T.state()")


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
    colours), then the access mark's three states."""
    kinds = ("sq", "P") if s["level"] == "area" else ("clear", "over", "P", "B", "pale", "A", "L", "here")
    assert s["legend"] == [k for k in kinds if k in s["shapes"]] + ["access-2", "access-1", "access-0"], s["legend"]


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
            assert first["strokes"] == first["m"] + first["thin"] and 10 < first["thin"] <= LIMIT and first["refused"] == 0
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
    """Above 5 000 thin lines the Lines level draws only the pale lines and says so, marked; with the best 100 it
    draws again. The squares' legend: the select of four values, five classes; a press on a square zooms to it and
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
            assert refused["shapes"] == ["pale"] or set(refused["shapes"]) <= {"pale", "clear", "over"}
            fewer = _state(page, "view.setBest(100);")
            assert fewer["refused"] == 0 and 100 < fewer["thin"] <= LIMIT and fewer["marked"] is False
            assert fewer["strokes"] == fewer["m"] + fewer["thin"] and fewer["numbered"] and len(fewer["numbers"]) > 10
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
            chosen = _state(page)
            assert chosen["selected"] == [spot, chosen["shown"]] and chosen["made"] == 1
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
            # several spots about as near under the mouse: none is selected (the table of spots asks which)
            crowded = page.evaluate("() => T.crowded(false)")
            assert crowded and len(crowded["spots"]) > 1
            page.mouse.click(crowded["x"], crowded["y"])
            assert _state(page)["selected"] is None and page.errors == []
        finally:
            browser.close()


def test_phone_touch(site):
    """A phone: the spots in view are those above the sheet; with the sheet lowered a tap on a number selects; a
    press held 600 ms opens "Lines from here" and the finger's lift changes nothing more; a tap on several spots
    zooms in one level around the point, says so and flashes; once the map shows 0.25 m per pixel a tap zooms no
    further."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", PHONE)
            # the sheet takes its height after the first draw: the view's rectangle is then taken again
            page.wait_for_function("() => { const s = T.state(); return s.free[3] < s.size[1] * 0.6 && s.spots.length === s.inPixels.length; }",
                                   timeout=WAIT)
            half = _state(page)
            assert half["free"][3] < half["size"][1] * 0.6  # the sheet covers the map's lower half
            _in_view_holds(half)
            _legend_holds(half)
            _numbers_hold(half, {f"B{k}" for k in range(1, 11)})
            fold = page.evaluate("() => [document.querySelector('.v-fold').getAttribute('aria-expanded'), document.querySelectorAll('.v-lg-line').length]")
            assert fold == ["true", 2]  # the legend: two lines, unfolded at the start
            page.tap(".v-fold")
            page.wait_for_function("() => !document.querySelector('.v-legend')", timeout=WAIT)
            page.tap(".v-fold")
            page.wait_for_selector(".v-legend", timeout=WAIT)
            # the sheet lowered: the view's rectangle is taken again, more spots are in view
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowDown")
            page.wait_for_function(f"() => T.free()[3] > {half['free'][3]} + 100 && T.state().spots.length === T.state().inPixels.length",
                                   timeout=WAIT)
            low = _state(page, "view.setLevel('spots');")
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
            # one quarter step closer than the last zoom above 0.25 m per pixel
            _state(page, "leaflet.setZoom(map.zoomOf(0.25) + 0.25, {animate: false});")
            last = page.evaluate("() => T.crowded(true)")
            if last:  # still several spots there: no further zoom (the table of spots is asked for)
                zoom = page.evaluate("() => window.FINDALINE_MAP.getZoom()")
                _tap(page, last["x"], last["y"])
                end = _state(page)
                assert end["zoom"] == zoom and not end["animating"] and end["mpp"] <= 0.25 * 1.001 and end["selected"] is None
            assert page.errors == []
        finally:
            browser.close()


def test_flag_old_run_and_blocked_storage(site):
    """Without the flag every run opens in today's page; `?view=b` opens the view and is remembered, `?view=today`
    ends it; a run without the view's columns opens today's page also with the flag, and the console says why;
    with the browser's storage blocked `?view=b` still opens the view for that load and it works."""
    from playwright.sync_api import sync_playwright
    which = "() => [!!window.FINDALINE_VIEW, !!window.FINDALINE_RESULT]"
    ready = "() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=False)
            page.wait_for_function(ready, timeout=WAIT)
            assert page.evaluate(which) == [False, True]
            for address, want in ((f"{site}&view=b#run={BIG}", [True, False]), (f"{site}#run={BIG}", [True, False]),
                                  (f"{site}&view=today#run={BIG}", [False, True]), (f"{site}#run={BIG}", [False, True])):
                page.goto("about:blank")
                page.goto(address)
                page.wait_for_function(ready, timeout=WAIT)
                assert page.evaluate(which) == want, address
            # the run's actions are not in the view yet; today's page has them
            assert page.evaluate("() => !!document.querySelector('.r-actions')") is True
            page.close()
            # a run saved before the view's columns (no store read): today's page, the console says why
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
            assert s["level"] == "spots" and s["selected"] is not None and not page.evaluate("() => !!document.querySelector('.r-actions')")
            _in_view_holds(s)
            page.goto("about:blank")
            page.goto(f"{site}#run={BIG}")
            page.wait_for_function(ready, timeout=WAIT)
            assert page.evaluate(which) == [False, True] and errors == []
        finally:
            browser.close()
