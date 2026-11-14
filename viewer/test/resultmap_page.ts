// A test page of result/ResultMap (tests/test_viewer.py builds it into a run's folder and opens it
// in headless Edge from the app's server): loadRun, a model, its map, a selection, measuring and
// destroy; the findings go into <pre id="result"> as JSON.

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { loadRun } from "../src/result/load";
import { ResultModel } from "../src/result/model";
import { ResultMap } from "../src/result/ResultMap";
import { addShore } from "../src/shoreLayer";
import { addCoarser } from "../src/coarserLayer";
import type { Line, Shore, TerrainSources } from "../src/types";

const out: Record<string, unknown> = {};
const finish = () => {
  const pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
};
const runId = decodeURIComponent(location.pathname.split("/")[2]);

(async () => {
  try {
    const failed = await loadRun("no such run").then(() => false, () => true);
    const data = await loadRun(runId);
    out.load = {failed, lines: data.lines.length, cleared: window.FINDALINE_RUN === undefined,
                cached: (await loadRun(runId)) === data};
    const div = document.createElement("div");
    div.id = "map";
    div.style.width = "800px";
    div.style.height = "600px";
    document.body.appendChild(div);
    const map = L.map(div, {center: data.center, zoom: 16});
    const before = Object.keys((map as any)._layers).length;
    const model = new ResultModel(data, {favourites: false, profiles: false});
    const clicked: string[] = [];
    let last: Line | null = null;
    const view = new ResultMap(map, model, {onLine: (l, g, variant) => {
      clicked.push(variant ? "variant" : "line");
      last = l;
      if (variant) model.choose(g, l); else model.select(l);
    }});
    view.fitArea();
    const count = () => Object.keys((map as any)._layers).length;
    out.drawn = count() - before;
    // The uncertain shore (shoreLayer.ts): its overlay for the layer control, its control shown with the metres
    // while the view holds a segment and hidden away from it
    const [lat, lon] = data.center;
    const ring: [number, number][] = [[lon - 0.0004, lat - 0.0002], [lon + 0.0004, lat - 0.0002], [lon + 0.0004, lat + 0.0002],
                                      [lon - 0.0004, lat + 0.0002], [lon - 0.0004, lat - 0.0002]];
    const shore: Shore = {rim_min: 5, segments: [{kind: "sea", px: 40, m: 90, ring}],
                          totals: {surface_m: 0, sea_m: 90, surface_px: 0, sea_px: 40}};
    const overlays: Record<string, L.Layer> = {};
    const shoreBox = addShore(map, shore, overlays);
    map.setView([lat, lon], 17, {animate: false});
    const shoreEl = div.querySelector<HTMLElement>(".u-shore");
    const more = shoreEl?.querySelector<HTMLElement>(".u-shore-more"), helpButton = shoreEl?.querySelector<HTMLButtonElement>(".u-shore-help");
    const closed = !!more?.hidden;
    helpButton?.click();
    out.shore = {overlays: Object.keys(overlays).length, shown: !!shoreEl && !shoreEl.hidden, text: shoreEl?.textContent ?? "",
                 help: [closed, !!more && !more.hidden, helpButton?.getAttribute("aria-expanded")]};
    map.setView([lat + 0.05, lon], 17, {animate: false});
    out.shoreAway = !!shoreEl && shoreEl.hidden;
    shoreBox?.remove();
    Object.values(overlays).forEach((layer) => map.removeLayer(layer));
    // The coarser terrain (coarserLayer.ts): its overlay hatched by a pattern of its SVG, the control with the km²
    // while the view holds a region, hidden away from it and while the overlay is off; fit shows every region
    const sources: TerrainSources = {land_km2: 1, fallback_share: 0.4, totals: {fallback_km2: 0.4, listed_km2: 0.4},
      layers: [{role: "source", name: "Own", resolution: 1, share: 0.6}, {role: "fallback", name: "Coarse", resolution: 10, share: 0.4}],
      regions: [{layer: 1, km2: 0.4, rings: [ring]}]};
    const coarseOverlays: Record<string, L.Layer> = {};
    map.setView([lat, lon], 17, {animate: false});
    const coarse = addCoarser(map, sources, coarseOverlays)!;
    const coarseEl = div.querySelector<HTMLElement>(".u-coarse");
    const fill = div.querySelector<SVGPathElement>("path.u-coarse-area")?.getAttribute("fill") ?? "";
    const patternId = fill.match(/^url\(#(.+)\)$/)?.[1] ?? "";
    out.coarse = {overlays: Object.keys(coarseOverlays), shown: !!coarseEl && !coarseEl.hidden, text: coarseEl?.textContent ?? "",
                  pattern: !!patternId && !!div.querySelector(`pattern[id="${patternId}"] line.u-coarse-hatch`),
                  none: addCoarser(map, {...sources, regions: []}, {}) === null};
    map.removeLayer(Object.values(coarseOverlays)[0]);
    out.coarseOff = !!coarseEl && coarseEl.hidden;
    map.setView([lat + 0.05, lon], 17, {animate: false});
    await new Promise((done) => { map.once("moveend", done); coarse.fit(); });
    const b = map.getBounds();
    out.coarseFit = {back: map.hasLayer(Object.values(coarseOverlays)[0]), holds: b.contains([lat, lon]), shown: !!coarseEl && !coarseEl.hidden};
    map.setView([lat + 0.05, lon], 17, {animate: false});
    out.coarseAway = !!coarseEl && coarseEl.hidden;
    coarse.control.remove();
    Object.values(coarseOverlays).forEach((layer) => map.removeLayer(layer));
    view.fitArea();
    // Selecting a group: its line, halo, anchors and variants drawn on top
    const group = model.groups.find((g) => g.members.length > 2)!;
    model.select(group);
    view.zoomTo(model.selected!.line, {top: 0, right: 300, bottom: 200, left: 0}, false);
    out.selectedLayers = count() - before;
    view.highlight(group.members[1]);
    view.hoverAt([group.rep.lat1, group.rep.lon1]);
    // A click on a variant (the middle of one where it is the nearest line, in screen pixels) through the canvas
    const shown = model.selected!.line;
    const middle = (m: Line) => map.latLngToContainerPoint([(m.lat1 + m.lat2) / 2, (m.lon1 + m.lon2) / 2]);
    const variant = group.members.find((m) => m !== shown &&
      view.near(map.containerPointToLatLng(middle(m)), 8)[0]?.line === m)!;
    const p = middle(variant);
    const canvas: HTMLCanvasElement = (view as any).renderer._container;  // the map's one canvas of the run
    const fire = (type: string, x: number, y: number) => {
      const r = div.getBoundingClientRect();
      canvas.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, clientX: r.left + x,
                                                 clientY: r.top + y}));
    };
    fire("mousemove", p.x, p.y);
    fire("click", p.x, p.y);
    out.clicked = clicked;
    // Overlapping variants: the one hit is shown (the group's other line than before)
    out.variantShown = last !== null && last !== shown && model.selected?.line === last &&
      model.selected?.group === group;
    // Measuring: two clicks on the map
    let measured: number[] | null = null;
    view.startMeasure((a, b) => { measured = [a.lat, b.lat]; });
    map.fire("click", {latlng: L.latLng(data.center), containerPoint: L.point(0, 0)} as any);
    map.fire("click", {latlng: L.latLng(data.center[0] + 0.001, data.center[1]), containerPoint: L.point(0, 0)} as any);
    out.measured = measured !== null && !view.isMeasuring;
    view.startMeasure(() => {});
    // onMove: called after a move, not after it is stopped
    let moves = 0;
    const stop = view.onMove(() => { moves++; });
    map.panBy([10, 0], {animate: false});
    stop();
    map.panBy([-10, 0], {animate: false});
    out.moves = moves;
    document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
    out.escaped = !view.isMeasuring;
    view.destroy();
    out.after = count() - before;
    model.select(null);  // no map to draw on any more: nothing happens
  } catch (e) {
    out.error = String(e && (e as Error).stack || e);
  }
  finish();
})();
