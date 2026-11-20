// The result view's canvas (docs/line-volume/spec-view.md B.2): draws a SpotView (spots.ts) on a Leaflet map the
// frame (view/SpotColumns.tsx) owns, takes the presses, and tells the view what the map shows. One canvas of its
// own (a Leaflet renderer without paths: the lines are drawn from the run's columns, never as one layer each),
// drawn again in full after every move, zoom or resize of the map and every change of the view:
// - the part of the map a person sees goes to the view as a Quad in the run's grid metres with its metres per
//   pixel (SpotView.setView: the level under Auto, the spots in view, their numbers);
// - Area: the squares (viewgeom.ts squareValues) in five classes with their values, the picks of "Start here"
//   bold with P1 …; a value clear of every control and of the numbers drawn over the squares (the picks', the fan's,
//   A1 and A2; valueAt: in its square's middle, else nearer a side or a corner of it, else left out: the square's
//   colour still tells it); Spots: the best spots' shown lines
//   bold with B1 …, the other spots in view pale; Lines: the best spots' lines not beaten thin, their shown line
//   bold with a halo (with All every passing line in view, thin); above 5 000 thin lines none, only the pale lines
//   (the view counts and refuses);
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
// Step 3c (today's features on the canvas, none of them pressable): the run's search area as today's thin dashed
// outline in the map's ink, over the squares' fills and under their values, the lines and the numbers (no obstacle
// for a number); a favourite that is its spot's shown line on today's gold halo (the selected one gold in the dark
// halo's place); Compare's other runs (ResultModel.others) in their colours with their dashed areas (one line per
// spot of a run with the view's columns, else every passing line), under this run's lines, never counted in the
// levels, the squares, Best N, "in view" or the picks; Measure (the members
// RunActions' RunActionsMap needs: two presses are two points, black dashes between white points, Esc cancels, a
// phone's map holds still) and a measured line the frame draws (drawMeasured); the bottom part the frame covers with
// its profile card (setCovered) is not in view, as a phone's sheet is not.
// The lines are drawn from their own latitudes and longitudes (Web Mercator by hand: two logarithms a line, no
// object per point); the squares' corners and the pressed point go through the view's fit.

import type { Geometry, Position } from "geojson";
import L from "leaflet";
import { accessMarkSvg, accessState, accessWord } from "../access";
import { passes as passesFilters } from "../filters";
import { t } from "../i18n";
import { timed } from "../perf";
import { COLORS } from "../style";
import { LineCursor } from "../types";
import type { Padding } from "./ResultMap";
import type { FanRow, SpotChoice, SpotView } from "./spots";
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

/** What the map shows now, for its legend: the shapes and colours drawn, and at Area the squares' value and breaks;
 *  `runs`: Compare's other runs drawn in the part a person sees (a line or the area's outline), in model.others'
 *  order. */
export interface Legend { level: Level; shapes: {[K in ShapeKind]?: true}; by: SquareBy; breaks: number[]; runs: LegendRun[] }
/** Step 3c's kinds: "fav" a favourite's gold halo in view, "area" the search area's outline crossing the part a person
 *  sees, "measure" a measurement drawn, "ends" an anchor of the selected line (A1 or A2) in the part a person sees
 *  (the legend's access marks: the user's "L b"). */
export type ShapeKind = "sq" | "P" | "B" | "L" | "A" | "pale" | "here" | "clear" | "over" | "fav" | "area" | "measure" | "ends";
/** Another run drawn on the map: its id, name and colour (others.ts colorOf: ShownRun.color). */
export interface LegendRun { id: string; name: string; color: string }
/** A line given by its ends (a measured line: not a row of the run). */
export interface LineEnds { lat1: number; lon1: number; lat2: number; lon2: number }
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
/** The canvas's text, px: R1's smallest, the value of --fs-1 (the pilot of 2026-11-18; the canvas reads no CSS token:
 *  a change of that step changes this constant too). The numbers' shapes keep their sizes (markSize, as before). */
const TEXT_PX = 12;
const MARK_FONT = `600 ${TEXT_PX}px system-ui, sans-serif`;
const HALO = 1.25;  // px the halo of a square's value reaches beyond its letters (half its 2.5 px stroke)
const D = Math.PI / 180;
/** A number is left out when even its farthest place is nearer than this share of a box (32 × 23 px) to a number
 *  placed before it; the numbers of "Lines from here" by the same rule, after the B and P numbers (the user's N1 b
 *  and N2 a at gate 1, 2026-11-20; before: a quarter, the fan's numbers never). tools/view_numbers.py keeps a copy. */
export const APART_MIN = 1 / 3;
const BOX_W = 32, BOX_H = 23;
/** Today's search area (ResultMap.ts): weight 1, dashes 6 (Leaflet's "6": 6 on, 6 off), here in the map's ink. */
const OUTLINE_PX = 1, OUTLINE_DASH = [6, 6];
/** A favourite's halo, the accepted mock-up's numbers (the planner's fix round 1, 2026-11-20): 10 px at 60 %, at 30 %
 *  while a line is selected or "Lines from here" is open; the selected one's gold, 12 px at 80 %, in the dark halo's
 *  place. The gold is today's (style.ts COLORS.favourite: light in both themes). */
const FAV_PX = 10, FAV_ALPHA = 0.6, FAV_DIMMED = 0.3, FAV_SELECTED_PX = 12, FAV_SELECTED = 0.8;
/** Another run's lines: 3 px (the accepted mock-up's), over trees or buildings dashed "6 4", 90 % (ResultMap.ts). */
const OTHER_PX = 3, OTHER_ALPHA = 0.9, OTHER_DASH = [6, 4];
/** A measurement: black dashes "6 4" of 2 px between white points of radius 5 with a black 2 px ring (ResultMap.ts). */
const MEASURE_PX = 2, MEASURE_DASH = [6, 4], MEASURE_R = 5;
/** px a number's shape is cut out of the measurement's dashes beyond its edge (its ring's outer half, 1.2 px for A's
 *  2.4 px ring, and the edge's antialiasing): no pixel of a number's box changes under a measured line. */
const CUT_GROW = 1.5;

/** Unit Web Mercator (0 … 1 each way) of a latitude and a longitude: the canvas's own projection. */
function mercX(lon: number): number { return lon / 360 + 0.5; }
function mercY(lat: number): number { const s = Math.sin(lat * D); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); }

