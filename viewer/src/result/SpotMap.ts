// The result view's canvas (docs/line-volume/spec-view.md B.2): draws a SpotView (spots.ts) on a Leaflet map the
// frame (view/SpotColumns.tsx) owns, takes the presses, and tells the view what the map shows. One canvas of its
// own (a Leaflet renderer without paths: the lines are drawn from the run's columns, never as one layer each),
// drawn again in full after every move, zoom or resize of the map and every change of the view:
// - the part of the map a person sees goes to the view as a Quad in the run's grid metres with its metres per
//   pixel (SpotView.setView: the level under Auto, the spots in view, their numbers);
// - Area: the squares (viewgeom.ts squareValues) in five classes with their values, the picks of "Start here"
//   bold with P1 …; Spots: the best spots' shown lines bold with B1 …, the other spots in view pale; Lines: the
//   best spots' lines not beaten thin, their shown line bold with a halo (with All every passing line in view,
//   thin); above 5 000 thin lines none, only the pale lines (the view counts and refuses);
// - a selected spot: its other passing lines thin, its line over a dark halo, A1 and A2 on its anchors (in a run
//   with the access mark the circle's ring in the state's colour and the mark on its corner), the rest dimmed;
//   "Lines from here": its lines with halos and their numbers, a dashed ring at the point;
// - a number (B, P, L) sits on the longest piece of its line that is on the map and clear of every control
//   (the bar's boxes `[data-map-control]`, Leaflet's controls, the frame's own obstacles), away from the numbers
//   placed before it; placed again when a control changed its size after the draw (at most twice);
// - presses: a number's shape first, then lines by rank (bold, thin, pale) within the reach of a mouse or a
//   finger; several spots about as near: the table of spots (onChoose), with a finger a zoom in around the point
//   until the map shows CLOSE_MPP; a square zooms to itself; a right click or a press held 600 ms opens "Lines
//   from here"; a mouse's hover thickens the line a press would take.
// The lines are drawn from their own latitudes and longitudes (Web Mercator by hand: two logarithms a line, no
// object per point); the squares' corners and the pressed point go through the view's fit.

import L from "leaflet";
import { accessMarkSvg, accessState, accessWord } from "../access";
import { t } from "../i18n";
import { timed } from "../perf";
import { COLORS } from "../style";
import type { Padding } from "./ResultMap";
import type { SpotChoice, SpotView } from "./spots";
import { breaks, classOf, FAN_HERE, reader, squareAt, squareSide, squareValues, SQUARE_PX, type Level, type Quad,
         type SquareBy, type SquareGrid } from "./viewgeom";

export type { Padding };

export interface SpotMapOptions {
  /** Several spots lie about as near a press (`at`: its point in the map's container): let the user choose. */
  onChoose(c: SpotChoice[], at: L.Point): void;
  /** A short message of the map ("Several spots here. Zoomed in. Tap again."). */
  onToast(text: string): void;
  /** The frame's own boxes over the map (the hint, its "?"): no number is placed under them. */
  obstacles(): DOMRect[];
  // --- added to the plan's interface (section 1) ---
  /** The pixels of the map's box, from each side, that a person does not see (a phone's sheet): the view's
   *  rectangle is the rest. None: the whole box. */
  free?(): Padding;
  /** After every full redraw (the first one: the view is drawn). */
  onDrawn?(): void;
  /** The phone layout: every press counts as a finger's. */
  phone?: boolean;
  /** The pixels of the map's box the frame's bars cover on each side (with what a person does not see): a move
   *  of the map by the canvas itself keeps them free (a fan shown, a sector, a square). None: `free`. */
  padding?(): Padding;
}

/** What the map shows now, for its legend: the shapes and colours drawn, and at Area the squares' value and breaks. */
export interface Legend { level: Level; shapes: {[K in ShapeKind]?: true}; by: SquareBy; breaks: number[] }
export type ShapeKind = "sq" | "P" | "B" | "L" | "A" | "pale" | "here" | "clear" | "over";
/** A number's shape on the map: B a box with round corners, P a diamond, L a six-sided tag, A a circle. */
export type MarkKind = "B" | "P" | "L" | "A";

const NONE: Padding = {top: 0, right: 0, bottom: 0, left: 0};
/** The closest a move of the map by the page zooms in, metres per pixel (the mock-up's last zoom): a row revealed,
 *  a sector shown; from here on a crowded tap opens the table of spots (B.2 item 9). */
export const CLOSE_MPP = 0.25;
/** A square pressed under Auto zooms to at most this many metres per pixel, so that Auto lands on Spots. */
export const SQUARE_MPP = 0.96;
const SNAP = 0.25;
const PANE = "spots";  // the canvas's pane on the map
const FIT_ROOM = 96;  // px a fit of the map keeps for what it fits, whatever covers the map
const REACH_MOUSE = 8, REACH_TOUCH = 20, TIE_MOUSE = 3, TIE_TOUCH = 8, CHOICES_MAX = 6;
/** A press held this long within this many px opens "Lines from here" (Leaflet's own numbers of a tap held); a
 *  browser's own contextmenu within MENU_QUIET ms after it is the same press. */
export const HOLD_MS = 600, HOLD_PX = 15, MENU_QUIET = 1000;
const FLASH_TAP = 1800, FLASH_SECTOR = 2400;
const PAD = 2;  // px a number's shape keeps clear of a control
const INK = "#1b2530", PAPER = "#ffffff";  // the numbers' shapes: the map's tiles stay light in the dark theme
const D = Math.PI / 180;

/** The half width and height of a number's shape. */
export function markSize(kind: MarkKind, text: string): [number, number] {
  return [kind === "P" ? 19 : kind === "L" ? 17.5 : kind === "A" ? 10.5 : text.length > 2 ? 15 : 12.5, kind === "P" ? 13.5 : 10.5];
}

function shapePath(ctx: CanvasRenderingContext2D, kind: MarkKind, x: number, y: number, text: string) {
  const [w, h] = markSize(kind, text);
  ctx.beginPath();
  if (kind === "P") { ctx.moveTo(x, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x, y + h); ctx.lineTo(x - w, y); ctx.closePath(); }
  else if (kind === "L") {
    ctx.moveTo(x - w + 6, y - h); ctx.lineTo(x + w - 6, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x + w - 6, y + h);
    ctx.lineTo(x - w + 6, y + h); ctx.lineTo(x - w, y); ctx.closePath();
  }
  else if (kind === "A") ctx.arc(x, y, 10.5, 0, 2 * Math.PI);
  else if (typeof ctx.roundRect === "function") ctx.roundRect(x - w, y - h, 2 * w, 2 * h, 4);
  else ctx.rect(x - w, y - h, 2 * w, 2 * h);
}

