// Draws a ResultModel on a Leaflet map that the caller (a shell of the app) owns: the run's area,
// its lines (pink clear, orange over trees/buildings), gold halos of favourites, other runs in their
// colours, the selected line emphasised (halo, anchors) with the others dimmed and its group's
// variants thin, a hover highlight, the profile's hover marker and a measure mode. Everything is drawn
// on one canvas, none of it interactive: a click takes the nearest line within a few pixels (more for a
// finger), the mouse shows it before, and when several spots lie about as near the caller may let the
// user choose (onChoose). No popups, no controls, no DOM outside the map: the shell's panels show the rest.

import L from "leaflet";
import type { Group } from "../grouping";
import { COLORS } from "../style";
import type { Line } from "../types";
import type { ResultModel } from "./model";

export interface Padding { top: number; right: number; bottom: number; left: number }

/** A line a click reached: `px` its distance from the click on the screen. */
export interface Choice { line: Line; group: Group<Line>; variant: boolean; px: number }

export interface ResultMapOptions {
  /** A line (`variant`: a thin line of the selected group) was clicked; default: model.select(line). */
  onLine?(line: Line, group: Group<Line>, variant: boolean): void;
  /** The mouse came to (a line) or left (null) the line a click would take. */
  onHover?(line: Line | null): void;
  /** Several spots lie about as near a click (`choices`: one line each, the nearest first; `at`: the click's
   *  point in the map's container): let the user choose. Without it the nearest line is taken. */
  onChoose?(choices: Choice[], at: L.Point): void;
}

const DIM = 0.25;  // opacity of the lines not selected while one is
const REACH_MOUSE = 8;   // px from a line's axis a click of the mouse still takes it
const REACH_TOUCH = 20;  // the same for a finger (a 40 px wide band)
const TIE_MOUSE = 3;     // another spot within this many px more than the nearest one: the click is ambiguous
const TIE_TOUCH = 8;
const CHOICES_MAX = 6;

