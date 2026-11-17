// A test page of the result view's frame (result/view/SpotColumns.tsx) with its model of spots and its canvas, on
// a made-up run (window.MADE: rows of data.js, the view's three columns and a head, written by
// tests/test_view_units.py, which opens the page in headless Edge from the app's server, under its CSP): the flag,
// the frame in columns and on a phone, the first draw (window.FINDALINE_VIEW), the switch, Best, the status line,
// the slots, Esc. The findings go into <pre id="result"> as JSON.

import { h, render } from "preact";
import "leaflet/dist/leaflet.css";
import "../src/ui/ui.css";
import { ResultModel } from "../src/result/model";
import type { SpotMap } from "../src/result/SpotMap";
import type { SpotView } from "../src/result/spots";
import { clipper } from "../src/result/viewgeom";
import { opensView, SpotColumns, viewWanted } from "../src/result/view/SpotColumns";
import type { SpotPanels } from "../src/result/view/SpotPanels";
import { lineColumns, type LineRow, type RunData, type RunHead } from "../src/types";

interface Made { rows: LineRow[]; head: RunHead; view: {spot: number[]; top: number[]; by_spot: number[]} }

const out: Record<string, unknown> = {};
const finish = () => {
  const pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
};
const shown = (): {view: SpotView; map: SpotMap} | undefined => (window as any).FINDALINE_VIEW;
/** Wait until `test` holds (the page draws after its effects), asked every 50 ms, 5 s at most. The page waits
 *  nowhere for a fixed time: every wait is this one, for something it then reads. */
async function until(test: () => boolean): Promise<boolean> {
  for (let k = 0; k < 100 && !test(); k++) await new Promise((resolve) => setTimeout(resolve, 50));
  return test();
}
const draws = () => performance.getEntriesByName("fal:view:draw").length;
const kindsListed = () => new Set(Array.from(document.querySelectorAll<HTMLElement>(".v-legend [data-kind]"), (e) => e.dataset.kind));
/** Wait until the page shows the canvas's picture as it stays: the legend lists the numbers' shapes and the pale
 *  lines the canvas drew (the page draws it after the canvas says so), and the canvas has not drawn again between
 *  two askings 50 ms apart (it places its numbers again on a zero timer when a control changed its size after a
 *  draw). This is a quiet time, not an event: the canvas tells nobody that it will not draw again; what is read
 *  after it does not depend on a later draw of the same view (the frame draws once more 120 ms after a phone's
 *  sheet moved: the same rectangle again). */
async function rested(): Promise<boolean> {
  let before = -1;
  return until(() => {
    const now = draws(), same = now === before, map = shown()?.map;
    before = now;
    if (!same || !map) return false;
    if (!document.querySelector(".v-legend")) return true;  // a phone's legend folded
    const on = map.legend().shapes as Record<string, true | undefined>, listed = kindsListed();
    return ["sq", "P", "B", "pale", "L"].every((kind) => !!on[kind] === listed.has(kind));
  });
}
const text = (selector: string) => document.querySelector(selector)?.textContent ?? null;
const pressed = () => Array.from(document.querySelectorAll<HTMLElement>(".v-levels button"),
                                 (b) => [b.dataset.level, b.getAttribute("aria-pressed"), b.classList.contains("v-now")]);
const measures = () => [...new Set(performance.getEntriesByType("measure").map((e) => e.name))].sort();
/** The picture now: the page's own count of strokes, the numbers on the map, the legend's shapes (the canvas's and
 *  the page's), the thin lines the view counted, and whether the canvas holds any ink. */
function picture(view: SpotView, map: SpotMap) {
  const d = map.drawn(), canvas = document.querySelector<HTMLCanvasElement>(".v-canvas")!;
  const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
  let ink = 0;
  for (let k = 3; k < pixels.length; k += 4) if (pixels[k]) ink++;
  return {strokes: d.strokes, numbers: d.numbers.map((n) => n.label), shapes: Object.keys(map.legend().shapes).sort(),
          legend: Array.from(document.querySelectorAll<HTMLElement>(".v-legend [data-kind]"), (e) => e.dataset.kind),
          thin: view.inView.strokes, picks: view.picks().length, ink: ink > 0,
          boxes: d.numbers.map((n) => [Math.round(n.box.left), Math.round(n.box.top), Math.round(n.box.right), Math.round(n.box.bottom)])};
}
/** The spots whose shown line crosses a rectangle of the map's box, counted in the map's own pixels from the
 *  line's latitudes and longitudes (the page counts them in grid metres through its fit). */