/** A run's area as rings and lines in unit Web Mercator ([x0, y0, x1, y1, …] each), and its box; the GeoJSON of a
 *  run's head (a Polygon or a MultiPolygon; a Feature, a collection or a line too, as Leaflet's geoJSON takes them). */
function areaOf(g: unknown): {rings: Float64Array[]; box: L.LatLngBounds | null} {
  const rings: Float64Array[] = [];
  let box: L.LatLngBounds | null = null;
  const line = (pts: Position[]) => {
    const a = new Float64Array(2 * pts.length);
    pts.forEach((p, k) => {
      a[2 * k] = mercX(p[0]); a[2 * k + 1] = mercY(p[1]);
      const at = L.latLng(p[1], p[0]);
      if (box) box.extend(at); else box = L.latLngBounds(at, at);
    });
    if (pts.length > 1) rings.push(a);
  };
  const walk = (o: any) => {
    switch (o?.type) {
      case "Polygon": case "MultiLineString": (o.coordinates as Position[][]).forEach(line); break;
      case "MultiPolygon": (o.coordinates as Position[][][]).forEach((p) => p.forEach(line)); break;
      case "LineString": line(o.coordinates as Position[]); break;
      case "GeometryCollection": (o.geometries as Geometry[]).forEach(walk); break;
      case "Feature": walk(o.geometry); break;
      case "FeatureCollection": (o.features as any[]).forEach((f) => walk(f?.geometry)); break;
    }
  };
  walk(g);
  return {rings, box};
}

/** An other run as the canvas draws it: its rings, its lines' ends and kinds, which of them pass the filters now. */
interface OtherRunDrawn { id: string; name: string; color: string; rings: Float64Array[]; n: number;
                          lat: ((i: number) => number)[]; lon: ((i: number) => number)[]; over: Uint8Array; ok: Uint8Array }

/** The half width and height of a number's shape. */
export function markSize(kind: MarkKind, text: string): [number, number] {
  return [kind === "P" ? 19 : kind === "L" ? 17.5 : kind === "A" ? 10.5 : text.length > 2 ? 15 : 12.5, kind === "P" ? 13.5 : 10.5];
}

/** A number's shape as a path; `begin` false: added to the path being made as a subpath of its own (a clip), `grow`
 *  px larger each way (its ring's outer half and its edge's antialiasing). */
function shapePath(ctx: CanvasRenderingContext2D, kind: MarkKind, x: number, y: number, text: string, begin = true, grow = 0) {
  const [w0, h0] = markSize(kind, text), w = w0 + grow, h = h0 + grow;
  if (begin) ctx.beginPath();
  if (kind === "P") { ctx.moveTo(x, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x, y + h); ctx.lineTo(x - w, y); ctx.closePath(); }
  else if (kind === "L") {
    ctx.moveTo(x - w + 6, y - h); ctx.lineTo(x + w - 6, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x + w - 6, y + h);
    ctx.lineTo(x - w + 6, y + h); ctx.lineTo(x - w, y); ctx.closePath();
  }
  else if (kind === "A") { ctx.moveTo(x + 10.5 + grow, y); ctx.arc(x, y, 10.5 + grow, 0, 2 * Math.PI); }
  else if (typeof ctx.roundRect === "function") ctx.roundRect(x - w, y - h, 2 * w, 2 * h, 4 + grow);
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

/** Where a square's value goes at Area (the design review's list of step 3c, item 3): `corners` the square's four
 *  corners in px (in order round it), (hw, hh) the half size of the value's box, `boxes` what it keeps PAD px clear
 *  of ([x0, y0, x1, y1] each: the controls over the map, the numbers drawn over the squares). The square's middle
 *  when the box there is clear: the value stands where it always stood, whatever its width; else the first clear
 *  place of eight nearer the square's sides (top, bottom, left, right) and corners (top left, top right, bottom left,
 *  bottom right) with the whole box inside the square (a square of the run's grid looks slightly turned on the web
 *  map: inside its corners' middle two coordinates each way); none: null, the value is left out (the square stays,
 *  its colour tells the value's class). */
export function valueAt(corners: [number, number][], hw: number, hh: number, boxes: number[][]): [number, number] | null {
  const clear = (x: number, y: number) =>
    boxes.every((r) => x + hw <= r[0] - PAD || x - hw >= r[2] + PAD || y + hh <= r[1] - PAD || y - hh >= r[3] + PAD);
  const cx = (corners[0][0] + corners[2][0]) / 2, cy = (corners[0][1] + corners[2][1]) / 2;
  if (clear(cx, cy)) return [cx, cy];
  const xs = corners.map((c) => c[0]).sort((a, b) => a - b), ys = corners.map((c) => c[1]).sort((a, b) => a - b);
  const x0 = xs[1] + hw, x1 = xs[2] - hw, y0 = ys[1] + hh, y1 = ys[2] - hh;
  if (x0 > x1 || y0 > y1) return null;
  const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  for (const [x, y] of [[mx, y0], [mx, y1], [x0, my], [x1, my], [x0, y0], [x1, y0], [x0, y1], [x1, y1]]) if (clear(x, y)) return [x, y];
  return null;
}

function segmentDistance(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const f = len2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - ax - f * dx, py - ay - f * dy);
}

interface Placed { kind: MarkKind; text: string; x: number; y: number; w: number; h: number; spot: number; row: number; end?: 1 | 2 }
/** A square's value at Area as the last paint placed it: its box's middle and half size in the layer's pixels; moved
 *  from the square's middle, or left out (then the box it had in the middle). */