/** The part of the segment a → b inside a box, as two fractions of it, or null (Liang-Barsky). */
function clipT(ax: number, ay: number, bx: number, by: number, x0: number, y0: number, x1: number, y1: number): [number, number] | null {
  let t0 = 0, t1 = 1;
  const dx = bx - ax, dy = by - ay, p = [-dx, dx, -dy, dy], q = [ax - x0, x1 - ax, ay - y0, y1 - ay];
  for (let k = 0; k < 4; k++) {
    if (p[k] === 0) { if (q[k] < 0) return null; continue; }
    const r = q[k] / p[k];
    if (p[k] < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
  }
  return t1 > t0 ? [t0, t1] : null;
}

function segmentDistance(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const f = len2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - ax - f * dx, py - ay - f * dy);
}

interface Placed { kind: MarkKind; text: string; x: number; y: number; w: number; h: number; spot: number; row: number; end?: 1 | 2 }
interface Hit { spot: number; row: number; d: number }

// A Leaflet renderer that draws nothing by itself: its canvas follows the map (placed and sized at every
// moveend, scaled during a zoom's animation) and `onUpdate` paints it
const Draw = (L.Renderer as any).extend({
  _initContainer(this: any) {
    const c = this._container = document.createElement("canvas");
    c.className = "v-canvas";
    this._ctx = c.getContext("2d");
  },
  _destroyContainer(this: any) {
    L.DomUtil.remove(this._container);
    delete this._container;
    delete this._ctx;
  },
  _updatePaths() { /* no paths */ },
  _update(this: any) {
    if (this._map._animatingZoom && this._bounds) return;
    (L.Renderer.prototype as any)._update.call(this);
    const b = this._bounds, c = this._container, size = b.getSize(), m = Math.min(2, window.devicePixelRatio || 1);
    L.DomUtil.setPosition(c, b.min);
    c.width = Math.round(m * size.x);
    c.height = Math.round(m * size.y);
    c.style.width = size.x + "px";
    c.style.height = size.y + "px";
    this._m = m;
    this.options.onUpdate();
  },
}) as new (options: L.RendererOptions & {onUpdate(): void}) => L.Renderer;

export class SpotMap {
  private readonly map: L.Map;
  private readonly view: SpotView;
  private readonly options: SpotMapOptions;
  private readonly renderer: L.Renderer;
  private readonly anchorMarks = L.layerGroup();  // the access mark on A1's and A2's corner (markers' icons)
  private readonly unsubscribe: () => void;
  private readonly listeners = new Set<() => void>();
  private readonly lat: ((i: number) => number)[];
  private readonly lon: ((i: number) => number)[];
  private readonly over: Uint8Array;
  private busy = false;
  private hovered: number | null = null;     // a row of the list under the mouse
  private mapHovered: number | null = null;  // the line a press on the map would take
  private marker: L.LatLng | null = null;
  private flash: number[] | null = null;
  private flashTimer = 0;
  private checkTimer = 0;
  private by: SquareBy = "spots";
  private grid: SquareGrid | null = null;
  private legendNow: Legend = {level: "area", shapes: {}, by: "spots", breaks: []};
  private legendKey = "";
  // what a press can take, in the layer's pixels of the last full paint: the lines (rank 2 bold: numbered, a pick,
  // the selected line; 1 thin; 0 pale), the numbers' shapes, the fan's lines
  private tx: number[] = [];
  private trow: number[] = [];
  private trank: number[] = [];
  private marks: Placed[] = [];
  private fanLines: {x1: number; y1: number; x2: number; y2: number; row: number}[] = [];
  private strokes = 0;
  private free = {x0: 0, y0: 0, x1: 0, y1: 0, rects: [] as number[][], sig: ""};
  private scale = 1;
  private ox = 0;
  private oy = 0;
  private pressedBy = "";
  private hold: {timer: number; x: number; y: number; id: number} | null = null;
  private heldAt = -Infinity;
  private swallowClick = false;
  private fanShown: SpotView["fan"] = null;

  constructor(map: L.Map, view: SpotView, options: SpotMapOptions) {
    this.map = map;
    this.view = view;
    this.options = options;
    const c = view.model.data.columns;
    this.lat = [reader(c.lat1), reader(c.lat2)];
    this.lon = [reader(c.lon1), reader(c.lon2)];
    this.over = c.over;
    // a pane of its own above Leaflet's overlays (the shore's and the coarser terrain's outlines stay under the lines)
    // and below the markers
    const pane = map.getPane(PANE) ?? map.createPane(PANE);
    pane.style.zIndex = "450";
    pane.style.pointerEvents = "none";
    this.renderer = new Draw({pane: PANE, padding: 0.3, onUpdate: () => this.full()});
    this.anchorMarks.addTo(map);
    map.on("resize", this.refresh).on("click", this.onClick).on("contextmenu", this.onMenu);
    map.on("mousemove", this.onMouseMove).on("mouseout", this.onMouseOut).on("zoomend", this.afterZoom);
    const el = map.getContainer();
    el.classList.add("v-leaflet");
    el.addEventListener("pointerdown", this.onPointerDown, true);
    el.addEventListener("pointermove", this.onPointerMove, true);
    el.addEventListener("pointerup", this.endHold, true);
    el.addEventListener("pointercancel", this.endHold, true);
    this.unsubscribe = view.subscribe(() => {
      if (this.busy) return;
      this.paint(true);
      // "Lines from here" opened now (by a press here, or by the page through the model): the map moves for it, but
      // only when a far end lies outside the view; a sort of its rows is the same fan
      const fan = view.fan, opened = fan !== null && fan !== this.fanShown;
      this.fanShown = fan;
      if (opened) this.showFan();
    });
    map.addLayer(this.renderer);  // draws at once when the map has a view
  }