function inPixels(view: SpotView, [left, top, right, bottom]: number[]): number {
  const leaflet = (window as any).FINDALINE_MAP, c = view.model.data.columns;
  const cross = clipper([[left, top], [right, top], [right, bottom], [left, bottom]]);
  let n = 0;
  for (const spot of view.order) {
    const row = view.shownOf(spot);
    const a = leaflet.latLngToContainerPoint([c.lat1.at(row), c.lon1.at(row)]), b = leaflet.latLngToContainerPoint([c.lat2.at(row), c.lon2.at(row)]);
    if (cross(a.x, a.y, b.x, b.y)) n++;
  }
  return n;
}

/** The page came to rest (rested), else the page's run ends here with the reason: no silent five seconds. */
async function rest(after: string) {
  if (!(await rested())) throw new Error(`the page did not come to rest after ${after}`);
}

(async () => { try {
  const made = (window as any).MADE as Made;
  const data: RunData = {...made.head, columns: lineColumns(made.rows, null, made.head.ends),
                         view: {spot: Uint32Array.from(made.view.spot), top: Uint8Array.from(made.view.top),
                                bySpot: Uint32Array.from(made.view.by_spot)}};
  // the flag: nothing asked, then kept in the browser's storage
  const before = [viewWanted(), opensView(data)];
  localStorage.setItem("findaline.view", "b");
  out.flag = {before, wanted: viewWanted(), opens: opensView(data), old: opensView({...data, view: undefined})};

  document.body.style.margin = "0";
  const root = document.createElement("div");
  root.className = "ui";
  root.style.cssText = "width:1400px;height:900px;display:flex;position:relative";
  document.body.appendChild(root);
  const model = new ResultModel(data, {ungrouped: true, favourites: false, profiles: false});
  // the slots filled by the page's own panels (the frame's default ones are the view's real panels)
  const panels: SpotPanels = {
    list: () => h("p", {"data-slot": "list"}, "the list's slot"), details: () => h("p", {"data-slot": "details"}, "the details' slot"),
    sheetHead: (p) => { (window as any).PANEL = p; return h("b", {"data-slot": "head"}, "the sheet's head"); },
    hint: (p) => h("button", {type: "button", "data-slot": "hint-" + p.place}, "?")};
  const props = {runId: data.run.id, line: null, nav: 0, hashOf: () => "", model, data, panels};
  const places = () => Array.from(document.querySelectorAll<HTMLElement>("[data-slot^=hint], [data-slot=head]"),
                                  (e) => [e.dataset.slot, e.closest(".v-row") ? "map" : e.closest(".u-sheet") ? "sheet" : "?"]);
  render(h(SpotColumns, {...props, wide: true}), root);
  out.drawn = await until(() => !!shown());
  const {view, map} = shown()!;
  const status = () => text(".v-status-text");
  out.first = {level: view.level, auto: view.auto, best: view.best, m: view.inView.m, spots: view.counts.spots, status: status(),
               pressed: pressed(), mpp: view.mpp, slots: [text("[data-slot=list]"), text("[data-slot=details]")], places: places(),
               result: (window as any).FINDALINE_RESULT === undefined, leaflet: (window as any).FINDALINE_MAP === (map as any).map,
               controls: [".leaflet-control-zoom", ".leaflet-control-layers", ".leaflet-control-scale", ".leaflet-control-attribution"]
                 .map((s) => !!document.querySelector(s)),
               header: text(".c-run-title"), actions: !!document.querySelector(".r-actions"), measures: measures(),
               drawn: picture(view, map), bestOff: document.querySelector<HTMLSelectElement>(".v-best select")?.disabled,
               snap: [(window as any).FINDALINE_MAP.options.zoomSnap, (window as any).FINDALINE_MAP.options.zoomDelta]};
  // a level held, and back to Auto
  document.querySelector<HTMLElement>('.v-levels button[data-level="lines"]')!.click();
  await until(() => !!document.querySelector(".v-back-auto"));
  await rest("a change");
  out.held = {level: view.level, auto: view.auto, status: text(".v-status"), pressed: pressed(), refused: !!document.querySelector(".v-refused"),
              drawn: picture(view, map), m: view.inView.m};
  document.querySelector<HTMLElement>(".v-back-auto")!.click();
  await until(() => !document.querySelector(".v-back-auto"));
  out.back = {level: view.level, auto: view.auto, status: status()};
  // zoomed in: Auto follows the zoom, the spots in view and the status follow the map
  const leaflet = (window as any).FINDALINE_MAP;
  leaflet.setZoom(leaflet.getZoom() + 2.5, {animate: false});
  await until(() => view.level !== "area");
  await rest("a change");
  const zoomedPicture = picture(view, map);
  const mapSize = leaflet.getSize();
  const spots = {level: view.level, m: view.inView.m, best: view.inView.best.length, numbered: view.inView.numbered, status: status(),
                 zoom: leaflet.getZoom(), mpp: view.mpp, pixels: inPixels(view, [0, 0, mapSize.x, mapSize.y])};
  const select = document.querySelector<HTMLSelectElement>(".v-best select")!;
  select.value = "all";
  select.dispatchEvent(new Event("change", {bubbles: true}));
  await until(() => view.best === "all" && (status() || "").includes("all"));
  await rest("a change");
  out.spots = {...spots, drawn: zoomedPicture, all: {best: view.best, status: status(), disabled: select.disabled, drawn: picture(view, map)}};
  // a spot selected: its lines, A1 and A2 (the access mark on their corners), the rest dimmed; then "Lines from here"
  view.select(view.spotOf(0));  // the made-up run's star: its lines leave the map's middle
  await rest("a change");
  const chosen = view.selected!;
  out.selected = {drawn: picture(view, map), passing: view.passingOf(chosen.spot).length, marks: document.querySelectorAll(".v-anchor-mark").length,
                  inView: view.inView.spots.includes(chosen.spot)};
  // opened through the model (as the details' buttons do): the canvas moves the map, because far ends lie outside
  const centre = leaflet.getCenter(), zoomBefore = leaflet.getZoom(), columns = view.model.data.columns;
  const outside = () => view.fan!.rows.filter((r) => {
    const far = leaflet.latLngToContainerPoint(r.near === 1 ? [columns.lat2.at(r.row), columns.lon2.at(r.row)] : [columns.lat1.at(r.row), columns.lon1.at(r.row)]);
    const size = leaflet.getSize();
    return far.x < 0 || far.y < 0 || far.x > size.x || far.y > size.y;
  }).length;
  view.openFan(centre, {row: chosen.row, end: 1});
  await rest("a change");
  const movedTo = leaflet.getCenter();
  // (`also`: the fan's rows that are also the shown line of a spot in view: such a line is stroked twice)
  const inViewShown = new Set(Array.from(view.inView.spots, (s) => view.shownOf(s)));
  out.fan = {drawn: picture(view, map), rows: view.fan!.rows.map((r) => r.label), marks: document.querySelectorAll(".v-anchor-mark").length,
             m: view.inView.m, moved: !movedTo.equals(centre) || leaflet.getZoom() !== zoomBefore, outside: outside(),
             also: view.fan!.rows.filter((r) => inViewShown.has(r.row)).length};
  // opened again with every far end in view: the map stays
  view.closeFan();
  view.openFan(movedTo, {row: chosen.row, end: 1});
  await rest("a change");
  out.fanAgain = {moved: !leaflet.getCenter().equals(movedTo), open: !!view.fan, outside: outside()};
  view.select(null);
  await rest("a change");
  // Esc ends the selection (the frame's key handler; nothing else is open)
  view.select(view.order[0]);
  const selected = view.selected?.spot;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
  out.escape = [selected === view.order[0], view.selected === null];
  // the panels' move through the canvas: a line far from the view is brought in
  const far = view.shownOf(view.order[view.order.length - 1]);
  map.zoomTo(far, {top: 0, right: 0, bottom: 0, left: 0});
  await rest("a change");
  out.zoomTo = view.inView.spots.includes(view.spotOf(far));
  // the map moved off the run, beyond its north-east corner (every corner of the view is then the same place of
  // the run's grid): no spot is in view, the status line says so, nothing is drawn
  const runBox = data.box!, corner = leaflet.latLngToContainerPoint(view.fit.toLatLng(runBox[2], runBox[3]));
  const away = Math.ceil(700 / view.mpp), mapBox = leaflet.getSize();
  leaflet.panBy([corner.x + away, corner.y - mapBox.y - away], {animate: false});
  await rest("a change");
  const cornerNow = leaflet.latLngToContainerPoint(view.fit.toLatLng(runBox[2], runBox[3]));
  out.off = {m: view.inView.m, status: status(), level: view.level, drawn: picture(view, map), corner: [cornerNow.x < 0, cornerNow.y > mapBox.y]};
  // the bar's row beside the status line is no box: with a hint that leaves the row wider than its boxes, a press
  // there goes to the map (here, with no line near: it ends the selection)
  const wideHint: SpotPanels = {...panels, hint: (p) => h("button", {type: "button", "data-slot": "hint-" + p.place},
    "A hint so long that it stands in a line of its own under the status line. ".repeat(4))};
  render(h(SpotColumns, {...props, panels: wideHint, wide: true}), root);
  view.select(view.order[0]);
  await rest("a change");
  const rowBox = document.querySelector(".v-row")!.getBoundingClientRect(), statusBox = document.querySelector(".v-status")!.getBoundingClientRect();
  const hintBox = document.querySelector("[data-slot=hint-map]")!.getBoundingClientRect();
  const beside = [Math.round(rowBox.right - 24), Math.round(statusBox.top + statusBox.height / 2)];
  const under = document.elementFromPoint(beside[0], beside[1]);
  const press = (type: string) => under?.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, clientX: beside[0], clientY: beside[1], button: 0}));
  const wasSelected = view.selected !== null;
  press("click");
  out.row = {wider: rowBox.right - statusBox.right > 100, wrapped: hintBox.top >= statusBox.bottom - 1, under: !!under, inFoot: !!under?.closest(".v-foot"),
             inMap: !!under?.closest(".c-leaflet"), wasSelected, selected: view.selected !== null,
             status: !!document.elementFromPoint(Math.round(statusBox.left + 6), beside[1])?.closest(".v-status"),
             hint: !!document.elementFromPoint(Math.round(hintBox.left + hintBox.width / 2), Math.round(hintBox.top + hintBox.height / 2))?.closest("[data-slot=hint-map]")};
  render(h(SpotColumns, {...props, wide: true}), root);

  // the window crossed the phone's width: the map with the sheet, the same model of spots (its Best stays); in
  // view is the part of the map above the sheet
  root.style.cssText = "width:600px;height:900px;display:flex;position:relative";
  render(h(SpotColumns, {...props, wide: false}), root);
  // the columns' canvas is taken away before the phone's is drawn (window.FINDALINE_VIEW names the new one)
  out.phoneDrawn = await until(() => !!shown() && shown()!.map !== map);
  out.gone = (window as any).FINDALINE_MAP !== leaflet && !document.querySelector(".c-cols");
  // the sheet took its height (the view opens with it low), and the bar's foot stands above it
  const sheetHeight = () => Math.round(document.querySelector(".c-leaflet")!.getBoundingClientRect().bottom - document.querySelector(".u-sheet")!.getBoundingClientRect().top);
  out.sheetDrawn = await until(() => sheetHeight() > 100 &&
    (document.querySelector(".v-map") as HTMLElement).style.getPropertyValue("--v-covered") === `${sheetHeight()}px`);
  await rest("a change");
  const phone = shown()!;
  const sheet = document.querySelector(".u-sheet")!.getBoundingClientRect(), box = document.querySelector(".c-leaflet")!.getBoundingClientRect();
  const foot = document.querySelector(".v-foot")!.getBoundingClientRect();
  out.phone = {same: phone.view === view, best: phone.view.best, sheet: Math.round(box.bottom - sheet.top), height: Math.round(box.height),
               footAbove: foot.bottom <= sheet.top + 1, slots: [text("[data-slot=list]"), text("[data-slot=details]")], places: places(),
               covered: (document.querySelector(".v-map") as HTMLElement).style.getPropertyValue("--v-covered"),
               sheetOrder: Array.from(document.querySelectorAll<HTMLElement>(".u-sheet .u-sheet-handle, .u-sheet [data-slot]"), (e) => e.dataset.slot ?? "handle"),
               pill: text(".c-pill-name"), level: phone.view.level};
  // the first view fits the run above the sheet; moved down by 150 px, a part of it lies under the sheet
  const fitted = {above: phone.view.inView.m, spots: phone.view.counts.spots};
  (window as any).FINDALINE_MAP.panBy([0, -150], {animate: false});
  await rest("a change");
  // the spots in view against a count in the map's own pixels: above the sheet, and with the sheet's part too
  const size = (window as any).FINDALINE_MAP.getSize();
  out.phoneView = {above: phone.view.inView.m, pixels: inPixels(phone.view, [0, 0, size.x, size.y - (box.bottom - sheet.top)]),
                   whole: inPixels(phone.view, [0, 0, size.x, size.y]), fitted};
  // a fan opened through the model on the phone, its far ends outside the part above the sheet: the map moves
  // until every far end is there, clear of the sheet
  const phoneMap = (window as any).FINDALINE_MAP, star = phone.view.spotOf(0), starRow = phone.view.shownOf(star), cols = phone.view.model.data.columns;
  phoneMap.setView([cols.lat1.at(starRow), cols.lon1.at(starRow)], phone.map.zoomOf(0.7), {animate: false});
  await rest("a change");
  const farOutside = () => { const s = phoneMap.getSize(), floor = s.y - Math.round(document.querySelector(".c-leaflet")!.getBoundingClientRect().bottom - document.querySelector(".u-sheet")!.getBoundingClientRect().top);
    return phone.view.fan!.rows.filter((r) => { const q = phoneMap.latLngToContainerPoint(r.near === 1 ? [cols.lat2.at(r.row), cols.lon2.at(r.row)] : [cols.lat1.at(r.row), cols.lon1.at(r.row)]);
      return q.x < 0 || q.y < 0 || q.x > s.x || q.y > floor; }).length; };
  const centreBefore = phoneMap.getCenter();
  phone.view.select(star);
  phone.view.openFan(centreBefore, {row: starRow, end: 1});
  await rest("a change");
  out.phoneFan = {moved: !phoneMap.getCenter().equals(centreBefore), outside: farOutside(), rows: phone.view.fan!.rows.length};
  phone.view.select(null);
  // what covers the map may exceed its height (the sheet at full: the bar's foot stands above the map's top; this
  // page draws no frames, so the sheet's own move cannot be waited for): a move asked by a panel with such a
  // padding still gives the map a finite, sensible view
  const panel = (window as any).PANEL;
  const sane = () => { const z = phoneMap.getZoom(), c = phoneMap.getCenter(); return Number.isFinite(z) && z >= 0 && z <= phoneMap.getMaxZoom() && Number.isFinite(c.lat) && Number.isFinite(c.lng) && Math.abs(c.lat - cols.lat1.at(starRow)!) < 0.5; };
  const pad = {...panel.padding(), top: 500, bottom: 700}, size2 = phoneMap.getSize(), full: boolean[] = [];
  phone.map.reveal(starRow, pad); full.push(sane());
  phone.map.zoomTo(starRow, pad); full.push(sane());
  phone.map.fitArea(pad); full.push(sane());
  out.full = {sane: full, padding: [pad.top, pad.bottom], height: size2.y, zoom: phoneMap.getZoom(), sheet: typeof panel.sheet.setSnap};
  // the legend's fold by the sheet's stop: unfolded by itself while the sheet is low, folded at half or higher; a
  // person's fold or unfold holds until the sheet next changes its stop; at full the bar's foot is not shown
  const folds: unknown[] = [];
  const stop = () => (window as any).PANEL.sheet.snap as string, unfolded = () => document.querySelector(".v-fold")?.getAttribute("aria-expanded");
  const note = () => folds.push([stop(), unfolded(), !!document.querySelector(".v-legend")]);
  const to = async (snap: string, want: string) => { (window as any).PANEL.sheet.setSnap(snap); await until(() => stop() === snap && unfolded() === want); note(); };
  const fold = async (want: string) => { document.querySelector<HTMLElement>(".v-fold")!.click(); await until(() => unfolded() === want); note(); };
  note();
  await to("half", "false");
  await fold("true");
  await to("peek", "true");
  await fold("false");
  await to("half", "false");
  await to("peek", "true");
  (window as any).PANEL.sheet.setSnap("full");
  out.footOff = await until(() => !!document.querySelector(".v-foot.v-foot-off"));
  out.folds = folds;
  render(null, root);
  localStorage.removeItem("findaline.view");
  out.after = viewWanted();
} catch (e) {
  out.error = String((e as Error)?.stack || e);
}
finish(); })();
