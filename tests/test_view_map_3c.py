"""The result view's map in step 3c (viewer/src/result/SpotMap.ts: today's features on the canvas; brief B1 of line
volume round 6), in Playwright's Edge over the app's server, offline, on the view's clip run (the fixtures of
tests/test_shell_c_view_map.py): the search area's outline at every level on both devices (over the squares' fills,
under their values, the lines and the numbers; no press reaches it; it moves no number), the favourites' gold halo
(dimmed, the selected one gold), Compare's other runs drawn apart (never counted, never pressable, following the
filters), Measure (the members RunActions' RunActionsMap needs: two presses, Esc, a new selection, a phone's map held
still) with drawMeasured and zoomToLine, the bottom part the frame covers (setCovered: not in view, no number or value
there, every move keeps it free) and the legend's `ends` (an anchor of the selected line in view). What the canvas
drew is read from its own record (SpotMap.drawn) and from the drawing calls of one full redraw (B.ops below). Every
wait is an event with a deadline (one exception: the shared _tap). Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import (DESKTOP, HELPERS, PHONE, SMALL_PHONE, WAIT, _open, _state,  # noqa: E402,F401
                                   _tap, site, view_clip)
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")

INK = "#1b2530"      # SpotMap.ts INK: the outline's colour (the mock-up's --map-ink)
GOLD = "#ffd400"     # style.ts COLORS.favourite, as the canvas reads it back
CLEAN, OVER = "#ff10f0", "#ff8c00"  # style.ts COLORS.clean, .over
OTHER_ID = "2026-11-20_120000_Other_00000000000000b1"

# The canvas's helpers of these checks (beside test_shell_c_view_map's T)
B_HELPERS = r"""
window.B = {
  // the drawing calls of one full redraw of the canvas: each fill, stroke and text with its colours, dashes, width and
  // alpha, in order (the canvas's own context, its methods wrapped for the one redraw)
  ops() { const {map} = window.FINDALINE_VIEW, ctx = document.querySelector('.v-canvas').getContext('2d'), log = [], keep = {};
    for (const name of ['fill', 'stroke', 'fillText', 'strokeText']) { keep[name] = ctx[name];
      ctx[name] = function (...a) { log.push({op: name, stroke: String(this.strokeStyle), fill: String(this.fillStyle),
        dash: this.getLineDash().join(','), width: this.lineWidth, alpha: Math.round(this.globalAlpha * 1000) / 1000,
        text: name.endsWith('Text') ? String(a[0]) : null}); return keep[name].apply(this, a); }; }
    try { map.refresh(); } finally { for (const name of Object.keys(keep)) delete ctx[name]; }
    return log; },
  // a colour as the canvas reads it back
  colour(c) { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; return String(x.fillStyle); },
  layers() { const s = getComputedStyle(window.FINDALINE_MAP.getContainer()); return [1, 2, 3, 4, 5].map((k) => this.colour(s.getPropertyValue('--layer-' + k).trim())); },
  // the run's area's rings in the map box's pixels (from the head's GeoJSON, as Leaflet projects it)
  rings() { const g = window.FINDALINE_VIEW.view.model.data.area, m = window.FINDALINE_MAP, out = [];
    const ring = (pts) => out.push(pts.map(([lon, lat]) => { const p = m.latLngToContainerPoint([lat, lon]); return [p.x, p.y]; }));
    const walk = (o) => { if (!o) return; if (o.type === 'Polygon') o.coordinates.forEach(ring); else if (o.type === 'MultiPolygon') o.coordinates.forEach((p) => p.forEach(ring));
      else if (o.type === 'Feature') walk(o.geometry); else if (o.type === 'FeatureCollection') o.features.forEach((f) => walk(f.geometry)); else if (o.type === 'GeometryCollection') o.geometries.forEach(walk); };
    walk(g); return out; },
  // the area's box from its GeoJSON: [south, west, north, east]
  areaBox() { let s = 90, w = 180, n = -90, e = -180; const g = window.FINDALINE_VIEW.view.model.data.area;
    const each = (c) => { if (typeof c[0] === 'number') { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); } else c.forEach(each); };
    const walk = (o) => { if (!o) return; if (o.coordinates) each(o.coordinates); else if (o.geometry) walk(o.geometry); else if (o.features) o.features.forEach((f) => walk(f.geometry)); else if (o.geometries) o.geometries.forEach(walk); };
    walk(g); return [s, w, n, e]; },
  // does the outline cross the part of the map a person sees (counted here in pixels), `bottom` px taken off below
  outlineInView(bottom = 0) { const f = T.free(); f[3] = Math.min(f[3], T.box().height - bottom);
    return this.rings().some((r) => r.some((p, k) => k > 0 && T.crosses([...r[k - 1], ...p], f))); },
  // a point of the outline in the part a person sees, `r` px clear of every control and number, where a press takes no
  // spot (pickAt): in the viewport, or null
  outlinePoint(r, finger) { const {map} = window.FINDALINE_VIEW, box = T.box();
    for (const ring of this.rings()) for (let k = 1; k < ring.length; k++) { const [ax, ay] = ring[k - 1], [bx, by] = ring[k];
      const n = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / 6));
      for (let j = 0; j <= n; j++) { const x = ax + (bx - ax) * j / n, y = ay + (by - ay) * j / n;
        if (!T.clear(x + box.left, y + box.top, r)) continue;
        if (map.pickAt(Math.round(x), Math.round(y), finger).length === 0 && map.pickAt(x, y, finger).length === 0) return {x: x + box.left, y: y + box.top}; } }
    return null; },
  // a copy of this run's columns moved `dlon` degrees east (another run's lines that lie beside this run's)
  moved(dlon) { const m = window.FINDALINE_VIEW.view.model, c = m.data.columns, NC = c.lon1.constructor;
    const shift = (col) => new NC(Float64Array.from({length: c.length}, (_, i) => col.at(i) + dlon), 0);
    const area = JSON.parse(JSON.stringify(m.data.area)), move = (p) => { if (typeof p[0] === 'number') p[0] += dlon; else p.forEach(move); };
    const walk = (o) => { if (!o) return; if (o.coordinates) move(o.coordinates); else if (o.geometry) walk(o.geometry); else if (o.features) o.features.forEach((f) => walk(f.geometry)); else if (o.geometries) o.geometries.forEach(walk); };
    walk(area);
    return {...m.data, area, columns: {...c, lon1: shift(c.lon1), lon2: shift(c.lon2)}}; },
  // the other run's lines in the map box's pixels
  otherEnds(dlon) { const c = window.FINDALINE_VIEW.view.model.data.columns, m = window.FINDALINE_MAP, out = [];
    for (let i = 0; i < c.length; i++) { const a = m.latLngToContainerPoint([c.lat1.at(i), c.lon1.at(i) + dlon]), b = m.latLngToContainerPoint([c.lat2.at(i), c.lon2.at(i) + dlon]);
      out.push([a.x, a.y, b.x, b.y]); } return out; },
};
"""

ORDER = "() => B.ops()"


def _page(browser, site, context):
    return _open(browser, f"{site}#run={BIG}", context, script=B_HELPERS)


def _outline(ops):
    """The index of the search area's outline among the drawing calls (the map's ink, today's dashes), else None."""
    return next((k for k, o in enumerate(ops) if o["op"] == "stroke" and o["stroke"] == INK and o["dash"] == "6,6"
                 and o["width"] == 1), None)