  /** Remove every layer and handler of this map. */
  destroy() {
    this.unsubscribe();
    this.listeners.clear();
    clearTimeout(this.flashTimer);
    clearTimeout(this.checkTimer);
    this.endHold();
    const map = this.map, el = map.getContainer();
    map.off("resize", this.refresh).off("click", this.onClick).off("contextmenu", this.onMenu);
    map.off("mousemove", this.onMouseMove).off("mouseout", this.onMouseOut).off("zoomend", this.afterZoom);
    el.classList.remove("v-leaflet", "v-target");
    el.removeEventListener("pointerdown", this.onPointerDown, true);
    el.removeEventListener("pointermove", this.onPointerMove, true);
    el.removeEventListener("pointerup", this.endHold, true);
    el.removeEventListener("pointercancel", this.endHold, true);
    map.removeLayer(this.anchorMarks);
    if (map.hasLayer(this.renderer)) map.removeLayer(this.renderer);
  }

  /** Call `f` when the legend's content changed (the shapes drawn, the squares' breaks); returns the stop. */
  subscribe(f: () => void): () => void {
    this.listeners.add(f);
    return () => { this.listeners.delete(f); };
  }

  /** What the legend lists: exactly the shapes and colours on the map now. */
  legend(): Legend { return this.legendNow; }

  /** What the squares show (the legend's select). */
  get squareBy(): SquareBy { return this.by; }
  setSquareBy(by: SquareBy) {
    if (by === this.by) return;
    this.by = by;
    this.paint(true);
  }

  // --- the view's rectangle ---

  /** The part of the map's box a person sees, in the container's pixels. */
  private freeBox(): {left: number; top: number; right: number; bottom: number} {
    const size = this.map.getSize(), p = this.options.free?.() ?? NONE;
    const left = Math.min(Math.max(0, p.left), size.x), top = Math.min(Math.max(0, p.top), size.y);
    return {left, top, right: Math.max(left, size.x - Math.max(0, p.right)), bottom: Math.max(top, size.y - Math.max(0, p.bottom))};
  }

  /** A full redraw: the canvas placed on the map as it is now, the view's rectangle and metres per pixel to the
   *  model, then the picture. The map's moves call it; the frame calls it when the free part changed without one
   *  (a phone's sheet moved). */
  refresh = () => {
    if ((this.renderer as any)._map) (this.renderer as any)._update();
  };

  private full() {
    const map = this.map, fit = this.view.fit, box = this.freeBox();
    if (!(box.right > box.left && box.bottom > box.top)) return;
    const corner = (x: number, y: number): [number, number] => {
      const at = map.containerPointToLatLng([x, y]);
      return fit.toGrid(at.lat, at.lng);
    };
    const quad: Quad = [corner(box.left, box.top), corner(box.right, box.top), corner(box.right, box.bottom),
                        corner(box.left, box.bottom)];
    // metres of the grid per pixel at the view's middle: the map's metres on the ground there, by the grid's scale
    // (the corners above are clamped to the run's box by the fit, so their distance is not the view's width)
    const y = (box.top + box.bottom) / 2, x = (box.left + box.right) / 2, span = Math.min(64, (box.right - box.left) / 2);
    const west = map.containerPointToLatLng([x - span, y]), east = map.containerPointToLatLng([x + span, y]);
    const mpp = map.distance(west, east) / (2 * span) * fit.scale((west.lat + east.lat) / 2, (west.lng + east.lng) / 2);
    this.busy = true;
    try {
      this.view.setView(quad, mpp);
    } finally {
      this.busy = false;
    }
    this.paint(true);
    this.options.onDrawn?.();
  }

  // --- the picture ---

  /** The line's ends in the layer's pixels, into `out` (x1, y1, x2, y2 from `at`). */
  private ends(row: number, out: number[] | Float64Array, at = 0) {
    for (let e = 0; e < 2; e++) {
      const s = Math.sin(this.lat[e](row) * D);
      out[at + 2 * e] = (this.lon[e](row) / 360 + 0.5) * this.scale - this.ox;
      out[at + 2 * e + 1] = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * this.scale - this.oy;
    }
  }

  /** A grid place in the layer's pixels (through the fit). */
  private place(x: number, y: number): [number, number] {
    const [lat, lon] = this.view.fit.toLatLng(x, y), s = Math.sin(lat * D);
    return [(lon / 360 + 0.5) * this.scale - this.ox, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * this.scale - this.oy];
  }

  /** The free part of the map in the layer's pixels: the part a person sees, and the boxes of every control on it. */
  private measureFree() {
    const map = this.map, el = map.getContainer(), box = el.getBoundingClientRect(), off = map.containerPointToLayerPoint([0, 0]);
    const f = this.freeBox(), rects: number[][] = [];
    let sig = `${f.left},${f.top},${f.right},${f.bottom}`;
    const add = (r: DOMRect) => {
      if (!r.width || !r.height || r.right <= box.left || r.left >= box.right || r.bottom <= box.top || r.top >= box.bottom) return;
      const q = [Math.floor(r.left - box.left), Math.floor(r.top - box.top), Math.ceil(r.right - box.left), Math.ceil(r.bottom - box.top)];
      sig += "|" + q.join(",");
      rects.push([q[0] + off.x, q[1] + off.y, q[2] + off.x, q[3] + off.y]);
    };
    (el.parentElement ?? el).querySelectorAll("[data-map-control], .leaflet-control").forEach((e) => add(e.getBoundingClientRect()));
    this.options.obstacles().forEach(add);
    return {x0: f.left + off.x, y0: f.top + off.y, x1: f.right + off.x, y1: f.bottom + off.y, rects, sig};
  }

  /** The pieces of a line (fractions of a → b) where the middle of a shape of half-size (hw, hh) may lie: the whole
   *  shape on the map and PAD px clear of every control; the longest first. */
  private freeParts(ax: number, ay: number, bx: number, by: number, hw: number, hh: number): [number, number][] {
    const f = this.free, mx = hw + PAD, my = hh + PAD;
    const inside = clipT(ax, ay, bx, by, f.x0 + mx, f.y0 + my, f.x1 - mx, f.y1 - my);
    if (!inside) return [];
    let parts: [number, number][] = [inside];
    for (const r of f.rects) {
      const cut = clipT(ax, ay, bx, by, r[0] - mx, r[1] - my, r[2] + mx, r[3] + my);
      if (!cut) continue;
      const next: [number, number][] = [];
      for (const s of parts) {
        if (cut[1] <= s[0] || cut[0] >= s[1]) { next.push(s); continue; }
        if (cut[0] > s[0]) next.push([s[0], cut[0]]);
        if (cut[1] < s[1]) next.push([cut[1], s[1]]);
      }
      parts = next;
    }
    return parts.sort((s, u) => (u[1] - u[0]) - (s[1] - s[0]) || s[0] - u[0]);
  }

