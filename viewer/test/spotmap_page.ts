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
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const shown = (): {view: SpotView; map: SpotMap} | undefined => (window as any).FINDALINE_VIEW;
/** Wait until `test` holds (the page draws after its effects), 5 s at most. */
async function until(test: () => boolean): Promise<boolean> {
  for (let k = 0; k < 100 && !test(); k++) await sleep(50);
  return test();
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
    sheetHead: () => h("b", {"data-slot": "head"}, "the sheet's head"),
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
  await sleep(50);  // the legend follows the picture
  out.held = {level: view.level, auto: view.auto, status: text(".v-status"), pressed: pressed(), refused: !!document.querySelector(".v-refused"),
              drawn: picture(view, map), m: view.inView.m};
  document.querySelector<HTMLElement>(".v-back-auto")!.click();
  await until(() => !document.querySelector(".v-back-auto"));
  out.back = {level: view.level, auto: view.auto, status: status()};
  // zoomed in: Auto follows the zoom, the spots in view and the status follow the map
  const leaflet = (window as any).FINDALINE_MAP;
  leaflet.setZoom(leaflet.getZoom() + 2.5, {animate: false});
  await until(() => view.level !== "area");
  await sleep(50);
  const zoomedPicture = picture(view, map);
  const mapSize = leaflet.getSize();
  const spots = {level: view.level, m: view.inView.m, best: view.inView.best.length, numbered: view.inView.numbered, status: status(),
                 zoom: leaflet.getZoom(), mpp: view.mpp, pixels: inPixels(view, [0, 0, mapSize.x, mapSize.y])};
  const select = document.querySelector<HTMLSelectElement>(".v-best select")!;
  select.value = "all";
  select.dispatchEvent(new Event("change", {bubbles: true}));
  await until(() => view.best === "all" && (status() || "").includes("all"));
  await sleep(50);
  out.spots = {...spots, drawn: zoomedPicture, all: {best: view.best, status: status(), disabled: select.disabled, drawn: picture(view, map)}};
  // a spot selected: its lines, A1 and A2 (the access mark on their corners), the rest dimmed; then "Lines from here"
  view.select(view.spotOf(0));  // the made-up run's star: its lines leave the map's middle
  await sleep(50);
  const chosen = view.selected!;
  out.selected = {drawn: picture(view, map), passing: view.passingOf(chosen.spot).length, marks: document.querySelectorAll(".v-anchor-mark").length};
  // opened through the model (as the details' buttons do): the canvas moves the map, because far ends lie outside
  const centre = leaflet.getCenter(), zoomBefore = leaflet.getZoom(), columns = view.model.data.columns;
  const outside = () => view.fan!.rows.filter((r) => {
    const far = leaflet.latLngToContainerPoint(r.near === 1 ? [columns.lat2.at(r.row), columns.lon2.at(r.row)] : [columns.lat1.at(r.row), columns.lon1.at(r.row)]);
    const size = leaflet.getSize();
    return far.x < 0 || far.y < 0 || far.x > size.x || far.y > size.y;
  }).length;
  view.openFan(centre, {row: chosen.row, end: 1});
  await sleep(50);
  const movedTo = leaflet.getCenter();
  out.fan = {drawn: picture(view, map), rows: view.fan!.rows.map((r) => r.label), marks: document.querySelectorAll(".v-anchor-mark").length,
             m: view.inView.m, moved: !movedTo.equals(centre) || leaflet.getZoom() !== zoomBefore, outside: outside()};
  // opened again with every far end in view: the map stays
  view.closeFan();
  view.openFan(movedTo, {row: chosen.row, end: 1});
  await sleep(50);
  out.fanAgain = {moved: !leaflet.getCenter().equals(movedTo), open: !!view.fan, outside: outside()};
  view.select(null);
  await sleep(50);
  // Esc ends the selection (the frame's key handler; nothing else is open)
  view.select(view.order[0]);
  const selected = view.selected?.spot;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
  out.escape = [selected === view.order[0], view.selected === null];
  // the panels' move through the canvas: a line far from the view is brought in
  const far = view.shownOf(view.order[view.order.length - 1]);
  map.zoomTo(far, {top: 0, right: 0, bottom: 0, left: 0});
  await sleep(50);
  out.zoomTo = view.inView.spots.includes(view.spotOf(far));

  // the window crossed the phone's width: the map with the sheet, the same model of spots (its Best stays); in
  // view is the part of the map above the sheet
  root.style.cssText = "width:600px;height:900px;display:flex;position:relative";
  render(h(SpotColumns, {...props, wide: false}), root);
  // the columns' canvas is taken away before the phone's is drawn (window.FINDALINE_VIEW names the new one)
  out.phoneDrawn = await until(() => !!shown() && shown()!.map !== map);
  out.gone = (window as any).FINDALINE_MAP !== leaflet && !document.querySelector(".c-cols");
  await sleep(400);  // the sheet took its height, the view's rectangle was taken again
  const phone = shown()!;
  const sheet = document.querySelector(".u-sheet")!.getBoundingClientRect(), box = document.querySelector(".c-leaflet")!.getBoundingClientRect();
  const foot = document.querySelector(".v-foot")!.getBoundingClientRect();
  out.phone = {same: phone.view === view, best: phone.view.best, sheet: Math.round(box.bottom - sheet.top), height: Math.round(box.height),
               footAbove: foot.bottom <= sheet.top + 1, slots: [text("[data-slot=list]"), text("[data-slot=details]")], places: places(),
               covered: (document.querySelector(".v-map") as HTMLElement).style.getPropertyValue("--v-covered"),
               pill: text(".c-pill-name"), level: phone.view.level};
  // the first view fits the run above the sheet; moved down by 150 px, a part of it lies under the sheet
  const fitted = {above: phone.view.inView.m, spots: phone.view.counts.spots};
  (window as any).FINDALINE_MAP.panBy([0, -150], {animate: false});
  await sleep(50);
  // the spots in view against a count in the map's own pixels: above the sheet, and with the sheet's part too
  const size = (window as any).FINDALINE_MAP.getSize();
  out.phoneView = {above: phone.view.inView.m, pixels: inPixels(phone.view, [0, 0, size.x, size.y - (box.bottom - sheet.top)]),
                   whole: inPixels(phone.view, [0, 0, size.x, size.y]), fitted};
  render(null, root);
  localStorage.removeItem("findaline.view");
  out.after = viewWanted();
} catch (e) {
  out.error = String((e as Error)?.stack || e);
}
finish(); })();