def _is_value(o):
    return o["op"] in ("fillText", "strokeText") and o["text"].isdigit()


def _is_mark(o):
    return o["op"] == "fillText" and o["text"][:1] in "BPLA" and o["text"][1:].isdigit()


def _is_line(o, width=None):
    return o["op"] == "stroke" and o["stroke"] in (CLEAN, OVER) and o["dash"] == "" and (width is None or o["width"] == width)


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_outline_every_level(site, device):
    """The search area's outline at Area, Spots and Lines on both devices: today's thin dashes (1 px, "6 6") in the map's
    ink; at Area over the squares' fills and under their values, the picks' lines and numbers; at Spots and Lines under
    every line and number; the legend's `area` exactly while it crosses the part a person sees; a press on it does what
    a press beside it does (it ends the selection: nothing takes the press); the numbers and the values are where they
    are without it."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, site, DESKTOP if device == "desktop" else SMALL_PHONE)
            if device == "phone":  # the sheet low, with its height
                page.wait_for_function("() => { const s = T.state(); return s.free[3] < s.size[1] && s.free[3] > s.size[1] * 0.6; }", timeout=WAIT)
            # the whole area in view, then each level held
            _state(page, "leaflet.fitBounds(map.areaBounds(), {animate: false});")
            layers = page.evaluate("() => B.layers()")
            for level in ("area", "spots", "lines"):
                s = _state(page, f"view.setLevel('{level}');")
                ops = page.evaluate(ORDER)
                drawn = page.evaluate("() => window.FINDALINE_VIEW.map.drawn()")
                k = _outline(ops)
                assert k is not None and drawn["outline"] is True, (level, ops[:5])
                assert ("area" in s["shapes"]) == page.evaluate("() => B.outlineInView()") is True, level
                if level == "area":
                    fills = [j for j, o in enumerate(ops) if o["op"] == "fill" and o["fill"] in layers]
                    values = [j for j, o in enumerate(ops) if _is_value(o)]
                    marks = [j for j, o in enumerate(ops) if _is_mark(o)]
                    lines = [j for j, o in enumerate(ops) if _is_line(o)]
                    assert fills and values and lines, (len(fills), len(values), len(lines))
                    assert max(fills) < k < min(values) and k < min(lines) and (not marks or max(values) < min(marks)), (k, fills[-1:], values[:1], marks[:1])
                else:
                    lines = [j for j, o in enumerate(ops) if _is_line(o)]
                    marks = [j for j, o in enumerate(ops) if _is_mark(o)]
                    assert lines and k < min(lines) and (not marks or k < min(marks)), (level, k, lines[:1], marks[:1])
            # the outline moves no number and no value: the canvas's places with its rings and without them
            for level in ("area", "spots"):
                _state(page, f"view.setLevel('{level}');")
                same = page.evaluate("""() => { const {map} = window.FINDALINE_VIEW, keep = map.area, read = () => { const d = map.drawn();
                    return JSON.stringify([d.numbers.map((n) => [n.label, n.box.x, n.box.y]), d.values.map((v) => [v.text, v.box.x, v.box.y, v.left])]); };
                  map.refresh(); const with_ = read(); map.area = {rings: [], box: keep.box}; map.refresh(); const without = read(); map.area = keep; map.refresh();
                  return [with_ === without, map.drawn().outline]; }""")
                assert same == [True, True], level
            # zoomed in on the area's middle the outline is out of view: no `area` in the legend
            out = _state(page, "const b = B.areaBox(); leaflet.setView([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], leaflet.getMaxZoom(), {animate: false});")
            assert ("area" in out["shapes"]) == page.evaluate("() => B.outlineInView()"), out["shapes"]
            # a press on the outline (no spot within reach there) ends the selection, as a press beside it does
            _state(page, "leaflet.fitBounds(map.areaBounds(), {animate: false}); view.setLevel('spots'); view.select(view.order[0]);")
            at = page.evaluate("([r, finger]) => B.outlinePoint(r, finger)", [24, device == "phone"])
            assert at, "no point of the outline free of lines, controls and numbers"
            misses = page.evaluate("() => window.FINDALINE_VIEW.view.fanMisses")
            if device == "desktop":
                page.mouse.click(at["x"], at["y"])
            else:
                _tap(page, at["x"], at["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.selected === null", timeout=WAIT)
            after = _state(page)
            assert after["fan"] is None and after["misses"] == misses
            assert page.errors == [], page.errors
        finally:
            browser.close()


def test_favourite_halo(site):
    """A favourite that is its spot's shown line wears today's gold halo under its line (10 px at 60 %; a spot's
    second line made a favourite becomes the shown line and wears it); dimmed with the lines while another line is
    selected; the selected favourite gold in the dark halo's place (11 px at 80 %, no dark halo); a pick at Area too;
    the legend's `fav` exactly while a halo is drawn; none once the favourites are removed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, site, DESKTOP)
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            s = _state(page, "view.setLevel('spots');")
            assert "fav" not in s["shapes"] and page.evaluate("() => window.FINDALINE_VIEW.map.drawn().halos") == 0
            # the first best spot's shown line, and the second passing line of another best spot
            rows = page.evaluate("""async () => { const {view} = window.FINDALINE_VIEW, m = view.model, best = Array.from(view.inView.best);
                const first = view.shownOf(best[0]), other = best.find((s) => s !== best[0] && view.passingCount(s) > 1);
                const second = view.passingOf(other)[1];
                await m.toggleFavourite(m.lineAt(first)); await m.toggleFavourite(m.lineAt(second));
                return {first, firstSpot: best[0], second, other}; }""")
            page.wait_for_function("([a, b]) => { const {view} = window.FINDALINE_VIEW; return view.isFavourite(a) && view.isFavourite(b); }",
                                   arg=[rows["first"], rows["second"]], timeout=WAIT)
            s = _state(page)
            assert page.evaluate("([s]) => window.FINDALINE_VIEW.view.shownOf(s)", [rows["other"]]) == rows["second"]  # B-3
            ops = page.evaluate(ORDER)
            gold = [j for j, o in enumerate(ops) if o["op"] == "stroke" and o["stroke"] == GOLD]
            bold = [j for j, o in enumerate(ops) if _is_line(o, 3)]
            assert gold and all(ops[j]["width"] == 10 and ops[j]["alpha"] == 0.6 for j in gold) and max(gold) < min(bold), [ops[j] for j in gold]
            assert "fav" in s["shapes"] and page.evaluate("() => window.FINDALINE_VIEW.map.drawn().halos") == 2
            # another line selected: the halos dimmed with the lines
            _state(page, "view.select(view.inView.best.find((s) => s !== %d && s !== %d));" % (rows["firstSpot"], rows["other"]))
            ops = page.evaluate(ORDER)
            gold = [o for o in ops if o["op"] == "stroke" and o["stroke"] == GOLD]
            assert gold and all(o["width"] == 10 and o["alpha"] == 0.18 for o in gold), gold
            # the favourite selected: gold in the dark halo's place
            _state(page, "view.select(%d);" % rows["firstSpot"])
            ops = page.evaluate(ORDER)
            assert any(o["op"] == "stroke" and o["stroke"] == GOLD and o["width"] == 11 and o["alpha"] == 0.8 for o in ops)
            assert not any(o["op"] == "stroke" and o["stroke"] == "#000000" and o["width"] == 11 for o in ops)
            assert page.evaluate("() => window.FINDALINE_VIEW.map.drawn().halos") == 2  # the other favourite's and the selected one's
            # a pick at Area made a favourite: its halo under its line
            pick = page.evaluate("""async () => { const {view} = window.FINDALINE_VIEW, m = view.model; view.select(null); view.setLevel('area');
                const row = view.picks()[0].row; if (!view.isFavourite(row)) await m.toggleFavourite(m.lineAt(row)); return row; }""")
            page.wait_for_function("([r]) => window.FINDALINE_VIEW.view.isFavourite(r)", arg=[pick], timeout=WAIT)
            s = _state(page)
            ops = page.evaluate(ORDER)
            gold = [j for j, o in enumerate(ops) if o["op"] == "stroke" and o["stroke"] == GOLD]
            picks = [j for j, o in enumerate(ops) if _is_line(o, 3.5)]
            assert gold and picks and max(gold) < min(picks) and "fav" in s["shapes"]
            # every favourite removed: no halo, no `fav`
            page.evaluate("""async () => { const m = window.FINDALINE_VIEW.view.model; for (const l of m.favouriteLines()) await m.toggleFavourite(l); }""")
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouriteLines().length === 0", timeout=WAIT)
            s = _state(page, "view.setLevel('spots');")
            assert "fav" not in s["shapes"] and not any(o["stroke"] == GOLD for o in page.evaluate(ORDER) if o["op"] == "stroke")
            assert page.errors == [], page.errors
        finally:
            browser.close()