/** The distance of (px, py) from the segment a–b. */
function segmentDistance(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const t = len2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

/** A canvas renderer whose redraw does nothing once its canvas is gone: Leaflet binds the redraw when it
 *  asks for the frame, so a frame asked for before the map or the renderer was removed may still run
 *  (headless Edge: "clearRect of undefined" after leaving a result). */
const SafeCanvas = (L.Canvas as any).extend({
  _redraw(this: any) {
    if (this._ctx) return (L.Canvas.prototype as any)._redraw.call(this);
    this._redrawRequest = null;
    this._redrawBounds = null;
  },
}) as new (options: L.RendererOptions & {tolerance?: number}) => L.Canvas;

export class ResultMap {
  private readonly map: L.Map;
  private readonly model: ResultModel;
  private readonly options: ResultMapOptions;
  // One canvas for everything: Leaflet's canvas takes the mouse events of its whole box, so a second one
  // (once that of the variants) would take every click and hover from the first
  private readonly renderer = new SafeCanvas({padding: 0.5});
  private readonly area: L.GeoJSON;
  private readonly otherAreas = L.layerGroup();
  private readonly linesLayer = L.layerGroup();
  private readonly topLayer = L.layerGroup();      // the selection and its variants
  private readonly hoverLayer = L.layerGroup();
  private readonly measureLayer = L.layerGroup();
  private readonly layers: L.Layer[];
  private marker: L.CircleMarker | null = null;
  private hovered: Line | null = null;     // a row of the list under the mouse
  private mapHovered: Line | null = null;  // the line a click on the map would take
  // The lines a click can reach in the order they are drawn (the last one on top), and their ends in the
  // map's pixels at `projectedZoom` (x1, y1, x2, y2 each; panning keeps them)
  private targets: {line: Line; group: Group<Line>; variant: boolean}[] = [];
  private projected: Float64Array | null = null;
  private projectedZoom = NaN;
  private pressedBy = "";  // the pointer type of the last press on the map
  private measuring: ((a: L.LatLng, b: L.LatLng) => void) | null = null;
  private points: L.LatLng[] = [];
  private readonly measureListeners = new Set<(measuring: boolean) => void>();
  private lastSelected: Line | null = null;  // a new selection ends measuring
  private readonly unsubscribe: () => void;

  constructor(map: L.Map, model: ResultModel, options: ResultMapOptions = {}) {
    this.map = map;
    this.model = model;
    this.options = options;
    this.area = L.geoJSON(model.data.area as any, {interactive: false,
                                                   style: {renderer: this.renderer, color: "black", weight: 1,
                                                           dashArray: "6", fill: false}});
    this.layers = [this.area, this.otherAreas, this.linesLayer, this.topLayer, this.hoverLayer, this.measureLayer];
    this.layers.forEach((layer) => layer.addTo(map));
    map.on("click", this.onMapClick);
    map.on("mousemove", this.onMouseMove).on("mouseout", this.onMouseOut);
    map.getContainer().addEventListener("pointerdown", this.onPress, true);
    document.addEventListener("keydown", this.onKey);
    this.unsubscribe = model.subscribe(() => this.render());
    this.render();
  }

  /** Remove every layer and handler of this map. */
  destroy() {
    this.unsubscribe();
    this.cancelMeasure();
    this.measureLayer.clearLayers();
    this.hoverAt(null);
    this.layers.forEach((layer) => this.map.removeLayer(layer));
    if (this.map.hasLayer(this.renderer)) this.map.removeLayer(this.renderer);
    this.map.off("click", this.onMapClick);
    this.map.off("mousemove", this.onMouseMove).off("mouseout", this.onMouseOut);
    this.map.getContainer().removeEventListener("pointerdown", this.onPress, true);
    document.removeEventListener("keydown", this.onKey);
  }

  private color(l: Line): string {
    return l.run ? l.run.color : l.over ? COLORS.over : COLORS.clean;
  }

  private weight(l: Line): number {
    return l.run ? 2.5 : 3;
  }

  /** A line of the map; lines of other runs are dashed over trees/buildings. */
  private polyline(l: Line, options: L.PolylineOptions): L.Polyline {
    return L.polyline([[l.lat1, l.lon1], [l.lat2, l.lon2]],
                      {color: this.color(l), renderer: this.renderer, interactive: false,
                       dashArray: l.run && l.over ? "6 4" : undefined, ...options});
  }

  /** A line a click can take; drawn later, it is on top. */
  private target(l: Line, g: Group<Line>, variant: boolean) {
    this.targets.push({line: l, group: g, variant});
  }

  /** Draw the model again (called on every change of it). */
  render() {
    const model = this.model, selected = model.selected;
    if ((selected?.line || null) !== this.lastSelected) {
      this.lastSelected = selected?.line || null;
      if (this.measuring) { this.cancelMeasure(); this.clearMeasure(); }
    }
    this.linesLayer.clearLayers();
    this.topLayer.clearLayers();
    this.otherAreas.clearLayers();
    this.targets = [];
    this.projected = null;
    model.others.forEach((run) => {
      L.geoJSON(run.area as any, {interactive: false,
                                  style: {renderer: this.renderer, color: run.color, weight: 1, dashArray: "6",
                                          fill: false}})
        .addTo(this.otherAreas);
    });
    const opacity = selected ? DIM : 0.9;
    // Lines over trees/buildings first, so clear lines stay on top
    const order = model.groups.filter((g) => g.rep.over).concat(model.groups.filter((g) => !g.rep.over));
    for (const g of order) {
      if (selected && g === selected.group) continue;
      const l = model.shownOf(g);
      if (model.favouritesOn && model.isFavourite(l)) {
        this.polyline(l, {color: COLORS.favourite, weight: this.weight(l) + 7, opacity: 0.6 * (selected ? DIM : 1),
                          dashArray: undefined, interactive: false}).addTo(this.linesLayer);
      }
      this.polyline(l, {weight: this.weight(l), opacity}).addTo(this.linesLayer);
      this.target(l, g, false);
    }
    if (selected) {
      const {group, line} = selected, w = this.weight(line);
      // The variants of its group, thin; then the line over a dark halo (gold for a favourite), its anchors marked
      for (const m of group.members) {
        if (m === line) continue;
        this.polyline(m, {weight: 1, opacity: 0.8}).addTo(this.topLayer);
        this.target(m, group, true);
      }
      const favourite = model.favouritesOn && model.isFavourite(line);
      this.polyline(line, {color: favourite ? COLORS.favourite : "#000", weight: w + 8, opacity: favourite ? 0.8 : 0.45,
                           dashArray: undefined, interactive: false}).addTo(this.topLayer);
      this.polyline(line, {weight: w + 2, opacity: 1}).addTo(this.topLayer);
      this.target(line, group, false);
      for (const at of [[line.lat1, line.lon1], [line.lat2, line.lon2]] as [number, number][]) {
        L.circleMarker(at, {radius: 5, color: "#000", weight: 2, fillColor: "#fff", fillOpacity: 1,
                            interactive: false, renderer: this.renderer}).addTo(this.topLayer);
      }
    }
    // The line under the mouse may be gone (a filter)
    if (this.mapHovered && !this.targets.some((t) => t.line === this.mapHovered)) this.setMapHovered(null);
    this.drawHover();
  }

  /** Draw a line wider (a row of the list under the mouse); null: none. */
  highlight(line: Line | null) {
    this.hovered = line;
    this.drawHover();
  }

  private drawHover() {
    this.hoverLayer.clearLayers();
    const l = this.hovered || this.mapHovered;
    if (l) this.polyline(l, {weight: 7, opacity: 1, interactive: false}).addTo(this.hoverLayer);
  }

  // --- picking a line ---

  /** The ends of the targets in the map's pixels at its zoom (computed again after a zoom or a render). */
  private ends(): Float64Array {
    const zoom = this.map.getZoom();
    if (this.projected && this.projectedZoom === zoom) return this.projected;
    const xy = new Float64Array(this.targets.length * 4);
    this.targets.forEach(({line}, k) => {
      const a = this.map.project([line.lat1, line.lon1], zoom), b = this.map.project([line.lat2, line.lon2], zoom);
      xy[4 * k] = a.x; xy[4 * k + 1] = a.y; xy[4 * k + 2] = b.x; xy[4 * k + 3] = b.y;
    });
    this.projected = xy;
    this.projectedZoom = zoom;
    return xy;
  }

  /** The spots with a line within `reach` px of a point, each by its nearest line, the nearest first (of
   *  two as near, the one drawn later: it is on top). */
  near(at: L.LatLng, reach: number): Choice[] {
    const xy = this.ends(), p = this.map.project(at, this.projectedZoom);
    const best = new Map<Group<Line>, Choice & {k: number}>();
    for (let k = 0; k < this.targets.length; k++) {
      const px = segmentDistance(p.x, p.y, xy[4 * k], xy[4 * k + 1], xy[4 * k + 2], xy[4 * k + 3]);
      if (px > reach) continue;
      const t = this.targets[k], had = best.get(t.group);
      if (!had || px <= had.px) best.set(t.group, {...t, px, k});
    }
    return [...best.values()].sort((a, b) => a.px - b.px || b.k - a.k)
      .map(({line, group, variant, px}) => ({line, group, variant, px}));
  }

  /** What a click at a point takes: the nearest spot's line, or the spots about as near (ambiguous). */
  private pick(at: L.LatLng, finger: boolean): Choice[] {
    const found = this.near(at, finger ? REACH_TOUCH : REACH_MOUSE);
    if (found.length < 2) return found;
    const tie = found[0].px + (finger ? TIE_TOUCH : TIE_MOUSE);
    return found.filter((c) => c.px <= tie).slice(0, CHOICES_MAX);
  }

  /** Take a line as a click on it does (onLine, else model.select). */
  choose(c: Choice) {
    if (this.options.onLine) this.options.onLine(c.line, c.group, c.variant);
    else this.model.select(c.line);
  }

  /** Give the focus back to the map (a choice closed with Esc). */
  focusMap() {
    this.map.getContainer().focus({preventScroll: true});
  }

  private setMapHovered(line: Line | null) {
    if (line === this.mapHovered) return;
    this.mapHovered = line;
    const canvas = (this.renderer as any)._container as HTMLElement | undefined;
    canvas?.classList.toggle("leaflet-interactive", !!line);  // Leaflet's pointer cursor
    this.drawHover();
    this.options.onHover?.(line);
  }

  /** Was the click a finger's: the type of the press before it (WebKit's click after a tap is a "mouse"
   *  PointerEvent), else the click's own, else (no PointerEvent) a coarse pointer. */
  private byFinger(e: L.LeafletMouseEvent): boolean {
    const type = this.pressedBy || (e.originalEvent as PointerEvent).pointerType;
    if (type) return type === "touch";
    return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  }

  private onPress = (e: PointerEvent) => { this.pressedBy = e.pointerType; };

  // The line a click would take, under the mouse (Leaflet's canvas passes its mousemove on about 30 times
  // a second, not while the map is dragged); none while measuring or for the mouse events of a finger
  private onMouseMove = (e: L.LeafletMouseEvent) => {
    if (this.measuring || this.pressedBy === "touch" || (e.originalEvent as any).sourceCapabilities?.firesTouchEvents) {
      this.setMapHovered(null);
      return;
    }
    const found = this.near(e.latlng, REACH_MOUSE);
    this.setMapHovered(found.length ? found[0].line : null);
  };

  private onMouseOut = () => this.setMapHovered(null);

  /** The point of the profile under the mouse; null: none. */
  hoverAt(at: L.LatLngExpression | null) {
    if (!at) {
      if (this.marker) { this.map.removeLayer(this.marker); this.marker = null; }
    } else if (!this.marker) {
      this.marker = L.circleMarker(at, {radius: 6, color: "#000", weight: 2, fillColor: "#fff", fillOpacity: 1,
                                        interactive: false, renderer: this.renderer}).addTo(this.map);
    } else this.marker.setLatLng(at);
  }

  /** The bounds of the run's area. */
  areaBounds(): L.LatLngBounds {
    return this.area.getBounds();
  }

  fitArea(padding: Padding = {top: 0, right: 0, bottom: 0, left: 0}, animate = true) {
    this.map.fitBounds(this.area.getBounds(), {paddingTopLeft: [padding.left, padding.top],
                                               paddingBottomRight: [padding.right, padding.bottom], animate});
  }

  /** Fit the map to a line, `padding` px kept free on each side (panels over the map) plus a margin. */
  zoomTo(line: Line, padding: Padding = {top: 0, right: 0, bottom: 0, left: 0}, animate = true) {
    const m = 60;
    this.map.fitBounds(L.latLngBounds([line.lat1, line.lon1], [line.lat2, line.lon2]),
                       {paddingTopLeft: [padding.left + m, padding.top + m],
                        paddingBottomRight: [padding.right + m, padding.bottom + m],
                        maxZoom: this.model.data.max_zoom, animate});
  }

  /** Is a line within the map's view (the list's "only in the map's view"). */
  inView(line: Line): boolean {
    return this.map.getBounds().intersects(L.latLngBounds([line.lat1, line.lon1], [line.lat2, line.lon2]));
  }

  /** Call `listener` after every move or zoom of the map (moveend); returns the function that stops it. */
  onMove(listener: () => void): () => void {
    this.map.on("moveend", listener);
    return () => { this.map.off("moveend", listener); };
  }

  // --- measuring ---

  get isMeasuring(): boolean {
    return this.measuring !== null;
  }

  /** Call `listener` when measure mode starts or ends; returns the function that stops it. */
  onMeasuring(listener: (measuring: boolean) => void): () => void {
    this.measureListeners.add(listener);
    return () => { this.measureListeners.delete(listener); };
  }

  /** Measure mode: the next two clicks on the map are the points, given to `done`; Esc cancels. */
  startMeasure(done: (a: L.LatLng, b: L.LatLng) => void) {
    this.measureLayer.clearLayers();
    this.points = [];
    this.measuring = done;
    this.map.getContainer().style.cursor = "crosshair";
    this.measureListeners.forEach((f) => f(true));
  }

  /** Leave measure mode (the points drawn stay until clearMeasure). */
  cancelMeasure() {
    if (!this.measuring) return;
    this.measuring = null;
    this.points = [];
    this.map.getContainer().style.cursor = "";
    this.measureListeners.forEach((f) => f(false));
  }

  /** Remove the points and line of a measurement (while measuring, the points taken so far too). */
  clearMeasure() {
    this.measureLayer.clearLayers();
    this.points = [];
  }

  private addPoint(at: L.LatLng) {
    const done = this.measuring;
    if (!done) return;
    this.points.push(at);
    L.circleMarker(at, {radius: 5, color: "#000", weight: 2, fillColor: "#fff", fillOpacity: 1,
                        interactive: false, renderer: this.renderer}).addTo(this.measureLayer);
    if (this.points.length < 2) return;
    const [a, b] = this.points;
    L.polyline([a, b], {color: "#000", weight: 2, dashArray: "6 4", interactive: false, renderer: this.renderer})
      .addTo(this.measureLayer);
    this.cancelMeasure();
    done(a, b);
  }

  // A click takes the nearest line, lets the user choose between spots about as near or, beside the lines,
  // ends the selection; while measuring it is a point
  private onMapClick = (e: L.LeafletMouseEvent) => {
    if (this.measuring) { this.addPoint(e.latlng); return; }
    const found = this.pick(e.latlng, this.byFinger(e));
    if (found.length > 1 && this.options.onChoose) this.options.onChoose(found, e.containerPoint);
    else if (found.length) this.choose(found[0]);
    else if (this.model.selected) this.model.select(null);
  };

  // Escape ends measuring, else the selection; not while typing or in a dialog (a Popover closes itself)
  private onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    if (this.measuring) { this.cancelMeasure(); this.clearMeasure(); return; }
    const at = document.activeElement;
    if (at && at.closest("input, select, textarea, [role=dialog], [role=alertdialog]")) return;
    if (this.model.selected) this.model.select(null);
  };
}