  /** Draw the view again: `full` with the presses' targets and the controls measured anew; else only the picture
   *  (a hover). */
  private paint(full: boolean, pass = 0) {
    const r = this.renderer as any, ctx = r._ctx as CanvasRenderingContext2D | undefined, b = r._bounds as L.Bounds | undefined;
    if (!ctx || !b || (this.map as any)._animatingZoom) return;
    timed("fal:view:draw", () => this.draw(ctx, b, r._m as number, full));
    if (!full) return;
    // the status line or the legend may change its size once the page has drawn this state: the numbers are then
    // placed again, at most twice
    clearTimeout(this.checkTimer);
    if (pass >= 2) return;
    this.checkTimer = window.setTimeout(() => {
      if ((this.renderer as any)._map && this.measureFree().sig !== this.free.sig) this.paint(true, pass + 1);
    }, 0);
  }

  private draw(ctx: CanvasRenderingContext2D, b: L.Bounds, m: number, full: boolean) {
    const view = this.view, map = this.map, level = view.level, v = view.inView, size = b.getSize(), min = b.min!;
    const origin = map.getPixelOrigin();
    this.scale = 256 * Math.pow(2, map.getZoom());
    this.ox = origin.x; this.oy = origin.y;
    if (full) {
      this.free = this.measureFree();
      this.tx = []; this.trow = []; this.trank = [];
    }
    this.marks = [];
    this.fanLines = [];
    ctx.setTransform(m, 0, 0, m, -min.x * m, -min.y * m);
    ctx.clearRect(min.x, min.y, size.x, size.y);
    ctx.lineCap = "round";
    const shapes: Legend["shapes"] = {}, fan = view.fan, sel = view.selected, dim = sel || fan ? 0.3 : 1;
    const p = new Float64Array(4), over = this.over;
    const counted = new Set<number>();  // the lines stroked, each once (a line may be drawn twice: thin and bold)
    let found: number[] = [];
    const inFan = new Set<number>();
    if (fan) for (const row of fan.rows) if (row.label[0] !== "L") inFan.add(row.row);  // its number is drawn by the fan, once

    const trace = (rows: ArrayLike<number>, which: number) => {  // which: 0 clear, 1 over, 2 every line
      let n = 0;
      ctx.beginPath();
      for (let k = 0; k < rows.length; k++) {
        const row = rows[k];
        if (which < 2 && over[row] !== which) continue;
        this.ends(row, p);
        ctx.moveTo(p[0], p[1]); ctx.lineTo(p[2], p[3]);
        n++;
      }
      return n;
    };
    /** Stroke lines in their colours (clear, over trees or buildings), or all in `colour`; counted once with `count`. */
    const stroke = (rows: ArrayLike<number>, width: number, alpha: number, colour?: string, count = false) => {
      if (!rows.length) return;
      ctx.lineWidth = width; ctx.globalAlpha = alpha;
      if (colour) { ctx.strokeStyle = colour; trace(rows, 2); ctx.stroke(); }
      else {
        ctx.strokeStyle = COLORS.clean;
        if (trace(rows, 0)) { ctx.stroke(); shapes.clear = true; }
        ctx.strokeStyle = COLORS.over;
        if (trace(rows, 1)) { ctx.stroke(); shapes.over = true; }
      }
      ctx.globalAlpha = 1;
      if (count) for (let k = 0; k < rows.length; k++) counted.add(rows[k]);
    };
    const target = (rows: ArrayLike<number>, rank: number) => {
      if (!full) return;
      for (let k = 0; k < rows.length; k++) {
        this.ends(rows[k], p);
        this.tx.push(p[0], p[1], p[2], p[3]); this.trow.push(rows[k]); this.trank.push(rank);
      }
    };
    const mark = (kind: MarkKind, x: number, y: number, text: string, spot: number, row: number, ring?: string, end?: 1 | 2) => {
      shapePath(ctx, kind, x, y, text);
      ctx.fillStyle = PAPER; ctx.fill();
      ctx.lineWidth = ring ? 2.4 : 1.6; ctx.strokeStyle = ring ?? INK; ctx.stroke();
      ctx.fillStyle = INK; ctx.font = "600 11px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(text, x, y + 0.5);
      shapes[kind] = true;
      const [w, h] = markSize(kind, text);
      this.marks.push({kind, text, x, y, w, h, spot, row, end});
    };
    const badges: [number, number][] = [];
    /** The number of a line: on the longest piece of the line that is on the map and clear of the controls, at the
     *  first of seven places a box away from every earlier number, else the farthest; nearer than a quarter of a
     *  box to an earlier one, or with no free piece: no number on the map (the row keeps it). */
    const badge = (row: number, text: string, kind: MarkKind, spot: number) => {
      this.ends(row, p);
      const ax = p[0], ay = p[1], bx = p[2], by = p[3], [hw, hh] = markSize(kind, text);
      const parts = this.freeParts(ax, ay, bx, by, hw, hh);
      if (!parts.length) return;
      let at: [number, number] | null = null, apart = -1;
      for (let n = 0; n < parts.length && apart < 1; n++) {
        for (const f of [0.5, 0.36, 0.64, 0.24, 0.76, 0.14, 0.86]) {
          if (apart >= 1) break;
          const s = parts[n][0] + (parts[n][1] - parts[n][0]) * f, x = ax + (bx - ax) * s, y = ay + (by - ay) * s;
          let near = 1e9;
          for (const q of badges) near = Math.min(near, Math.max(Math.abs(q[0] - x) / 32, Math.abs(q[1] - y) / 23));
          if (near > apart) { apart = near; at = [x, y]; }
        }
      }
      if (!at || apart < 0.25) return;
      badges.push(at);
      mark(kind, at[0], at[1], text, spot, row);
    };
    const shownOf = (spots: ArrayLike<number>) => Array.from(spots, (s) => view.shownOf(s));

    if (level === "area") {
      const grid = timed("fal:view:squares", () => squareValues(view, squareSide(view.mpp), this.by));
      const br = breaks(grid.values, this.by === "spots" || this.by === "lines");
      this.grid = grid;
      found = br;
      const colours = this.layerColours();
      // only the squares on the canvas: their middles against the canvas's box in grid metres (the fit's corners)
      const side = grid.side, px = side / view.mpp, label = px >= SQUARE_PX;
      const corners = [this.gridAt(min.x, min.y), this.gridAt(min.x + size.x, min.y), this.gridAt(min.x + size.x, min.y + size.y),
                       this.gridAt(min.x, min.y + size.y)];
      const gx0 = Math.min(...corners.map((c) => c[0])) - side, gx1 = Math.max(...corners.map((c) => c[0])) + side;
      const gy0 = Math.min(...corners.map((c) => c[1])) - side, gy1 = Math.max(...corners.map((c) => c[1])) + side;
      let drawn = 0;
      for (let k = 0; k < grid.cells.length; k++) {
        const cell = grid.cells[k], i = cell % grid.nx, j = (cell - i) / grid.nx;
        const x = grid.x0 + i * side, y = grid.y0 + j * side;
        if (x + side < gx0 || x > gx1 || y + side < gy0 || y > gy1) continue;
        const a = this.place(x, y), bb = this.place(x + side, y), c = this.place(x + side, y + side), d = this.place(x, y + side);
        const cls = classOf(grid.values[k], br);
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(bb[0], bb[1]); ctx.lineTo(c[0], c[1]); ctx.lineTo(d[0], d[1]); ctx.closePath();
        ctx.globalAlpha = 0.62 * (dim < 1 ? 0.6 : 1); ctx.fillStyle = colours[cls]; ctx.fill();
        ctx.globalAlpha = 0.9; ctx.lineWidth = 0.8; ctx.strokeStyle = colours[cls]; ctx.stroke();
        if (label) {
          const text = String(Math.round(grid.values[k])), cx = (a[0] + c[0]) / 2, cy = (a[1] + c[1]) / 2;
          ctx.font = `600 ${px >= 44 ? 13 : px >= 32 ? 11 : 10}px system-ui, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.lineWidth = 2.5; ctx.globalAlpha = 0.55; ctx.strokeStyle = cls >= 2 ? INK : PAPER; ctx.strokeText(text, cx, cy);
          ctx.globalAlpha = 1; ctx.fillStyle = cls >= 2 ? PAPER : INK; ctx.fillText(text, cx, cy);
        }
        drawn++;
      }
      ctx.globalAlpha = 1;
      if (drawn) shapes.sq = true;
      const picks = view.picks(), lines = picks.map((pick) => pick.row);
      stroke(lines, 7, 0.55 * dim, PAPER);
      stroke(lines, 3.5, dim, undefined, true);
      target(lines, 2);
      for (const pick of picks) if (!inFan.has(pick.row)) badge(pick.row, "P" + pick.n, "P", pick.spot);
    } else {
      this.grid = null;
      const all = view.best === "all", refused = v.refused > 0;
      const isBest = new Set<number>(refused ? [] : Array.from(v.best));
      const rest = shownOf(Array.from(v.spots).filter((s) => !isBest.has(s)));
      stroke(rest, 1.5, 0.24 * dim, undefined, true);
      target(rest, 0);
      if (rest.length) shapes.pale = true;
      if (level === "lines" && v.thin) {
        stroke(v.thin, 1, (all ? 0.22 : 0.3) * dim, undefined, true);
        target(v.thin, 1);
      }
      if (!refused && !(level === "lines" && all)) {
        const bold = shownOf(v.best);
        if (level === "lines") stroke(bold, 6, 0.5 * dim, PAPER);
        stroke(bold, 3, 0.92 * dim, undefined, true);
        target(bold, all ? 1 : 2);
        if (v.numbered) {
          ctx.globalAlpha = dim < 1 ? 0.55 : 1;
          for (let r = 0; r < v.best.length; r++) {
            const row = view.shownOf(v.best[r]);
            if (!inFan.has(row)) { badge(row, "B" + (r + 1), "B", v.best[r]); ctx.globalAlpha = dim < 1 ? 0.55 : 1; }
          }
          ctx.globalAlpha = 1;
        }
      }
    }

    if (this.flash) stroke(this.flash, 5, 0.9, this.accent());
    if (sel && !fan) {
      const own = Array.from(view.passingOf(sel.spot)).filter((row) => row !== sel.row);
      stroke(own, 1, 0.8, undefined, true);
      target(own, 1);
      stroke([sel.row], 11, 0.45, "#000");
      stroke([sel.row], 5, 1, undefined, true);
      target([sel.row], 2);
      this.ends(sel.row, p);
      const states = [accessState(sel.line.access1), accessState(sel.line.access2)];
      const rings = [null, "--acc-map-hard", "--acc-map-tell", "--acc-map-easy"];
      for (const end of [1, 2] as const) {
        const state = states[end - 1];
        mark("A", p[2 * end - 2], p[2 * end - 1], "A" + end, sel.spot, sel.row,
             state === null ? undefined : this.token(rings[state + 1]!), end);
      }
    }
    if (full) this.placeAnchorMarks();
    if (fan) {
      const rows = fan.rows.map((row) => row.row);
      stroke(rows, 7, 0.5, PAPER);
      stroke(rows, 3.2, 1, undefined, true);
      for (const row of fan.rows) {
        this.ends(row.row, p);
        this.fanLines.push({x1: p[0], y1: p[1], x2: p[2], y2: p[3], row: row.row});
        // its number near the far end (the lines meet at the point), on the free piece of the line
        const near = row.near === 1 ? 0 : 2, far = 2 - near, kind: MarkKind = row.label[0] === "L" ? "L" : row.label[0] as MarkKind;
        const [hw, hh] = markSize(kind, row.label), parts = this.freeParts(p[near], p[near + 1], p[far], p[far + 1], hw, hh);
        if (!parts.length) continue;
        const s = parts[0][0] + (parts[0][1] - parts[0][0]) * 0.82;
        mark(kind, p[near] + (p[far] - p[near]) * s, p[near + 1] + (p[far + 1] - p[near + 1]) * s, row.label, view.spotOf(row.row), row.row);
      }
      const at = this.place(fan.xy[0], fan.xy[1]);
      ctx.beginPath(); ctx.arc(at[0], at[1], Math.max(9, FAN_HERE / view.mpp), 0, 2 * Math.PI);
      ctx.lineWidth = 2; ctx.strokeStyle = INK; ctx.setLineDash([4, 3]); ctx.stroke(); ctx.setLineDash([]);
      shapes.here = true;
    }
    const hover = this.hovered ?? this.mapHovered;
    if (hover !== null && view.passes(hover)) stroke([hover], 7, 0.95);
    if (this.marker) {
      const at = map.latLngToLayerPoint(this.marker);
      ctx.beginPath(); ctx.arc(at.x, at.y, 6, 0, 2 * Math.PI);
      ctx.fillStyle = PAPER; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = "#000"; ctx.stroke();
    }
    ctx.globalAlpha = 1;
    if (!full) return;
    this.strokes = counted.size;
    const legend: Legend = {level, shapes, by: this.by, breaks: found};
    const key = JSON.stringify(legend);
    this.legendNow = legend;
    if (key !== this.legendKey) {
      this.legendKey = key;
      this.listeners.forEach((f) => f());
    }
  }

  /** A layer point in grid metres (through the fit). */
  private gridAt(x: number, y: number): [number, number] {
    const at = this.map.layerPointToLatLng([x, y]);
    return this.view.fit.toGrid(at.lat, at.lng);
  }

  private token(name: string): string {
    return getComputedStyle(this.map.getContainer()).getPropertyValue(name).trim() || "#888";
  }

  private accent(): string { return this.token("--accent"); }

  /** The squares' five classes' colours (the highline layer's tokens). */
  private layerColours(): string[] {
    const style = getComputedStyle(this.map.getContainer());
    return [1, 2, 3, 4, 5].map((k) => style.getPropertyValue(`--layer-${k}`).trim() || "#3987e5");
  }

  /** The access mark on the corner of A1 and A2 of the selected line (a run made with the mark): markers' icons
   *  that take no pointer events (a press there goes to the map as beside them). */
  private placeAnchorMarks() {
    this.anchorMarks.clearLayers();
    const sel = this.view.selected;
    if (!sel || this.view.fan) return;
    const l = sel.line, ends: [number, number, number | null][] = [[l.lat1, l.lon1, accessState(l.access1)], [l.lat2, l.lon2, accessState(l.access2)]];
    ends.forEach(([lat, lon, state], k) => {
      if (state === null) return;
      const label = t("ui.access.anchor_state", {n: k + 1, state: accessWord(state)});
      L.marker([lat, lon], {interactive: false, keyboard: false, icon: L.divIcon({
        className: "ac-map-icon v-anchor-mark", html: accessMarkSvg(state, label), iconSize: [18, 18], iconAnchor: [-2, 20]})})
        .addTo(this.anchorMarks);
    });
  }

  /** What the map shows now, by the page's own count: the lines stroked (each line once, however often it is drawn:
   *  thin and bold, pale and selected; its halo not counted)
   *  and the numbers with their boxes in the viewport. */
  drawn(): {strokes: number; numbers: {label: string; box: DOMRect}[]} {
    const box = this.map.getContainer().getBoundingClientRect();
    return {strokes: this.strokes, numbers: this.marks.map((m) => {
      const at = this.map.layerPointToContainerPoint([m.x, m.y]);
      return {label: m.text, box: new DOMRect(box.left + at.x - m.w, box.top + at.y - m.h, 2 * m.w, 2 * m.h)};
    })};
  }

  // --- presses ---

  private byFinger(): boolean {
    return this.options.phone === true || this.pressedBy === "touch";
  }

  /** The number's shape under a point: its own box (2 px more with a mouse, at least 40 × 40 px with a finger); of
   *  several the one whose middle is nearest. A shape wins over every line under it. */
  private markAt(x: number, y: number, finger: boolean): Placed | null {
    let best: Placed | null = null, bd = 1e9;
    for (const m of this.marks) {
      const hw = finger ? Math.max(m.w, 20) : m.w + 2, hh = finger ? Math.max(m.h, 20) : m.h + 2, dx = Math.abs(x - m.x), dy = Math.abs(y - m.y);
      if (dx <= hw && dy <= hh && Math.hypot(dx, dy) < bd) { bd = Math.hypot(dx, dy); best = m; }
    }
    return best;
  }

  /** The spots a press reaches, each by one line. A bold line wins over the thin and pale lines beside it where it
   *  is within the tie of the nearest thin line; a thin line where it is clearly the nearer; a pale line only alone.
   *  `others`: the spots whose bold line is in reach but was not taken. */
  private pick(x: number, y: number, finger: boolean): {found: Hit[]; others: Hit[]} {
    const reach = finger ? REACH_TOUCH : REACH_MOUSE, tie = finger ? TIE_TOUCH : TIE_MOUSE, tx = this.tx;
    const per = [new Map<number, Hit>(), new Map<number, Hit>(), new Map<number, Hit>()];
    for (let k = 0; k < this.trow.length; k++) {
      const d = segmentDistance(x, y, tx[4 * k], tx[4 * k + 1], tx[4 * k + 2], tx[4 * k + 3]);
      if (d > reach) continue;
      const row = this.trow[k], spot = this.view.spotOf(row), into = per[this.trank[k]], had = into.get(spot);
      if (!had || d <= had.d) into.set(spot, {spot, row, d});
    }
    const sorted = (m: Map<number, Hit>) => Array.from(m.values()).sort((a, b) => a.d - b.d);
    const bold = sorted(per[2]), thin = sorted(per[1]);
    let from = sorted(per[0]), others: Hit[] = [];
    if (bold.length && (!thin.length || bold[0].d <= thin[0].d + tie)) from = bold;
    else if (thin.length) { from = thin; others = bold; }
    const found = from.filter((f) => f.d <= from[0].d + tie).slice(0, CHOICES_MAX);
    return {found, others: others.filter((o) => !found.some((f) => f.spot === o.spot))};
  }

  /** The spots a press at a point of the map's box would take (a number's shape first; an anchor's circle: none). */
  pickAt(x: number, y: number, finger: boolean): number[] {
    const at = this.map.containerPointToLayerPoint([x, y]), m = this.markAt(at.x, at.y, finger);
    return m ? (m.kind === "A" ? [] : [m.spot]) : this.pick(at.x, at.y, finger).found.map((f) => f.spot);
  }

  /** A press on a number: B, P and L select their line, A opens the lines from that anchor. */
  private pressMark(m: Placed) {
    if (m.kind !== "A") { this.view.select(m.spot, m.row); return; }
    const l = this.view.selected!.line, end = m.end ?? 1;
    this.view.openFan(L.latLng(end === 1 ? [l.lat1, l.lon1] : [l.lat2, l.lon2]), {row: m.row, end});
  }

  /** The table of the spots under a press: a numbered spot reads as on the map and stands for its bold line; the
   *  numbered spots first, by their number, the others by their distance. */
  private choose(hits: Hit[], at: L.Point) {
    const seen = new Set<number>(), rows: (SpotChoice & {n: number})[] = [];
    for (const h of hits) {
      if (seen.has(h.spot)) continue;
      seen.add(h.spot);
      const mark = this.view.markOf(h.spot);
      rows.push({spot: h.spot, row: mark ? mark.row : h.row, label: mark ? mark.kind + mark.n : null, px: h.d, n: mark ? mark.n : 0});
    }
    rows.sort((a, b) => (a.n ? 0 : 1) - (b.n ? 0 : 1) || (a.n && b.n ? a.n - b.n : a.px - b.px));
    this.options.onChoose(rows.slice(0, CHOICES_MAX).map(({n: _, ...row}) => row), at);
  }

  private onClick = (e: L.LeafletMouseEvent) => {
    if (this.swallowClick) { this.swallowClick = false; return; }  // the end of a press held: it opened the fan
    const view = this.view, pt = e.layerPoint, finger = this.byFinger(), m = this.markAt(pt.x, pt.y, finger);
    if (m) { this.pressMark(m); return; }
    if (view.fan) {
      // a line of the fan selects it; an empty point closes "Lines from here" and keeps the spot
      let best = -1, bd = finger ? REACH_TOUCH : REACH_MOUSE;
      for (const f of this.fanLines) {
        const d = segmentDistance(pt.x, pt.y, f.x1, f.y1, f.x2, f.y2);
        if (d <= bd) { bd = d; best = f.row; }
      }
      if (best >= 0) view.select(view.spotOf(best), best); else view.closeFan();
      return;
    }
    const {found, others} = this.pick(pt.x, pt.y, finger);
    if (found.length > 1) {
      if (finger) this.crowded(e.latlng, found, others, e.containerPoint);
      else this.choose(found.concat(others), e.containerPoint);
      return;
    }
    if (found.length === 1) { view.select(found[0].spot, found[0].row); return; }
    if (view.level === "area" && this.grid) {
      const [x, y] = view.fit.toGrid(e.latlng.lat, e.latlng.lng), grid = this.grid;
      if (squareAt(grid, x, y) >= 0) {
        const i = Math.floor((x - grid.x0) / grid.side), j = Math.floor((y - grid.y0) / grid.side);
        const x0 = grid.x0 + i * grid.side, y0 = grid.y0 + j * grid.side;
        this.map.fitBounds(this.bounds([[x0, y0], [x0 + grid.side, y0], [x0 + grid.side, y0 + grid.side], [x0, y0 + grid.side]]),
                           {...this.fitOptions(this.own(), 30, view.auto ? SQUARE_MPP : CLOSE_MPP), animate: true});
        return;
      }
    }
    if (view.selected) view.select(null);
  };

  /** Several spots under a finger: the map zooms in one level around the point, flashes their lines and says so;
   *  once it shows CLOSE_MPP or closer, the table of spots opens. */
  private crowded(at: L.LatLng, found: Hit[], others: Hit[], point: L.Point) {
    if (this.view.mpp <= CLOSE_MPP * 1.001 || this.map.getZoom() >= this.map.getMaxZoom() - 0.01) {
      this.choose(found.concat(others), point);
      return;
    }
    this.flashRows(found.map((f) => f.row), FLASH_TAP);
    this.map.setZoomAround(at, Math.min(this.map.getMaxZoom(), this.map.getZoom() + 1));
    this.options.onToast(t("ui.view.map.crowded"));
  }

  private flashRows(rows: number[], ms: number) {
    this.flash = rows;
    clearTimeout(this.flashTimer);
    this.flashTimer = window.setTimeout(() => { this.flash = null; this.paint(false); }, ms);
    this.paint(false);
  }

  /** "Lines from here" at a point of the map (a right click, a press held): a number's shape there is a press on
   *  it; no line within reach: the map says so (an open fan stays). */
  private menuAt(point: L.Point, at: L.LatLng) {
    const layer = this.map.containerPointToLayerPoint(point), m = this.markAt(layer.x, layer.y, this.byFinger());
    if (m) { this.pressMark(m); return; }
    const misses = this.view.fanMisses;
    this.view.openFan(at);
    if (this.view.fanMisses !== misses) this.options.onToast(t("ui.view.map.fan_none", {m: FAN_HERE}));
  }

  /** The map moves for an open fan only when a far end lies outside the view. */
  private showFan() {
    const fan = this.view.fan;
    if (!fan) return;
    const box = this.freeBox(), points: L.LatLng[] = [fan.at];
    for (const row of fan.rows) {
      const far = row.near === 1 ? 1 : 0;
      points.push(L.latLng(this.lat[far](row.row), this.lon[far](row.row)));
    }
    const outside = points.some((at) => {
      const q = this.map.latLngToContainerPoint(at);
      return q.x < box.left || q.x > box.right || q.y < box.top || q.y > box.bottom;
    });
    if (outside) this.map.fitBounds(L.latLngBounds(points), this.fitOptions(this.own(), 30));
  }

  private onMenu = (e: L.LeafletMouseEvent) => {
    e.originalEvent?.preventDefault?.();  // no menu of the browser on the map
    if (performance.now() - this.heldAt < MENU_QUIET) return;  // the browser's own long-press event of the press held
    this.endHold();  // the browser's event came first (Chrome on a phone, after about 500 ms): the press is taken
    if (this.pressedBy !== "mouse") this.swallowClick = true;
    this.menuAt(e.containerPoint ?? this.map.latLngToContainerPoint(e.latlng), e.latlng);
  };

  // A press held by a finger or a pen (its own timer: only Safari's phones get Leaflet's): HOLD_MS within HOLD_PX
  private onPointerDown = (e: PointerEvent) => {
    this.pressedBy = e.pointerType;
    this.swallowClick = false;
    this.endHold();
    if (e.pointerType === "mouse" || !e.isPrimary || (e.target as HTMLElement).closest?.(".leaflet-control")) return;
    const id = e.pointerId, x = e.clientX, y = e.clientY;
    this.hold = {id, x, y, timer: window.setTimeout(() => {
      this.hold = null;
      const box = this.map.getContainer().getBoundingClientRect(), point = L.point(x - box.left, y - box.top);
      this.heldAt = performance.now();
      this.swallowClick = true;
      this.menuAt(point, this.map.containerPointToLatLng(point));
    }, HOLD_MS)};
  };

  private onPointerMove = (e: PointerEvent) => {
    const h = this.hold;
    if (h && (e.pointerId !== h.id || Math.hypot(e.clientX - h.x, e.clientY - h.y) > HOLD_PX)) this.endHold();
  };

  private endHold = () => {
    if (this.hold) clearTimeout(this.hold.timer);
    this.hold = null;
  };

  private afterZoom = () => { this.endHold(); };

  // The line a press would take, under the mouse (thicker); none for the mouse events of a finger or while "Lines
  // from here" is open
  private onMouseMove = (e: L.LeafletMouseEvent) => {
    if (this.pressedBy === "touch" || this.view.fan || (e.originalEvent as any)?.sourceCapabilities?.firesTouchEvents) {
      this.setMapHovered(null, false);
      return;
    }
    const pt = e.layerPoint, m = this.markAt(pt.x, pt.y, false), found = m ? [] : this.pick(pt.x, pt.y, false).found;
    this.setMapHovered(m ? (m.kind === "A" ? null : m.row) : found.length ? found[0].row : null, !!m);
  };

  private onMouseOut = () => this.setMapHovered(null, false);

  private setMapHovered(row: number | null, onMark: boolean) {
    this.map.getContainer().classList.toggle("v-target", onMark || row !== null);
    if (row === this.mapHovered) return;
    this.mapHovered = row;
    this.paint(false);
  }

  // --- moves ---

  private fitOptions(p: Padding, margin: number, maxMpp?: number): L.FitBoundsOptions {
    // What covers the map may leave no room (a phone's sheet at full: the bar's foot stands above the map's top):
    // FIT_ROOM px stay for the fitted thing each way, the paddings give way in their proportion (with none left,
    // Leaflet's fit would ask for the zoom of a negative size)
    const size = this.map.getSize();
    const squeeze = (a: number, b: number, total: number): [number, number] => {
      const over = a + b - Math.max(0, total - FIT_ROOM);
      return over > 0 && a + b > 0 ? [a - over * a / (a + b), b - over * b / (a + b)] : [a, b];
    };
    const [top, bottom] = squeeze(p.top + margin, p.bottom + margin, size.y);
    const [left, right] = squeeze(p.left + margin, p.right + margin, size.x);
    return {paddingTopLeft: [left, top], paddingBottomRight: [right, bottom],
            maxZoom: maxMpp ? this.zoomOf(maxMpp) : this.view.model.data.max_zoom, animate: false};
  }

  /** The zoom at which the map shows `mpp` metres per pixel or a little more, on the map's quarter steps (not above
   *  its last). */
  zoomOf(mpp: number): number {
    const now = this.view.mpp, zoom = this.map.getZoom();
    const want = now === now ? zoom + Math.log2(now / mpp) : zoom;
    return Math.min(this.map.getMaxZoom(), Math.floor(want / SNAP + 1e-6) * SNAP);
  }

  /** The frame's padding for the canvas's own moves. */
  private own(): Padding {
    return this.options.padding?.() ?? this.options.free?.() ?? NONE;
  }

  private bounds(xy: [number, number][]): L.LatLngBounds {
    return L.latLngBounds(xy.map(([x, y]) => this.view.fit.toLatLng(x, y)));
  }

  private lineBounds(rows: ArrayLike<number>): L.LatLngBounds {
    const points: [number, number][] = [];
    for (let k = 0; k < rows.length; k++) for (let e = 0; e < 2; e++) points.push([this.lat[e](rows[k]), this.lon[e](rows[k])]);
    return L.latLngBounds(points);
  }

  /** Fit the map to the run's lines (the box of their anchors), `p` px kept free on each side. */
  fitArea(p: Padding = NONE) {
    const box = this.view.model.data.box;
    if (!box) return;
    this.map.fitBounds(this.bounds([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]),
                       this.fitOptions(p, 16));
  }

  /** Fit the map to a line, `p` px kept free on each side plus a margin. */
  zoomTo(row: number, p: Padding = NONE) {
    this.map.fitBounds(this.lineBounds([row]), this.fitOptions(p, 60));
  }

  /** Bring a line of the list into view: the map moves only when the line is not inside the view less 8 % or is
   *  under 60 px long (then it is fitted, not closer than CLOSE_MPP). */
  reveal(row: number, p: Padding = NONE) {
    const box = this.freeBox(), dx = (box.right - box.left) * 0.08, dy = (box.bottom - box.top) * 0.08;
    const ends = [0, 1].map((e) => this.map.latLngToContainerPoint([this.lat[e](row), this.lon[e](row)]));
    const inside = ends.every((q) => q.x >= box.left + dx && q.x <= box.right - dx && q.y >= box.top + dy && q.y <= box.bottom - dy);
    if (inside && ends[0].distanceTo(ends[1]) >= 60) return;
    this.map.fitBounds(this.lineBounds([row]), this.fitOptions(p, 50, CLOSE_MPP));
  }

  /** Fit the map to the shown lines of a sector's spots (`n`: the sector from 0) and flash them. */
  showSector(n: number) {
    const sector = this.view.sectors.find((s) => s.n === n);
    if (!sector || !sector.spots.length) return;
    const rows = sector.spots.map((spot) => this.view.shownOf(spot));
    this.map.fitBounds(this.lineBounds(rows), this.fitOptions(this.own(), 14, CLOSE_MPP));
    this.flashRows(rows, FLASH_SECTOR);
  }

  /** Draw a line wider (a row of the list under the mouse); null: none. */
  highlight(row: number | null) {
    if (row === this.hovered) return;
    this.hovered = row;
    this.paint(false);
  }

  /** The point of the profile under the mouse; null: none. */
  hoverAt(at: L.LatLngExpression | null) {
    this.marker = at ? L.latLng(at as any) : null;
    this.paint(false);
  }
}