MEASURE = """() => { const {map} = window.FINDALINE_VIEW; if (window.MEAS) window.MEAS.stop(); window.MEAS = {on: [], done: null};
  window.MEAS.stop = map.onMeasuring((v) => window.MEAS.on.push(v));
  map.startMeasure((a, b) => { window.MEAS.done = [[a.lat, a.lng], [b.lat, b.lng]]; }); }"""
MEASURED = "() => { const {map} = window.FINDALINE_VIEW; return {on: map.isMeasuring, events: window.MEAS.on, done: window.MEAS.done, points: map.drawn().measured, cursor: window.FINDALINE_MAP.getContainer().style.cursor, drag: window.FINDALINE_MAP.dragging.enabled(), dbl: window.FINDALINE_MAP.doubleClickZoom.enabled()}; }"


@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_measure(site, device):
    """Measure's members (RunActions' RunActionsMap): while measuring a press on a number's shape is a point (no
    selection, no fan), a right click opens no "Lines from here" (desktop), the cursor is a crosshair; the second press
    ends it and gives both points; the measurement drawn as black dashes "6 4" between white points over every line
    and number; a deselection keeps it, a new selection clears it; Esc while measuring cancels and clears it and keeps
    the selection (the frame's Esc does nothing more); a new selection while measuring ends it. A phone's map holds
    still: no drag and no double tap's zoom while measuring (two quick taps leave the zoom and the middle), both back
    after it; a desktop's map keeps its drag. drawMeasured draws and clears a given line; areaBounds is the area's box."""
    from playwright.sync_api import sync_playwright
    finger = device == "phone"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, site, DESKTOP if device == "desktop" else SMALL_PHONE)
            if finger:
                page.wait_for_function("() => { const s = T.state(); return s.free[3] < s.size[1] && s.free[3] > s.size[1] * 0.6; }", timeout=WAIT)
            press = (lambda x, y: _tap(page, x, y)) if finger else (lambda x, y: page.mouse.click(x, y))
            sel = _state(page, "view.setLevel('spots'); view.select(view.order[0]);")["selected"]
            page.evaluate(MEASURE)
            m = page.evaluate(MEASURED)
            assert m["on"] is True and m["events"] == [True] and m["cursor"] == "crosshair" and m["points"] == []
            assert (m["drag"], m["dbl"]) == ((False, False) if finger else (True, True))
            number = next(n for n in _state(page)["numbers"] if n["label"][0] == "B")
            box = page.evaluate("() => { const b = T.box(); return [b.left, b.top]; }")
            press(box[0] + number["x"], box[1] + number["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.map.drawn().measured.length === 1", timeout=WAIT)
            s = _state(page)
            assert s["selected"] == sel and s["fan"] is None, s["selected"]
            first = page.evaluate(MEASURED)["points"][0]
            assert abs(first["x"] - box[0] - number["x"]) < 1.5 and abs(first["y"] - box[1] - number["y"]) < 1.5
            if not finger:  # a right click while measuring: no "Lines from here", no point
                a = page.evaluate("([spots]) => T.anchor(spots, 24)", [s["spots"]])
                page.mouse.click(a["x"], a["y"], button="right")
                page.evaluate("() => T.frames()")
                assert _state(page)["fan"] is None and page.evaluate(MEASURED)["points"].__len__() == 1
            view = page.evaluate("() => [window.FINDALINE_MAP.getZoom(), window.FINDALINE_MAP.getCenter().lat, window.FINDALINE_MAP.getCenter().lng]")
            empty = page.evaluate("([f]) => T.empty(f)", [finger])
            if finger:  # at once after the first tap: a double tap where the map would zoom (but it holds still)
                page.touchscreen.tap(empty["x"], empty["y"])
            else:
                press(empty["x"], empty["y"])
            page.wait_for_function("() => window.MEAS.done !== null", timeout=WAIT)
            m = page.evaluate(MEASURED)
            assert m["on"] is False and m["events"] == [True, False] and len(m["points"]) == 2 and m["cursor"] == "", m
            # the drag and the double tap's zoom back once the tap's own events are over (the dblclick zoomed nothing)
            page.wait_for_function("() => window.FINDALINE_MAP.dragging.enabled() && window.FINDALINE_MAP.doubleClickZoom.enabled()", timeout=WAIT)
            page.evaluate("() => T.frames()")
            assert page.evaluate("() => [window.FINDALINE_MAP.getZoom(), window.FINDALINE_MAP.getCenter().lat, window.FINDALINE_MAP.getCenter().lng]") == view
            # the points given are where the presses were
            given = page.evaluate("() => window.MEAS.done.map(([lat, lng]) => { const p = window.FINDALINE_MAP.latLngToContainerPoint([lat, lng]), b = T.box(); return [p.x + b.left, p.y + b.top]; })")
            assert abs(given[1][0] - empty["x"]) < 1.5 and abs(given[1][1] - empty["y"]) < 1.5, (given, empty)
            # drawn over every line and number: the dashes, then the white points
            ops = page.evaluate(ORDER)
            dashes = [j for j, o in enumerate(ops) if o["op"] == "stroke" and o["stroke"] == "#000000" and o["dash"] == "6,4" and o["width"] == 2]
            points = [j for j, o in enumerate(ops) if o["op"] == "fill" and o["fill"] == "#ffffff" and j > (dashes or [0])[0]]
            assert len(dashes) == 1 and len(points) >= 2
            assert dashes[0] > max(j for j, o in enumerate(ops) if _is_line(o) or _is_mark(o)), dashes
            assert "measure" in _state(page)["shapes"]
            # a deselection keeps it; a new selection clears it
            _state(page, "view.select(null);")
            assert len(page.evaluate(MEASURED)["points"]) == 2
            _state(page, "view.select(view.order[1]);")
            assert page.evaluate(MEASURED)["points"] == []
            # Esc while measuring: cancelled and cleared, the selection stays
            sel = _state(page, "view.select(view.order[0]);")["selected"]
            page.evaluate(MEASURE)
            empty = page.evaluate("([f]) => T.empty(f)", [finger])
            press(empty["x"], empty["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.map.drawn().measured.length === 1", timeout=WAIT)
            page.keyboard.press("Escape")
            m = page.evaluate(MEASURED)
            assert m["on"] is False and m["points"] == [] and m["events"] == [True, False] and m["done"] is None
            assert (m["drag"], m["dbl"]) == (True, True)  # at once: no press under way
            assert _state(page)["selected"] == sel
            # a new selection while measuring ends it
            page.evaluate(MEASURE)
            _state(page, "view.select(view.order[1]);")
            m = page.evaluate(MEASURED)
            assert m["on"] is False and m["events"] == [True, False] and m["points"] == []
            # drawMeasured: a line given by the frame drawn as a measurement, and cleared
            line = page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, l = view.model.lineAt(view.shownOf(view.order[2]));
                map.drawMeasured({lat1: l.lat1, lon1: l.lon1, lat2: l.lat2, lon2: l.lon2}); return [l.lat1, l.lon1, l.lat2, l.lon2]; }""")
            pts = page.evaluate("() => window.FINDALINE_VIEW.map.drawn().measured")
            ends = page.evaluate("([a, b, c, d]) => [[a, b], [c, d]].map(([lat, lng]) => { const p = window.FINDALINE_MAP.latLngToContainerPoint([lat, lng]), x = T.box(); return [p.x + x.left, p.y + x.top]; })", line)
            assert len(pts) == 2 and all(abs(p["x"] - e[0]) < 0.01 and abs(p["y"] - e[1]) < 0.01 for p, e in zip(pts, ends))
            page.evaluate("() => window.FINDALINE_VIEW.map.drawMeasured(null)")
            assert page.evaluate("() => window.FINDALINE_VIEW.map.drawn().measured") == []
            # areaBounds: the area's box
            got = page.evaluate("() => { const b = window.FINDALINE_VIEW.map.areaBounds(); return [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]; }")
            assert got == pytest.approx(page.evaluate("() => B.areaBox()"), abs=1e-9)
            assert page.errors == [], page.errors
        finally:
            browser.close()


def test_covered_and_ends(site):
    """setCovered (the desktop's card over the map's bottom): the spots in view are those whose shown line crosses the
    map above it (counted in pixels); no number below its top; at Area no value drawn reaches into it; zoomTo and
    zoomToLine keep a line above it; 0 gives the whole map back. The legend's `ends`: set while an anchor of the
    selected line is in the part a person sees, not while both are off it or only under the covered part."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, site, DESKTOP)
            whole = _state(page, "view.setLevel('spots');")
            height = whole["size"][1]
            cover = 300
            s = _state(page, f"map.setCovered({cover});")
            assert page.evaluate("() => window.FINDALINE_VIEW.map.covered") == cover
            seen = page.evaluate("""([cover]) => { const {view} = window.FINDALINE_VIEW, f = T.free(); f[3] -= cover;
                return Array.from(view.order).filter((s) => T.crosses(T.ends(view.shownOf(s)), f)); }""", [cover])
            assert s["spots"] == seen and 0 < s["m"] < whole["m"], (s["m"], whole["m"])
            top = page.evaluate("() => T.box().top") + height - cover
            assert s["numbers"] and all(n["y"] + n["h"] / 2 <= height - cover + 0.5 for n in s["numbers"]), s["numbers"]
            area = _state(page, "view.setLevel('area'); leaflet.fitBounds(map.areaBounds(), {animate: false});")
            values = page.evaluate("() => window.FINDALINE_VIEW.map.drawn().values.filter((v) => !v.left).map((v) => v.box.bottom)")
            assert values and all(b <= top - 2 + 0.01 for b in values), (max(values), top)
            assert area["level"] == "area"
            # a move keeps the line above the covered part
            for move in ("map.zoomTo(view.shownOf(view.order[0]));",
                         "const l = view.model.lineAt(view.shownOf(view.order[1])); map.zoomToLine({lat1: l.lat1, lon1: l.lon1, lat2: l.lat2, lon2: l.lon2});"):
                _state(page, "view.setLevel('spots'); " + move)
                row = page.evaluate("() => { const {view} = window.FINDALINE_VIEW; return [view.shownOf(view.order[0]), view.shownOf(view.order[1])]; }")[0 if "zoomTo(" in move else 1]
                e = page.evaluate("([r]) => T.ends(r)", [row])
                assert max(e[1], e[3]) <= height - cover - 50 and min(e[1], e[3]) >= 0, (move, e)
            # ends: the selected line's anchors in the part a person sees
            _state(page, "map.setCovered(0); view.select(view.order[0]);")
            e = page.evaluate("() => T.ends(window.FINDALINE_VIEW.view.selected.row)")
            assert "ends" in _state(page)["shapes"]
            heard = page.evaluate("() => { window.HEARD = 0; window.FINDALINE_VIEW.map.subscribe(() => { window.HEARD++; }); return 0; }")
            # both anchors off the map: the map moved so the line lies left of its box
            s = _state(page, "const b = T.box(), e = T.ends(view.selected.row); leaflet.panBy([Math.max(e[0], e[2]) + 80, 0], {animate: false});")
            assert "ends" not in s["shapes"] and "A" in s["shapes"] and page.evaluate("() => window.HEARD") > heard
            # one anchor in view: back by half the line's width plus a little
            s = _state(page, "const e = T.ends(view.selected.row), x = Math.min(e[0], e[2]); leaflet.panBy([x - 40, 0], {animate: false});")
            e = page.evaluate("() => T.ends(window.FINDALINE_VIEW.view.selected.row)")
            inside = [0 <= e[k] <= whole["size"][0] and 0 <= e[k + 1] <= height for k in (0, 2)]
            assert any(inside) and "ends" in s["shapes"], (e, inside)
            # the anchors in view only under the covered part: they do not count
            seen = [e[k + 1] for k in (0, 2) if inside[k // 2]]
            s = _state(page, f"map.setCovered({int(height - min(seen) + 4)});")
            assert "ends" not in s["shapes"], (e, s["shapes"])
            _state(page, "map.setCovered(0);")
            assert page.evaluate("() => window.FINDALINE_VIEW.map.covered") == 0
            assert page.errors == [], page.errors
        finally:
            browser.close()


def test_other_runs_apart(site):
    """Compare's other runs (ResultModel.others): drawn in the run's colour with its dashed area, its lines 2.5 px (over
    trees dashed "6 4") under this run's lines, dimmed while a line is selected; following the filters (Favourites only
    included, not "Top level only"); never counted: the spots in view, the best, the numbers, the strokes, the picks
    and the squares' values are those without it; never pressable (a press on its line far from this run's lines does
    what an empty point does); the legend's `runs` lists it while drawn in view; removed, nothing of it is left."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, site, DESKTOP)
            # the other run: this run's lines moved east by the lines' own width and a half (beside them)
            dlon = page.evaluate("() => { const b = B.areaBox(); return (b[3] - b[1]) * 0.6; }")
            page.evaluate("([d]) => { const b = B.areaBox(); window.FINDALINE_MAP.fitBounds([[b[0], b[1]], [b[2], b[3] + d]], {animate: false}); }", [dlon])

            def snapshot(level):
                _state(page, f"view.setLevel('{level}');")
                return page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, d = map.drawn(), v = view.inView;
                    return JSON.stringify({spots: Array.from(v.spots), best: Array.from(v.best), m: v.m, strokes: d.strokes, counts: view.counts,
                      numbers: d.numbers.map((n) => [n.label, Math.round(n.box.x * 100), Math.round(n.box.y * 100)]), picks: view.picks().map((p) => p.row),
                      values: d.values.map((x) => [x.text, Math.round(x.box.x * 100), Math.round(x.box.y * 100), x.left])}); }""")
            before = {level: snapshot(level) for level in ("area", "spots", "lines")}
            info = {"id": OTHER_ID, "name": "Other run", "created": "2026-11-20T12:00:00", "has_lines": True}
            page.evaluate("([info, dlon]) => { const m = window.FINDALINE_VIEW.view.model; m.addRun(info, B.moved(dlon)); }", [info, dlon])
            n = page.evaluate("() => window.FINDALINE_VIEW.view.model.data.columns.length")
            colour = page.evaluate("([id]) => window.FINDALINE_VIEW.view.model.others.get(id).color", [OTHER_ID])
            for level in ("area", "spots", "lines"):
                assert snapshot(level) == before[level], level
                d = page.evaluate("() => window.FINDALINE_VIEW.map.drawn()")
                assert d["others"] == [{"id": OTHER_ID, "lines": n}], d["others"]
                legend = page.evaluate("() => window.FINDALINE_VIEW.map.legend().runs")
                assert legend == [{"id": OTHER_ID, "name": "Other run", "color": colour}]
            # its strokes: the area dashed in its colour, its lines 2.5 px under this run's lines, those over trees dashed
            _state(page, "view.setLevel('spots');")
            ops = page.evaluate(ORDER)
            mine = [j for j, o in enumerate(ops) if o["op"] == "stroke" and o["stroke"] == B_colour(page, colour)]
            first = min(j for j, o in enumerate(ops) if _is_line(o))
            assert any(ops[j]["dash"] == "6,6" and ops[j]["width"] == 1 for j in mine)
            lines = [ops[j] for j in mine if ops[j]["width"] == 2.5]
            assert lines and max(j for j in mine) < first and {o["alpha"] for o in lines} == {0.9}
            assert {o["dash"] for o in lines} <= {"", "6,4"} and (page.evaluate("() => window.FINDALINE_VIEW.view.model.data.columns.over.some((v) => v)") is False
                                                                  or "6,4" in {o["dash"] for o in lines})
            ops = page.evaluate("() => { window.FINDALINE_VIEW.view.select(window.FINDALINE_VIEW.view.order[0]); return B.ops(); }")
            assert {o["alpha"] for o in ops if o["op"] == "stroke" and o["stroke"] == B_colour(page, colour) and o["width"] == 2.5} == {0.27}
            # never pressable: a point on its line far from this run's lines does what an empty point does
            at = page.evaluate("""([dlon]) => { const {map} = window.FINDALINE_VIEW, box = T.box();
                for (const [ax, ay, bx, by] of B.otherEnds(dlon)) for (let t = 0.2; t < 0.85; t += 0.1) { const x = ax + (bx - ax) * t, y = ay + (by - ay) * t;
                  if (!T.clear(x + box.left, y + box.top, 30)) continue;
                  if (map.pickAt(Math.round(x), Math.round(y), false).length === 0) return {x: x + box.left, y: y + box.top}; }
                return null; }""", [dlon])
            assert at, "no point of the other run's lines away from this run's"
            page.mouse.click(at["x"], at["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.selected === null", timeout=WAIT)
            assert _state(page)["fan"] is None
            # the filters: a length filter and the lines over trees left out, as for this run's lines
            got = page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, m = view.model, c = m.data.columns, len = view.values.len;
                const sorted = Array.from(len).sort((a, b) => a - b), at = sorted[Math.floor(sorted.length / 2)];
                m.setFilters({...m.filters, lenMin: Math.round(at)}); map.refresh();
                const long = map.drawn().others[0].lines;
                m.setState({...m.state, showOver: false}); map.refresh();
                const clear = map.drawn().others[0].lines;
                let wantLong = 0, wantClear = 0;
                for (let i = 0; i < c.length; i++) { if (len[i] >= Math.round(at)) { wantLong++; if (!c.over[i]) wantClear++; } }
                m.setState({...m.state, showOver: true}); m.setFilters({...m.filters, lenMin: null});
                return {long, clear, wantLong, wantClear}; }""")
            assert got["long"] == got["wantLong"] and got["clear"] == got["wantClear"] and got["clear"] < got["long"] < n, got
            # Favourites only: none of the other run's lines is a favourite, none is drawn
            page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
            fav = page.evaluate("""() => { const {view, map} = window.FINDALINE_VIEW, m = view.model; m.setFilters({...m.filters, favOnly: true}); map.refresh();
                const on = map.drawn().others[0].lines; m.setFilters({...m.filters, favOnly: false}); map.refresh(); return [on, map.drawn().others[0].lines]; }""")
            assert fav == [0, n], fav
            # "Top level only" off and on changes nothing of it
            tops = page.evaluate("() => { const {view, map} = window.FINDALINE_VIEW; view.setTopOnly(false); map.refresh(); const a = map.drawn().others[0].lines; view.setTopOnly(true); map.refresh(); return [a, map.drawn().others[0].lines]; }")
            assert tops == [n, n]
            # removed: nothing of it drawn, no `runs`
            s = _state(page, f"view.model.removeRun('{OTHER_ID}');")
            assert page.evaluate("() => window.FINDALINE_VIEW.map.drawn().others") == [] and page.evaluate("() => window.FINDALINE_VIEW.map.legend().runs") == []
            assert s["level"]
            assert page.errors == [], page.errors
        finally:
            browser.close()


def B_colour(page, colour):
    """A colour as the canvas reads it back."""
    return page.evaluate("([c]) => B.colour(c)", [colour])