interface Value { text: string; x: number; y: number; w: number; h: number; moved: boolean; left: boolean }
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
  private legendNow: Legend = {level: "area", shapes: {}, by: "spots", breaks: [], runs: []};
  private legendKey = "";
  // step 3c
  private readonly area: {rings: Float64Array[]; box: L.LatLngBounds | null};  // the run's search area
  private otherRuns: OtherRunDrawn[] = [];  // Compare's other runs, as drawn now
  private othersKey = "";                   // what otherRuns was made for
  private otherLayer: {canvas: HTMLCanvasElement; key: string; drew: {id: string; lines: number}[]} | null = null;
  private coveredPx = 0;                    // the frame's box over the map's bottom (setCovered)
  private measuring: ((a: L.LatLng, b: L.LatLng) => void) | null = null;
  private measured: L.LatLng[] = [];        // the measurement's points drawn (0, 1 or 2)
  private readonly measureListeners = new Set<(measuring: boolean) => void>();
  private still: {drag: boolean; dbl: boolean; touch: string} | null = null;  // a phone's map held still: what was on
  private restore: (() => void) | null = null;  // its putting back, when it waits for the press under way to end
  private stillTimer = 0;
  private selectedRow = -1;                 // the selection the measurement last saw
  private drewNow = {halos: 0, outline: false, others: [] as {id: string; lines: number}[]};  // drawn(): what was painted
  // what a press can take, in the layer's pixels of the last full paint: the lines (rank 2 bold: numbered, a pick,
  // the selected line; 1 thin; 0 pale), the numbers' shapes, the fan's lines
  private tx: number[] = [];
  private trow: number[] = [];
  private trank: number[] = [];
  private marks: Placed[] = [];
  private values: Value[] = [];
  private fanLines: {x1: number; y1: number; x2: number; y2: number; row: number}[] = [];
  private strokes = 0;
  private free = {x0: 0, y0: 0, x1: 0, y1: 0, rects: [] as number[][], sig: "", cover: null as number[] | null};
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
    this.area = areaOf(view.model.data.area);
    this.selectedRow = view.selected?.row ?? -1;
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
    // before the frame's own Esc (SpotColumns useEscape, added after this canvas is made): Esc while measuring ends
    // the measuring alone and says so (defaultPrevented), the selection stays
    document.addEventListener("keydown", this.onKey);
    this.unsubscribe = view.subscribe(() => {
      this.selectionMoved();
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
    document.removeEventListener("keydown", this.onKey);
    this.cancelMeasure();
    this.holdStill(false);  // a putting back still to come: now, while the map is there
    this.measureListeners.clear();
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

  /** The part of the map's box a person sees, in the container's pixels: without what `free` says is not seen (a
   *  phone's sheet) and the bottom part the frame covers (setCovered: the desktop's card; the larger of the two). */
  private freeBox(): {left: number; top: number; right: number; bottom: number} {
    const size = this.map.getSize(), p = this.options.free?.() ?? NONE, under = Math.max(0, p.bottom, this.coveredPx);
    const left = Math.min(Math.max(0, p.left), size.x), top = Math.min(Math.max(0, p.top), size.y);
    return {left, top, right: Math.max(left, size.x - Math.max(0, p.right)), bottom: Math.max(top, size.y - under)};
  }

  /** The px of the map's bottom the frame covers with a box of its own (the desktop's profile card: from the map
   *  box's bottom edge up to the card's top; 0: none), not in view as a phone's sheet is not: "in view", the levels
   *  under Auto, Best N and the numbers count only the map above it, a square's value keeps clear of it, and every
   *  move of the map by the canvas keeps it free. A change redraws at once. */
  setCovered(px: number) {
    const next = px > 0 && isFinite(px) ? Math.round(px) : 0;
    if (next === this.coveredPx) return;
    this.coveredPx = next;
    this.refresh();
  }

  /** The px set by setCovered (0 before). */
  get covered(): number { return this.coveredPx; }

  /** A padding of the map with the covered part kept free at the bottom too. */
  private withCovered(p: Padding): Padding {
    return this.coveredPx > p.bottom ? {...p, bottom: this.coveredPx} : p;
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
    // the covered part (setCovered) as a box a square's value keeps clear of (a phone's sheet is not one: as before)
    const size = map.getSize(), under = Math.min(this.coveredPx, size.y);
    const cover = under > 0 ? [off.x, size.y - under + off.y, size.x + off.x, size.y + off.y] : null;
    return {x0: f.left + off.x, y0: f.top + off.y, x1: f.right + off.x, y1: f.bottom + off.y, rects, sig, cover};
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
    this.values = [];
    this.fanLines = [];
    ctx.setTransform(m, 0, 0, m, -min.x * m, -min.y * m);
    ctx.clearRect(min.x, min.y, size.x, size.y);
    ctx.lineCap = "round";
    const shapes: Legend["shapes"] = {}, fan = view.fan, sel = view.selected, dim = sel || fan ? 0.3 : 1;
    const p = new Float64Array(4), over = this.over, f = this.free;
    const counted = new Set<number>();  // the lines stroked, each once (a line may be drawn twice: thin and bold)
    let found: number[] = [];
    const inFan = new Set<number>();
    if (fan) for (const row of fan.rows) if (row.label[0] !== "L") inFan.add(row.row);  // its number is drawn by the fan, once
    const drew = {halos: 0, outline: false, others: [] as {id: string; lines: number}[]};
    const runs: LegendRun[] = [];
    /** Does a segment cross the part of the map a person sees (asked in a full paint: the free box measured then). */
    const seen = (ax: number, ay: number, bx: number, by: number) => clipT(ax, ay, bx, by, f.x0, f.y0, f.x1, f.y1) !== null;

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
      ctx.fillStyle = INK; ctx.font = MARK_FONT; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(text, x, y + 0.5);
      shapes[kind] = true;
      const [w, h] = markSize(kind, text);
      this.marks.push({kind, text, x, y, w, h, spot, row, end});
    };
    const badges: [number, number][] = [];
    /** How far a place lies from the numbers placed before it, in boxes (the larger of its two shares of a box). */
    const apartOf = (x: number, y: number): number => {
      let near = 1e9;
      for (const q of badges) near = Math.min(near, Math.max(Math.abs(q[0] - x) / BOX_W, Math.abs(q[1] - y) / BOX_H));
      return near;
    };
    /** Where the number of a line goes: on the longest piece of the line that is on the map and clear of the
     *  controls, at the first of seven places a box away from every earlier number, else the farthest; nearer than
     *  APART_MIN of a box to an earlier one, or with no free piece: null, no number on the map (the row keeps it).
     *  The place counts as an earlier number's for the next. */
    const placeBadge = (row: number, text: string, kind: MarkKind): [number, number] | null => {
      this.ends(row, p);
      const ax = p[0], ay = p[1], bx = p[2], by = p[3], [hw, hh] = markSize(kind, text);
      const parts = this.freeParts(ax, ay, bx, by, hw, hh);
      if (!parts.length) return null;
      let at: [number, number] | null = null, apart = -1;
      for (let n = 0; n < parts.length && apart < 1; n++) {
        for (const f of [0.5, 0.36, 0.64, 0.24, 0.76, 0.14, 0.86]) {
          if (apart >= 1) break;
          const s = parts[n][0] + (parts[n][1] - parts[n][0]) * f, x = ax + (bx - ax) * s, y = ay + (by - ay) * s;
          const near = apartOf(x, y);
          if (near > apart) { apart = near; at = [x, y]; }
        }
      }
      if (!at || apart < APART_MIN) return null;
      badges.push(at);
      return at;
    };
    /** The number of a line placed (placeBadge) and drawn. */
    const badge = (row: number, text: string, kind: MarkKind, spot: number) => {
      const at = placeBadge(row, text, kind);
      if (at) mark(kind, at[0], at[1], text, spot, row);
    };
    /** Where the number of a row of "Lines from here" would go: near its far end (the lines meet at the point), at
     *  82 % of the longest free piece of its line toward that end; null: no free piece. */
    const fanPlace = (row: FanRow): {kind: MarkKind; x: number; y: number} | null => {
      this.ends(row.row, p);
      const near = row.near === 1 ? 0 : 2, far = 2 - near, kind: MarkKind = row.label[0] === "L" ? "L" : row.label[0] as MarkKind;
      const [hw, hh] = markSize(kind, row.label), parts = this.freeParts(p[near], p[near + 1], p[far], p[far + 1], hw, hh);
      if (!parts.length) return null;
      const s = parts[0][0] + (parts[0][1] - parts[0][0]) * 0.82;
      return {kind, x: p[near] + (p[far] - p[near]) * s, y: p[near + 1] + (p[far + 1] - p[near + 1]) * s};
    };
    /** The numbers of "Lines from here" as drawn, once a paint and after the B and P numbers: each at its one place
     *  (fanPlace), left out when nearer than APART_MIN of a box to a number placed before it (B, P or an earlier row
     *  of the fan: the user's N2 a, the numbers' one rule), else counted as placed for the next. */
    let fanKept: ({kind: MarkKind; x: number; y: number} | null)[] | null = null;
    const fanNumbers = () => {
      if (!fanKept) fanKept = (fan ? fan.rows : []).map((row) => {
        const at = fanPlace(row);
        if (!at || apartOf(at.x, at.y) < APART_MIN) return null;
        badges.push([at.x, at.y]);
        return at;
      });
      return fanKept;
    };
    const shownOf = (spots: ArrayLike<number>) => Array.from(spots, (s) => view.shownOf(s));
    const favourites = view.model.favouritesOn;
    /** Of `lists`, the lines that wear the gold halo: a favourite that is its spot's shown line (B-3), but the
     *  selected line (its halo is the selection's, below). */
    const gold = (lists: ArrayLike<number>[]): number[] => {
      if (!favourites) return [];
      const out = new Set<number>(), own = sel && !fan ? sel.row : -1;
      for (const rows of lists) {
        for (let k = 0; k < rows.length; k++) {
          const row = rows[k];
          if (row !== own && view.isFavourite(row) && view.shownOf(view.spotOf(row)) === row) out.add(row);
        }
      }
      return Array.from(out);
    };
    /** Today's gold halo under `rows`, dimmed with the lines. */
    const halo = (rows: number[]) => {
      if (!rows.length) return;
      stroke(rows, FAV_PX, dim < 1 ? FAV_DIMMED : FAV_ALPHA, COLORS.favourite);
      drew.halos += rows.length;
      if (full && rows.some((row) => { this.ends(row, p); return seen(p[0], p[1], p[2], p[3]); })) shapes.fav = true;
    };
    /** The run's search area (today's thin dashes in the map's ink) and Compare's other runs: each run's area in its
     *  colour, then its lines that pass the filters (over trees or buildings dashed, the clear ones on top), dimmed
     *  with the lines; never counted, never a target. */
    const outlines = () => {
      if (this.area.rings.length) {
        this.traceRings(ctx, this.area.rings);
        ctx.globalAlpha = 1; ctx.lineWidth = OUTLINE_PX; ctx.strokeStyle = INK; ctx.setLineDash(OUTLINE_DASH);
        ctx.stroke(); ctx.setLineDash([]);
        drew.outline = true;
        if (full && this.ringsCross(this.area.rings)) shapes.area = true;
      }
      const runs_ = this.others();
      if (!runs_.length) { this.otherLayer = null; return; }
      // the other runs' picture is kept (a canvas of its own) and copied in on the paints that change none of it (a
      // hover, the flash, the profile's point): their raster is the costly part (every passing line at 2.5 px)
      const key = `${this.othersKey}|${min.x},${min.y},${size.x},${size.y},${m},${dim},${this.scale},${this.ox},${this.oy}`;
      const cache = this.otherLayer;
      if (!full && cache && cache.key === key) {
        drew.others = cache.drew.map((o) => ({...o}));
      } else {
        const layer = cache?.canvas ?? document.createElement("canvas");
        layer.width = ctx.canvas.width; layer.height = ctx.canvas.height;
        const o = layer.getContext("2d")!;
        o.setTransform(m, 0, 0, m, -min.x * m, -min.y * m);
        o.lineCap = "round";
        const counts: {id: string; lines: number}[] = [];
        for (const run of runs_) {
          let inSight = false;
          if (run.rings.length) {
            this.traceRings(o, run.rings);
            o.globalAlpha = 1; o.lineWidth = OUTLINE_PX; o.strokeStyle = run.color; o.setLineDash(OUTLINE_DASH);
            o.stroke();
            inSight = full && this.ringsCross(run.rings);
          }
          o.lineWidth = OTHER_PX; o.globalAlpha = OTHER_ALPHA * dim; o.strokeStyle = run.color;
          let lines = 0;
          for (const kind of [1, 0]) {
            o.setLineDash(kind ? OTHER_DASH : []);
            o.beginPath();
            let n = 0;
            for (let i = 0; i < run.n; i++) {
              if (!run.ok[i] || run.over[i] !== kind) continue;
              this.otherEnds(run, i, p);
              o.moveTo(p[0], p[1]); o.lineTo(p[2], p[3]);
              n++;
              if (full && !inSight) inSight = seen(p[0], p[1], p[2], p[3]);
            }
            if (n) o.stroke();
            lines += n;
          }
          o.setLineDash([]); o.globalAlpha = 1;
          counts.push({id: run.id, lines});
          if (inSight) runs.push({id: run.id, name: run.name, color: run.color});
        }
        this.otherLayer = {canvas: layer, key, drew: counts};
        drew.others = counts.map((c) => ({...c}));
      }
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalAlpha = 1;
      ctx.drawImage(this.otherLayer!.canvas, 0, 0);
      ctx.restore();
    };

    if (level === "area") {
      const grid = timed("fal:view:squares", () => squareValues(view, squareSide(view.mpp), this.by));
      const br = breaks(grid.values, this.by === "spots" || this.by === "lines");
      this.grid = grid;
      found = br;
      const colours = this.layerColours();
      // the numbers drawn over the squares placed first (their places do not depend on the squares): the picks' (drawn
      // after their lines, as ever), the fan's (L …, and a pick's P where the fan draws it) and the selected line's A1
      // and A2 (on its anchors; drawn in their own places below, by the same rules): the squares' values keep clear of
      // them, of every control and of the covered part, and stay under the lines and the numbers
      const picks = view.picks(), lines = picks.map((pick) => pick.row);
      const placed = picks.map((pick) => inFan.has(pick.row) ? null : placeBadge(pick.row, "P" + pick.n, "P"));
      const taken = this.free.rects.slice(), take = (kind: MarkKind, text: string, x: number, y: number) => {
        const [w, h] = markSize(kind, text);
        taken.push([x - w, y - h, x + w, y + h]);
      };
      if (this.free.cover) taken.push(this.free.cover);
      placed.forEach((at, n) => { if (at) take("P", "P" + picks[n].n, at[0], at[1]); });
      if (fan) fanNumbers().forEach((at, k) => { if (at) take(at.kind, fan.rows[k].label, at.x, at.y); });
      if (sel && !fan) {
        this.ends(sel.row, p);
        take("A", "A1", p[0], p[1]);
        take("A", "A2", p[2], p[3]);
      }
      // only the squares on the canvas: their middles against the canvas's box in grid metres (the fit's corners); the
      // fills first, then the outlines over them, then the values (the mock-up's order: the values stay readable)
      const side = grid.side, px = side / view.mpp, label = px >= SQUARE_PX, font = px >= 44 ? TEXT_PX + 1 : TEXT_PX;
      const corners = [this.gridAt(min.x, min.y), this.gridAt(min.x + size.x, min.y), this.gridAt(min.x + size.x, min.y + size.y),
                       this.gridAt(min.x, min.y + size.y)];
      const gx0 = Math.min(...corners.map((c) => c[0])) - side, gx1 = Math.max(...corners.map((c) => c[0])) + side;
      const gy0 = Math.min(...corners.map((c) => c[1])) - side, gy1 = Math.max(...corners.map((c) => c[1])) + side;
      const texts: {text: string; quad: [number, number][]; cls: number}[] = [];
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
        if (label) texts.push({text: String(Math.round(grid.values[k])), quad: [a, bb, c, d], cls});
        drawn++;
      }
      ctx.globalAlpha = 1;
      if (drawn) shapes.sq = true;
      outlines();
      ctx.font = `600 ${font}px system-ui, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (const {text, quad, cls} of texts) {
        const cx = (quad[0][0] + quad[2][0]) / 2, cy = (quad[0][1] + quad[2][1]) / 2;
        const hw = ctx.measureText(text).width / 2 + HALO, hh = font / 2 + HALO, at = valueAt(quad, hw, hh, taken);
        if (at) {
          ctx.lineWidth = 2.5; ctx.globalAlpha = 0.55; ctx.strokeStyle = cls >= 2 ? INK : PAPER; ctx.strokeText(text, at[0], at[1]);
          ctx.globalAlpha = 1; ctx.fillStyle = cls >= 2 ? PAPER : INK; ctx.fillText(text, at[0], at[1]);
        }
        const [x, y] = at ?? [cx, cy];
        this.values.push({text, x, y, w: hw, h: hh, moved: at !== null && (x !== cx || y !== cy), left: at === null});
      }
      ctx.globalAlpha = 1;
      halo(gold([lines]));
      stroke(lines, 7, 0.55 * dim, PAPER);
      stroke(lines, 3.5, dim, undefined, true);
      target(lines, 2);
      placed.forEach((at, n) => { if (at) mark("P", at[0], at[1], "P" + picks[n].n, picks[n].spot, picks[n].row); });
      // the legend lists the pick's shape whenever a pick's line is in view, its number drawn or not: a number left out
      // for want of room took its row out of the legend, the foot shrank, and the number came back, again and again
      // (the user's decision of 2026-11-18; the pick's line is on the map either way)
      if (picks.some((pick) => { this.ends(pick.row, p); return seen(p[0], p[1], p[2], p[3]); })) shapes.P = true;
    } else {
      this.grid = null;
      outlines();
      const all = view.best === "all", refused = v.refused > 0;
      const isBest = new Set<number>(refused ? [] : Array.from(v.best));
      const rest = shownOf(Array.from(v.spots).filter((s) => !isBest.has(s)));
      const thin = level === "lines" && v.thin ? v.thin : null;
      const boldOn = !refused && !(level === "lines" && all), bold = boldOn ? shownOf(v.best) : [];
      halo(gold(thin ? [rest, thin, bold] : [rest, bold]));
      stroke(rest, 1.5, 0.24 * dim, undefined, true);
      target(rest, 0);
      if (rest.length) shapes.pale = true;
      if (thin) {
        stroke(thin, 1, (all ? 0.22 : 0.3) * dim, undefined, true);
        target(thin, 1);
      }
      if (boldOn) {
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
      // a favourite selected: gold in the dark halo's place (today's)
      const favourite = favourites && view.isFavourite(sel.row);
      stroke([sel.row], favourite ? FAV_SELECTED_PX : 11, favourite ? FAV_SELECTED : 0.45, favourite ? COLORS.favourite : "#000");
      stroke([sel.row], 5, 1, undefined, true);
      target([sel.row], 2);
      this.ends(sel.row, p);
      if (favourite) {
        drew.halos++;
        if (full && seen(p[0], p[1], p[2], p[3])) shapes.fav = true;
      }
      // an anchor in the part of the map a person sees: the legend shows the access marks (the user's "L b")
      if ([0, 2].some((k) => p[k] >= f.x0 && p[k] <= f.x1 && p[k + 1] >= f.y0 && p[k + 1] <= f.y1)) shapes.ends = true;
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
      const rows = fan.rows.map((row) => row.row), kept = fanNumbers();
      stroke(rows, 7, 0.5, PAPER);
      stroke(rows, 3.2, 1, undefined, true);
      fan.rows.forEach((row, k) => {
        this.ends(row.row, p);
        this.fanLines.push({x1: p[0], y1: p[1], x2: p[2], y2: p[3], row: row.row});
        const at = kept[k];
        if (at) mark(at.kind, at.x, at.y, row.label, view.spotOf(row.row), row.row);
      });
      // the legend lists the fan's own number (L) whenever such a row's line is in view, drawn or not: the rule may
      // leave every L out, and a legend row that comes and goes moves the foot and the numbers (as the pick's: above)
      if (fan.rows.some((row) => { this.ends(row.row, p); return row.label[0] === "L" && seen(p[0], p[1], p[2], p[3]); })) shapes.L = true;
      const at = this.place(fan.xy[0], fan.xy[1]);
      ctx.beginPath(); ctx.arc(at[0], at[1], Math.max(9, FAN_HERE / view.mpp), 0, 2 * Math.PI);
      ctx.lineWidth = 2; ctx.strokeStyle = INK; ctx.setLineDash([4, 3]); ctx.stroke(); ctx.setLineDash([]);
      shapes.here = true;
    }
    const hover = this.hovered ?? this.mapHovered;
    if (hover !== null && view.passes(hover)) stroke([hover], 7, 0.95);
    // a measurement (today's black dashes between white points) over every line, under the numbers' shapes and the
    // squares' values (PRODUCT.md principle 9: no label is crossed; the design review's F1, the code review's F2): each
    // label the segment crosses (its box grown by CUT_GROW and half the dashes' width; usually none to three) is cut
    // out of the dashes' clip, a clip each, so overlapping labels stay cut, and no clip for a label it misses (a clip
    // per label cost a paint about 3.5 times its time: the second code review's F1); its two points on top, the
    // profile's point above them
    if (this.measured.length) {
      const pts = this.measured.map((at): [number, number] => [mercX(at.lng) * this.scale - this.ox, mercY(at.lat) * this.scale - this.oy]);
      ctx.globalAlpha = 1;
      if (pts.length > 1) {
        ctx.save();
        const [ax, ay] = pts[0], [bx, by] = pts[1], g = CUT_GROW + MEASURE_PX / 2;
        const crosses = (x: number, y: number, w: number, h: number) => clipT(ax, ay, bx, by, x - w - g, y - h - g, x + w + g, y + h + g) !== null;
        for (const k of this.marks) {
          if (!crosses(k.x, k.y, k.w, k.h)) continue;
          ctx.beginPath();
          ctx.rect(min.x, min.y, size.x, size.y);
          shapePath(ctx, k.kind, k.x, k.y, k.text, false, CUT_GROW);
          ctx.clip("evenodd");
        }
        for (const v of this.values) {  // a value's box holds its halo; one left out is not drawn
          if (v.left || !crosses(v.x, v.y, v.w, v.h)) continue;
          ctx.beginPath();
          ctx.rect(min.x, min.y, size.x, size.y);
          ctx.rect(v.x - v.w - CUT_GROW, v.y - v.h - CUT_GROW, 2 * (v.w + CUT_GROW), 2 * (v.h + CUT_GROW));
          ctx.clip("evenodd");
        }
        ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); ctx.lineTo(pts[1][0], pts[1][1]);
        ctx.lineWidth = MEASURE_PX; ctx.strokeStyle = "#000"; ctx.setLineDash(MEASURE_DASH); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();
      }
      for (const [x, y] of pts) {
        ctx.beginPath(); ctx.arc(x, y, MEASURE_R, 0, 2 * Math.PI);
        ctx.fillStyle = PAPER; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = "#000"; ctx.stroke();
      }
      shapes.measure = true;
    }
    if (this.marker) {
      const at = map.latLngToLayerPoint(this.marker);
      ctx.beginPath(); ctx.arc(at.x, at.y, 6, 0, 2 * Math.PI);
      ctx.fillStyle = PAPER; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = "#000"; ctx.stroke();
    }
    ctx.globalAlpha = 1;
    this.drewNow = drew;
    if (!full) return;
    this.strokes = counted.size;
    const legend: Legend = {level, shapes, by: this.by, breaks: found, runs};
    const key = JSON.stringify(legend);
    this.legendNow = legend;
    if (key !== this.legendKey) {
      this.legendKey = key;
      this.listeners.forEach((f) => f());
    }
  }

  /** Rings in unit Web Mercator (areaOf) as one path in the layer's pixels. */
  private traceRings(ctx: CanvasRenderingContext2D, rings: Float64Array[]) {
    const k = this.scale, ox = this.ox, oy = this.oy;
    ctx.beginPath();
    for (const r of rings) {
      ctx.moveTo(r[0] * k - ox, r[1] * k - oy);
      for (let i = 2; i < r.length; i += 2) ctx.lineTo(r[i] * k - ox, r[i + 1] * k - oy);
    }
  }

  /** Does a ring cross the part of the map a person sees (the free box of the last full paint). */
  private ringsCross(rings: Float64Array[]): boolean {
    const k = this.scale, ox = this.ox, oy = this.oy, f = this.free;
    for (const r of rings) {
      for (let i = 2; i < r.length; i += 2) {
        if (clipT(r[i - 2] * k - ox, r[i - 1] * k - oy, r[i] * k - ox, r[i + 1] * k - oy, f.x0, f.y0, f.x1, f.y1)) return true;
      }
    }
    return false;
  }

  /** An other run's line's ends in the layer's pixels, into `out` (x1, y1, x2, y2). */
  private otherEnds(run: OtherRunDrawn, i: number, out: Float64Array) {
    for (let e = 0; e < 2; e++) {
      out[2 * e] = mercX(run.lon[e](i)) * this.scale - this.ox;
      out[2 * e + 1] = mercY(run.lat[e](i)) * this.scale - this.oy;
    }
  }

  /** Compare's other runs as the canvas draws them (ResultModel.others, in its order; their columns:
   *  ResultModel.runColumns): which of their lines are drawn. A line passes by today's filtering of them (both kinds
   *  of lines as shown, the filters with this run's lift, Favourites only; not "Top level only": their spots are not
   *  this run's); of a run with the result view's columns (ShownRun.view) only each spot's shown line is drawn, as
   *  this run's (its first passing line in the spot's order, a passing favourite first: B-3), of another run every
   *  passing line (the planner's (c), 2026-11-20: today's page drew one line per group). Made again only when what
   *  passes or the runs shown changed (the view's version, the favourites, the runs). */
  private others(): OtherRunDrawn[] {
    const model = this.view.model;
    if (!model.others.size) {
      this.otherRuns = [];
      this.othersKey = "";
      return this.otherRuns;
    }
    const f = model.filters, s = model.state, favOnly = f.favOnly && model.favouritesOn;
    const favs = model.favouritesOn ? model.favouriteLines().map((l) => model.indexOf(l)) : null;
    let key = `${this.view.version}|${favs ? favs.join(",") : "-"}`;
    for (const run of model.others.values()) key += `|${run.info.id}:${run.start}:${run.count}:${run.color}:${run.view ? 1 : 0}`;
    if (key === this.othersKey) return this.otherRuns;
    this.othersKey = key;
    const lift = model.data.lift, out: OtherRunDrawn[] = [];
    for (const run of model.others.values()) {
      const cols = model.runColumns(run.info.id);
      if (!cols) continue;
      const n = cols.length, cursor = new LineCursor(cols), over = cols.over;
      let ok = new Uint8Array(n);
      const fav = favs ? new Set(favs.filter((at) => at >= run.start && at < run.start + n).map((at) => at - run.start)) : null;
      for (let i = 0; i < n; i++) {
        if (over[i] ? !s.showOver : !s.showClean) continue;
        cursor.i = i;
        if (!passesFilters(cursor, f, lift)) continue;
        if (favOnly && fav && !fav.has(i)) continue;
        ok[i] = 1;
      }
      const v = run.view;
      if (v && v.spot.length === n && v.bySpot.length === n) {
        // each spot's shown line: a passing favourite, else its first passing line in the spot's order (bySpot)
        let spots = 0;
        for (let i = 0; i < n; i++) if (v.spot[i] >= spots) spots = v.spot[i] + 1;
        const first = new Int32Array(spots).fill(-1), liked = new Int32Array(spots).fill(-1);
        for (let k = 0; k < n; k++) {
          const row = v.bySpot[k];
          if (row >= n || !ok[row]) continue;
          const spot = v.spot[row];
          if (first[spot] < 0) first[spot] = row;
          if (liked[spot] < 0 && fav && fav.has(row)) liked[spot] = row;
        }
        const shown = new Uint8Array(n);
        for (let p = 0; p < spots; p++) {
          const row = liked[p] >= 0 ? liked[p] : first[p];
          if (row >= 0) shown[row] = 1;
        }
        ok = shown;
      }
      out.push({id: run.info.id, name: run.info.name, color: run.color, rings: areaOf(run.area).rings, n, over, ok,
                lat: [reader(cols.lat1), reader(cols.lat2)], lon: [reader(cols.lon1), reader(cols.lon2)]});
    }
    this.otherRuns = out;
    return out;
  }

  /** A layer point in grid metres (through the fit). */
  private gridAt(x: number, y: number): [number, number] {
    const at = this.map.layerPointToLatLng([x, y]);
    return this.view.fit.toGrid(at.lat, at.lng);
  }

  private token(name: string): string {
    return getComputedStyle(this.map.getContainer()).getPropertyValue(name).trim() || "#888";
  }

  /** The accent of what is drawn on the tiles (the flash): the light theme's in both themes, the tiles staying light. */
  private accent(): string { return this.token("--accent-map"); }

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
   *  and the numbers with their boxes in the viewport; at Area the squares' values on the canvas with their boxes
   *  (with the halo), each moved from its square's middle or not, or left out (its box then the one it had there). */
  drawn(): {strokes: number; numbers: {label: string; box: DOMRect}[]; values: {text: string; box: DOMRect; moved: boolean; left: boolean}[];
            halos: number; outline: boolean; others: {id: string; lines: number}[]; measured: {x: number; y: number}[]} {
    const box = this.map.getContainer().getBoundingClientRect();
    const rect = (x: number, y: number, w: number, h: number) => {
      const at = this.map.layerPointToContainerPoint([x, y]);
      return new DOMRect(box.left + at.x - w, box.top + at.y - h, 2 * w, 2 * h);
    };
    // step 3c: the gold halos stroked (the selected favourite's one of them), whether the search area's outline was
    // drawn, each other run's lines stroked, the measurement's points in the viewport
    const d = this.drewNow;
    return {strokes: this.strokes, numbers: this.marks.map((m) => ({label: m.text, box: rect(m.x, m.y, m.w, m.h)})),
            values: this.values.map((v) => ({text: v.text, box: rect(v.x, v.y, v.w, v.h), moved: v.moved, left: v.left})),
            halos: d.halos, outline: d.outline, others: d.others.map((o) => ({...o})),
            measured: this.measured.map((at) => {
              const q = this.map.latLngToContainerPoint(at);
              return {x: box.left + q.x, y: box.top + q.y};
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
    // while measuring a press is a point, whatever lies under it (no hold is timed then: onPointerDown)
    if (this.measuring) { this.swallowClick = false; this.addPoint(e.latlng); return; }
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
    if (this.measuring) return;  // no "Lines from here" while measuring
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
    if (this.measuring || e.pointerType === "mouse" || !e.isPrimary || (e.target as HTMLElement).closest?.(".leaflet-control")) return;
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

  // The line a press would take, under the mouse (thicker); none for the mouse events of a finger, while "Lines
  // from here" is open or while measuring
  private onMouseMove = (e: L.LeafletMouseEvent) => {
    if (this.measuring || this.pressedBy === "touch" || this.view.fan || (e.originalEvent as any)?.sourceCapabilities?.firesTouchEvents) {
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

  private fitOptions(given: Padding, margin: number, maxMpp?: number): L.FitBoundsOptions {
    // What covers the map may leave no room (a phone's sheet at full: the bar's foot stands above the map's top):
    // FIT_ROOM px stay for the fitted thing each way, the paddings give way in their proportion (with none left,
    // Leaflet's fit would ask for the zoom of a negative size). Every move keeps the covered part free too
    // (setCovered), whatever padding the caller gave.
    const size = this.map.getSize(), p = this.withCovered(given);
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

  /** The frame's padding for the canvas's own moves (fitOptions adds the covered part). */
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

  /** Fit the map to a line given by its ends (a measured line, a link's measured line: not a row of the run), `p` px
   *  kept free on each side plus zoomTo's margin, the covered part too; not closer than the run's last zoom.
   *  Default: the frame's padding of the canvas's own moves. */
  zoomToLine(line: LineEnds, p: Padding = this.own()) {
    this.map.fitBounds(L.latLngBounds([line.lat1, line.lon1], [line.lat2, line.lon2]), this.fitOptions(p, 60));
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

  // --- measuring: what RunActions' RunActionsMap needs, as today's ResultMap has it ---

  /** Measure mode is on (from startMeasure to its second point, cancelMeasure, Esc or a change of the selection). */
  get isMeasuring(): boolean {
    return this.measuring !== null;
  }

  /** Call `listener` when measure mode starts (true) or ends (false); returns the function that stops it. */
  onMeasuring(listener: (measuring: boolean) => void): () => void {
    this.measureListeners.add(listener);
    return () => { this.measureListeners.delete(listener); };
  }

  /** Measure mode: the next two presses on the map are the points, given to `done` after the second; a measurement
   *  drawn before goes. While measuring a press selects nothing and opens no "Lines from here", the mouse thickens no
   *  line, the cursor is a crosshair, and a phone's map holds still (holdStill). Esc cancels. */
  startMeasure(done: (a: L.LatLng, b: L.LatLng) => void) {
    this.measured = [];
    this.measuring = done;
    this.selectedRow = this.view.selected?.row ?? -1;
    this.endHold();
    this.setMapHovered(null, false);
    this.map.getContainer().style.cursor = "crosshair";  // the CSSOM, not an attribute (the CSP)
    this.holdStill(true);
    this.measureListeners.forEach((f) => f(true));
    this.paint(true);
  }

  /** Leave measure mode (the points drawn stay until clearMeasure). */
  cancelMeasure() {
    this.endMeasure(false);
  }

  /** Measure mode ends; `later`: a phone's map moves again only once the press that ended it is over (a quick second
   *  tap is a double tap, and its dblclick comes after the click that took the point: it must not zoom). */
  private endMeasure(later: boolean) {
    if (!this.measuring) return;
    this.measuring = null;
    this.map.getContainer().style.cursor = "";
    this.holdStill(false, later);
    this.measureListeners.forEach((f) => f(false));
  }

  /** Remove the points and the line of a measurement (while measuring, the points taken so far too). */
  clearMeasure() {
    if (!this.measured.length) return;
    this.measured = [];
    this.paint(true);
  }

  /** Draw a measured line the frame holds (a link's measured line; the frame's own after the canvas was made again
   *  across the phone's width) as a measurement is drawn, in place of what is drawn. null: nothing drawn (as
   *  clearMeasure). While measuring: null leaves the points taken so far (the frame's "no measured line" may come
   *  after startMeasure: RunActions clears it just before), a line ends measuring and is drawn (it replaces the
   *  measurement under way, whose `done` is not called). */
  drawMeasured(line: LineEnds | null) {
    if (this.measuring) {
      if (!line) return;
      this.cancelMeasure();
    }
    this.measured = line ? [L.latLng(line.lat1, line.lon1), L.latLng(line.lat2, line.lon2)] : [];
    this.paint(true);
  }

  /** The bounds of the run's search area (Compare's box of the run); without an area, the box of its lines. */
  areaBounds(): L.LatLngBounds {
    const area = this.area.box, box = this.view.model.data.box;
    if (area) return L.latLngBounds(area.getSouthWest(), area.getNorthEast());
    if (box) return this.bounds([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]);
    const at = this.view.model.data.center;
    return L.latLngBounds(at, at);
  }

  private addPoint(at: L.LatLng) {
    const done = this.measuring;
    if (!done) return;
    this.measured = this.measured.concat([at]);
    this.paint(true);
    if (this.measured.length < 2) return;
    const [a, b] = this.measured;
    this.endMeasure(true);
    done(a, b);
  }

  /** A change of the selection ends a measurement: while measuring any change cancels it and clears its points
   *  (today's ResultMap.render); a measurement drawn goes when a line is selected, not when the selection ends
   *  (today's useMeasureEnds). Called before the view's change is drawn. */
  private selectionMoved() {
    const row = this.view.selected?.row ?? -1;
    if (row === this.selectedRow) return;
    this.selectedRow = row;
    if (this.measuring) {
      this.cancelMeasure();
      this.measured = [];
    } else if (row >= 0) this.measured = [];
  }

  /** Esc while measuring cancels it and clears its points, and nothing else: the frame's own Esc (the table of spots,
   *  "Lines from here", the selection: SpotColumns useEscape) skips an event already taken. An event taken before
   *  (a menu closed itself) is left alone, as today. */
  private onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || e.defaultPrevented || !this.measuring) return;
    this.cancelMeasure();
    this.clearMeasure();
    e.preventDefault();
  };

  /** A phone's map holds still while measuring (the accepted mock-up: the points are pressed on a map that does not
   *  move): no drag and no double tap's zoom from startMeasure until measuring ends; the zoom buttons and a pinch
   *  still zoom. Leaflet's drag off takes its class `leaflet-touch-drag` and with it `touch-action: none`
   *  (leaflet.css: `pan-x pan-y` then, a swipe the browser's own: a pull to reload, a bounce): the map's box keeps
   *  `touch-action: none` in its own style meanwhile (the CSSOM; the code review's F1). What was on is put back: at
   *  once, or (`later`) after the events of the press now under way. */
  private holdStill(on: boolean, later = false) {
    if (this.restore) {  // a putting back still to come: now
      clearTimeout(this.stillTimer);
      this.restore();
    }
    const map = this.map;
    if (on) {
      if (this.still || !this.options.phone) return;
      const box = map.getContainer();
      this.still = {drag: map.dragging.enabled(), dbl: map.doubleClickZoom.enabled(), touch: box.style.touchAction};
      box.style.touchAction = "none";
      map.dragging.disable();
      map.doubleClickZoom.disable();
    } else if (this.still) {
      const was = this.still;
      this.still = null;
      const restore = () => {
        this.restore = null;
        if (was.drag) map.dragging.enable();
        if (was.dbl) map.doubleClickZoom.enable();
        map.getContainer().style.touchAction = was.touch;
      };
      if (later) {
        this.restore = restore;
        this.stillTimer = window.setTimeout(restore, 0);
      } else restore();
    }
  }
}
