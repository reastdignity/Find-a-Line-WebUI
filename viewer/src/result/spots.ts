// The result view's model of spots (docs/line-volume/spec-view.md B.2, B.3): on a ResultModel built without the
// grouping (ResultOptions.ungrouped), from the three columns and the head's sectors a run's store holds
// (types.ts ViewColumns: the spots, the order inside a spot and the top-level flag are computed at saving,
// mapping.view_columns; nothing is grouped here). It answers, after every change of the filters or the view: which
// lines pass, each spot's shown line (its first passing line), the spots' order, the sectors, the picks of "Start
// here", the lines not beaten, the spots in view and the best of them, the numbers they carry, the selection and
// "Lines from here". The canvas (SpotMap.ts) and the panels (view/Spot*.tsx) draw it. Plain TypeScript without the
// DOM or Leaflet (types only), so tests run it under Node (tests/test_view_units.py).
//
// Rows are indices of this run's lines (ResultModel.lineAt); spots are the stored numbers 0 … S-1; a sector is its
// index from 0 in the head's `sectors` (shown as "Sector n+1"; a spot's label is "<sector+1>.<k>"). Everything that
// goes through every line reads typed arrays (`values`: the store's own float64 arrays where it has them); a Line
// is made only for the selected line.

import type L from "leaflet";
import { NO_FILTERS, passes as passesFilters, type Filters } from "../filters";
import { timed } from "../perf";
import { ACCESS_EASY, hasView, LineCursor, type Line, type NumberColumn, type RunData, type ViewColumns } from "../types";
import type { ResultModel } from "./model";
import { autoLevel, clipper, gridFit, quadArea, reader, BEST_ROWS, FAN_GROUP, FAN_HERE, FAN_MAX, LIMIT, PICK_APART, QUAD_MIN,
         type GridFit, type Level, type Quad } from "./viewgeom";

/** The keys the list of spots sorts by: mean height, clearance, length, highest point (each of the spot's shown
 *  line, highest first), the spot's passing lines. */
export type ViewSort = "hmean" | "clr" | "len" | "hmax" | "n";
export type Best = 10 | 30 | 100 | "all";
/** The picks of "Start here": highest on average, longest with at least 3 m clear, highest above the ground, most
 *  lines in one spot, and "From a top edge" (both anchors read easy access; a run with the access mark). */
export type PickKind = "mean" | "long3" | "high" | "most" | "edge";
/** A pick: its line and spot, and `n` of its number P1 … (the picks in the kept order). */
export interface Pick { kind: PickKind; row: number; spot: number; n: number }
/** A sector's head in the tree: `n` its index from 0 (the head's `sectors[n]`; "Sector n+1"), its word, its spots
 *  with a passing line in `order`, its passing lines, their highest mean height and their shortest and longest. */
export interface SectorRow { n: number; word: string; spots: number[]; lines: number; hmeanMax: number;
                             len: [number, number] }
/** The spots whose shown line crosses the view, in `order`; `best` the first of them (Best; all of them with
 *  "all"); `m` how many are in view; `numbered`: the best carry B1 … (not with All, when refused, above 100 or at
 *  the Area level); `refused`: 0, or the thin lines the Lines level would draw when they are more than LIMIT;
 *  `strokes`: the thin lines of the Lines level counted (drawn unless refused); `thin`: their rows (null: none
 *  drawn: another level, or refused). */
export interface InView { spots: Uint32Array; best: Uint32Array; m: number; numbered: boolean;
                          refused: number; strokes: number; thin: Uint32Array | null }
/** How "Lines from here" sorts its rows (numbered rows stay first): mean height, clearance, length (highest
 *  first), height difference (smallest first), direction (by bearing). */
export type FanSort = "hmean" | "clr" | "len" | "dh" | "dir";
/** A row of "Lines from here": its line (the highest on average of `rows`, the lines whose far ends lie within
 *  FAN_GROUP of it), the label it carries on the map now (B3, P1: a numbered line keeps its number; else L1 …),
 *  the line's end at the point, the height difference from that end to the far end (signed, m) and the direction
 *  to the far end (degrees from true north). */
export interface FanRow { row: number; rows: Uint32Array; label: string; numbered: boolean; near: 1 | 2;
                          dh: number; bearing: number }
/** "Lines from here" at a point: `at` on the map and `xy` in grid metres, its rows (at most FAN_MAX, in `sort`'s
 *  order), how many passing lines start within FAN_HERE of the point (`lines`), to how many far ends (`farEnds`;
 *  `capped`: more than the rows shown). */
export interface Fan { at: L.LatLng; xy: [number, number]; rows: FanRow[]; lines: number; farEnds: number;
                       capped: boolean; sort: FanSort }
/** A spot a press reached, for the table of spots: the line it would select, its label on the map (null: none)
 *  and its distance from the press, px. */
export interface SpotChoice { spot: number; row: number; label: string | null; px: number }
/** The number a spot or a line carries on the map now: B (a best spot in view) or P (a pick, at the Area level),
 *  its number and its line. */
export interface Mark { kind: "B" | "P"; n: number; row: number }
/** The lines' values the view reads at every line, by row, as doubles (NaN: not known). */
export interface ViewValues { x1: Float64Array; y1: Float64Array; x2: Float64Array; y2: Float64Array;
                              len: Float64Array; clr: Float64Array; hmean: Float64Array; hmax: Float64Array }

export interface SpotView {
  /** The run's model, built without the grouping: its lines (lineAt), filters (filters, setFilters, clearFilters,
   *  ranges, state), favourites, profiles, links, other runs and notes are today's. */
  readonly model: ResultModel;
  /** Call `f` after every change of the view or of the model; returns the function that stops it. */
  subscribe(f: () => void): () => void;
  /** The run's lines and spots. */
  readonly count: number; readonly spotCount: number;
  /** A spot's fixed label "<sector+1>.<k>". */
  label(spot: number): string;
  /** A spot's sector, from 0. */
  sectorOf(spot: number): number;
  /** Every line of a spot, in the spot's order (mean height, clearance, length). */
  linesOf(spot: number): Uint32Array;
  // --- filters: the model's own (model.filters, setFilters, clearFilters, state); "Top level only" is the view's
  /** "Top level only" (on at every start, not kept): hides every line whose `top` is 0. */
  readonly topOnly: boolean; setTopOnly(on: boolean): void;
  /** Does a line pass the filters (and "Top level only") now. */
  passes(row: number): boolean;
  /** The spots with a passing line and the passing lines; `hidden` the lines that do not pass; `topHidden` the
   *  lines with `top` 0 among those that pass the other filters (hidden when the chip is on, shown too when it is
   *  off); `total` the run's lines. */
  readonly counts: {spots: number; lines: number; hidden: number; topHidden: number; total: number};
  // --- shown lines and order
  /** A spot's shown line: the user's favourite among its passing lines, else its first passing line; -1: none. */
  shownOf(spot: number): number;
  /** A spot's passing lines in its order (the stepper's "Line k of n"). */
  passingOf(spot: number): Uint32Array;
  /** A spot's passing lines not beaten: in its order, a line is left out when an earlier line kept is at least as
   *  long and at least as clear (so at least as high on average). */
  notBeatenOf(spot: number): Uint32Array;
  sort: ViewSort; setSort(s: ViewSort): void;
  /** The spots with a passing line, by the sort of their shown line (best first; equal: the lower number). */
  readonly order: Uint32Array;
  /** The sectors with a passing line, in the order the tree shows them (by their best spot in `order`). */
  readonly sectors: SectorRow[];
  /** "Start here": the picks over every passing line, numbered P1 … in this order. */
  picks(): Pick[];
  // --- the map's state: written by SpotMap, read by the list
  /** The level drawn; `auto`: it follows the zoom (else it is held). */
  readonly level: Level; readonly auto: boolean; best: Best;
  setLevel(l: Level | "auto"): void; setBest(b: Best): void;
  /** The map's view (the part a person sees, in grid metres) and its metres per pixel, at every full redraw. */
  setView(view: Quad, mpp: number): void;
  readonly inView: InView;
  /** The number a spot carries on the map now (B at Spots and Lines, P of its pick at Area); 0: none. */
  numberOf(spot: number): number;
  // --- selection
  /** The selected spot and its selected line (`line`: the Line of `row`, for the profile and the details). */
  readonly selected: {spot: number; row: number; line: Line} | null;
  /** Select a spot (its shown line, or `row` of it), or nothing; closes "Lines from here". */
  select(spot: number | null, row?: number): void;
  /** The next or the previous passing line of the selected spot; false at the end. */
  step(by: 1 | -1): boolean;
  /** The selected line's place among its spot's passing lines, from 0; -1: nothing selected. */
  readonly selectedIndex: number;
  // --- Lines from here
  readonly fan: Fan | null;
  /** Open "Lines from here" at a point of the map, or at an anchor of a line (`anchor`: its grid place is taken,
   *  `at` is where it is drawn). No passing line within FAN_HERE: nothing changes but `fanMisses`. */
  openFan(at: L.LatLng, anchor?: {row: number; end: 1 | 2}): void;
  closeFan(): void;
  /** One Esc: closes "Lines from here", else ends the selection; false: nothing was open. */
  escape(): boolean;

  // --- added to the plan's interface (section 1) ---
  /** The fit between the run's grid and the map (viewgeom.ts). */
  readonly fit: GridFit;
  /** The lines' values by row. */
  readonly values: ViewValues;
  /** Counts the changes of which lines pass (the filters, "Top level only", the favourites shown). */
  readonly version: number;
  /** The mark of a spot (its number and line) or of a line (only when it is the marked line), else null. */
  markOf(spot: number): Mark | null;
  markOfRow(row: number): Mark | null;
  /** The spot of a line. */
  spotOf(row: number): number;
  /** How many passing lines a spot has. */
  passingCount(spot: number): number;
  /** The metres per pixel of the last view (NaN before the first). */
  readonly mpp: number;
  /** Sort the rows of "Lines from here" (their L numbers follow the order). */
  sortFan(by: FanSort): void;
  /** How often openFan found no line (the map says "No line starts within 10 m of this point."). */
  readonly fanMisses: number;
  /** Stop following the model. */
  destroy(): void;

  // --- added in step 3c ---
  /** Is a line hidden by "Top level only" alone: the chip is on, the line's `top` is 0, and it passes every other
   *  filter (a link to it turns the chip off: the user's "6. a", view/viewlink.ts). */
  topOnlyHides(row: number): boolean;
  /** Is a line of this run one of the user's favourites (while they are known: model.favouritesOn); the canvas's gold
   *  halo (SpotMap.ts) goes under a spot's shown line that is one. */
  isFavourite(row: number): boolean;
}

/** The farthest an anchor may lie from the fit's place of it, m (the planner, 2026-11-16): the fit takes the lowest
 *  degree that keeps within it (viewgeom.ts gridFit); a run no degree fits opens in today's page. The fit places
 *  the view's edge, the squares' corners and the point of "Lines from here" (10 m around it); the lines themselves
 *  are drawn from their own coordinates. */
export const FIT_MAX = 0.5;

/** What the view needs of a run, checked once per run before its model is built (viewOf). */
export interface ViewBase { fit: GridFit; start: Uint32Array; sectorStart: Uint32Array }
const checked = new WeakMap<RunData, ViewBase | string>();

/** Can the result view show this run: its ViewBase, or why not (a text for the console): no columns of the view
 *  (hasView), no lines, columns that are not spots in runs (`by_spot` every row once, the spots' numbers from 0
 *  without a gap, the sectors' spots adding up to them), or a grid the fit does not reach within FIT_MAX. */
export function viewOf(d: RunData): ViewBase | string {
  let found = checked.get(d);
  if (found === undefined) {
    found = check(d);
    checked.set(d, found);
  }
  return found;
}

function check(d: RunData): ViewBase | string {
  if (!hasView(d)) return "the run has no columns of the result view";
  const {spot, bySpot} = d.view as ViewColumns, n = d.columns.length;
  if (!n) return "the run has no lines";
  const seen = new Uint8Array(n), starts: number[] = [];
  let now = -1;
  for (let k = 0; k < n; k++) {
    const row = bySpot[k];
    if (row >= n || seen[row]) return "the view's columns do not hold every line once";
    seen[row] = 1;
    const s = spot[row];
    if (s !== now) {
      if (s !== now + 1) return "the view's columns do not hold the spots in runs";
      now = s;
      starts.push(k);
    }
  }
  starts.push(n);
  // the head against the columns: a store whose head disagrees with them opens today's page, it never throws
  const sectors = d.sectors!;
  if (sectors.some((s) => !s || typeof s.word !== "string" || !Number.isInteger(s.spots) || !(s.spots > 0))) {
    return "the head's sectors are not words with their counts of spots";
  }
  const box = d.box as unknown, lengths = d.lengths as unknown, finite = (v: unknown) => typeof v === "number" && isFinite(v);
  if (!Array.isArray(box) || box.length !== 4 || !box.every(finite)) return "the head's box is not four numbers";
  if (!Array.isArray(lengths) || lengths.length !== 2 || !lengths.every(finite) || lengths[0] > lengths[1]) {
    return "the head's lengths are not the shortest and the longest line";
  }
  const ends = [reader(d.columns.x1), reader(d.columns.y1), reader(d.columns.x2), reader(d.columns.y2)];
  for (let i = 0; i < n; i++) {
    for (let e = 0; e < 4; e += 2) {
      const x = ends[e](i), y = ends[e + 1](i);
      if (x < box[0] - 1e-6 || x > box[2] + 1e-6 || y < box[1] - 1e-6 || y > box[3] + 1e-6) return "the head's box does not hold every anchor";
    }
  }
  const sectorStart = new Uint32Array(sectors.length + 1);
  sectors.forEach((s, k) => { sectorStart[k + 1] = sectorStart[k] + s.spots; });
  if (sectorStart[sectors.length] !== now + 1 || sectors.some((s) => !(s.spots > 0))) {
    return "the head's sectors do not hold the view's spots";
  }
  const fit = gridFit(d.columns, FIT_MAX);
  if (!fit) return "the run's grid could not be fitted to the map";
  const worst = Math.max(fit.residual, fit.back);
  if (!(worst <= FIT_MAX)) {
    return `the run's grid lies up to ${worst.toFixed(2)} m from its fit to the map of degree ${fit.degree} (at most ${FIT_MAX} m)`;
  }
  return {fit, start: Uint32Array.from(starts), sectorStart};
}

/** A column's values as doubles by row: the column's own array when it is float64 with every value there (a
 *  store's unrounded values), else a copy (null, NaN and a missing value as NaN). */
function dense(c: NumberColumn, n: number): Float64Array {
  if (c.values instanceof Float64Array && c.scale === 0 && c.valid === null && c.nulls === null && c.values.length === n) {
    return c.values;
  }
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const v = c.at(i);
    out[i] = typeof v === "number" ? v : NaN;
  }
  return out;
}

/** Highest first, NaN last. */
const down = (a: number, b: number): number => a === b ? 0 : a !== a ? (b !== b ? 0 : 1) : b !== b ? -1 : b - a;

const EMPTY = new Uint32Array(0);
const NO_VIEW: InView = {spots: EMPTY, best: EMPTY, m: 0, numbered: false, refused: 0, strokes: 0, thin: null};
const DEG = Math.PI / 180;

class Spots implements SpotView {
  readonly model: ResultModel;
  readonly fit: GridFit;
  readonly values: ViewValues;
  readonly count: number;
  readonly spotCount: number;
  version = 0;
  topOnly = true;
  sort: ViewSort = "hmean";
  best: Best = 10;
  order: Uint32Array = EMPTY;
  sectors: SectorRow[] = [];
  counts = {spots: 0, lines: 0, hidden: 0, topHidden: 0, total: 0};
  inView: InView = NO_VIEW;
  selected: {spot: number; row: number; line: Line} | null = null;
  fan: Fan | null = null;
  fanMisses = 0;
  mpp = NaN;

  private readonly spot: Uint32Array;
  private readonly top: Uint8Array;
  private readonly bySpot: Uint32Array;
  private readonly start: Uint32Array;        // a spot's run of bySpot: start[s] … start[s + 1] - 1
  private readonly sectorStart: Uint32Array;  // a sector's run of spots
  private readonly sectorAt: Uint16Array;     // a spot's sector
  private readonly ok: Uint8Array;            // 1: the line passes
  private readonly shown: Int32Array;         // a spot's shown line, -1: none passes
  private readonly passing: Uint32Array;      // a spot's passing lines
  private readonly num: Uint16Array;          // a spot's B number in view, 0: none
  private readonly listeners = new Set<() => void>();
  private readonly unfollow: () => void;
  private held: Level | null = null;          // the level held by the user; null: Auto
  private autoNow: Level | null = null;       // the level Auto shows; null before the first view
  private quad: Quad | null = null;
  private picked: Pick[] | null = null;
  private front = new Map<number, Uint32Array>();  // notBeatenOf, per version
  private favourites = new Set<number>();     // the rows of this run's favourites, while they are known
  private favouriteKey = "";
  private fanAnchor: {row: number; end: 1 | 2} | null = null;  // the open fan's anchor (none: its point)
  private fanSorted = false;                                  // the person sorted the open fan
  private fanMarks = "";                                      // marksKey() at the open fan's last derivation
  private away = false;                                       // the last view held no part of the run
  private lastFilters: Filters;
  private lastState: unknown;

  constructor(model: ResultModel, base: ViewBase) {
    const d = model.data, v = d.view as ViewColumns, c = d.columns, n = c.length;
    this.model = model;
    this.fit = base.fit;
    this.count = n;
    this.spot = v.spot; this.top = v.top; this.bySpot = v.bySpot;
    this.start = base.start;
    this.sectorStart = base.sectorStart;
    this.spotCount = base.start.length - 1;
    this.sectorAt = new Uint16Array(this.spotCount);
    for (let s = 0; s + 1 < base.sectorStart.length; s++) this.sectorAt.fill(s, base.sectorStart[s], base.sectorStart[s + 1]);
    this.values = {x1: dense(c.x1, n), y1: dense(c.y1, n), x2: dense(c.x2, n), y2: dense(c.y2, n), len: dense(c.len, n),
                   clr: dense(c.clr, n), hmean: dense(c.hmean, n), hmax: dense(c.hmax, n)};
    this.ok = new Uint8Array(n);
    this.shown = new Int32Array(this.spotCount);
    this.passing = new Uint32Array(this.spotCount);
    this.num = new Uint16Array(this.spotCount);
    this.lastFilters = model.filters;
    this.lastState = model.state;
    this.readFavourites();
    this.recompute();
    this.unfollow = model.subscribe(() => this.follow());
  }

  destroy() {
    this.unfollow();
    this.listeners.clear();
  }

  subscribe(f: () => void): () => void {
    this.listeners.add(f);
    return () => { this.listeners.delete(f); };
  }

  private notify() {
    this.listeners.forEach((f) => f());
  }

  /** The model changed: its filters, the lines shown or the favourites give the passing lines again; anything else
   *  (a note, a profile) is only passed on. */
  private follow() {
    const m = this.model, favourites = this.readFavourites();
    if (m.filters !== this.lastFilters || m.state !== this.lastState || favourites) {
      // a change of the favourites alone keeps "Lines from here" (no filter changed); with "Favourites only" on
      // the favourites are the passing lines: the fan then stays only when the same lines pass as before (a
      // favourite of a line that another filter hides changes nothing)
      const keep = m.filters === this.lastFilters && m.state === this.lastState ? this.fan : null;
      const passed = keep && m.filters.favOnly ? this.ok.slice() : null;
      this.lastFilters = m.filters;
      this.lastState = m.state;
      this.recompute();
      if (keep && (!passed || passed.every((p, i) => p === this.ok[i]))) {
        this.fan = keep;
        this.refan();
      }
    }
    this.notify();
  }

  /** The rows of this run's favourites again; true when they changed. */
  private readFavourites(): boolean {
    const m = this.model, rows: number[] = [];
    if (m.favouritesOn) {
      for (const l of m.favouriteLines()) {
        const at = m.indexOf(l);
        if (at >= 0 && at < this.count) rows.push(at);
      }
    }
    const key = rows.join(",");
    if (key === this.favouriteKey) return false;
    this.favouriteKey = key;
    this.favourites = new Set(rows);
    return true;
  }

  // --- spots ---

  label(spot: number): string {
    const s = this.sectorAt[spot];
    return `${s + 1}.${spot - this.sectorStart[s] + 1}`;
  }

  sectorOf(spot: number): number { return this.sectorAt[spot]; }
  spotOf(row: number): number { return this.spot[row]; }
  linesOf(spot: number): Uint32Array { return this.bySpot.subarray(this.start[spot], this.start[spot + 1]); }
  passes(row: number): boolean { return this.ok[row] === 1; }
  shownOf(spot: number): number { return this.shown[spot]; }
  passingCount(spot: number): number { return this.passing[spot]; }

  passingOf(spot: number): Uint32Array {
    const rows = this.linesOf(spot), out = new Uint32Array(this.passing[spot]);
    let n = 0;
    for (let k = 0; k < rows.length; k++) if (this.ok[rows[k]]) out[n++] = rows[k];
    return out;
  }

  notBeatenOf(spot: number): Uint32Array {
    let kept = this.front.get(spot);
    if (!kept) {
      const rows = this.linesOf(spot), {len, clr} = this.values, out: number[] = [];
      for (let k = 0; k < rows.length; k++) {
        const row = rows[k];
        if (!this.ok[row]) continue;
        let beaten = false;
        for (let j = 0; j < out.length && !beaten; j++) beaten = len[out[j]] >= len[row] && clr[out[j]] >= clr[row];
        if (!beaten) out.push(row);
      }
      kept = Uint32Array.from(out);
      this.front.set(spot, kept);
    }
    return kept;
  }

  // --- what passes, what is shown, the order ---

  setTopOnly(on: boolean) {
    if (on === this.topOnly) return;
    this.topOnly = on;
    this.recompute();
    this.notify();
  }

  setSort(s: ViewSort) {
    if (s === this.sort) return;
    this.sort = s;
    timed("fal:view:order", () => this.reorder());
    this.picked = null;
    this.look();  // the spots in view follow the order; "Lines from here" stays
    this.notify();
  }

  /** Everything that follows from the filters: which lines pass, each spot's shown line, the order, the sectors;
   *  the picks and the lines not beaten when they are asked for. The selection stays on a line that still passes,
   *  "Lines from here" closes. */
  private recompute() {
    timed("fal:view:pass", () => this.pass(), {count: this.count});
    timed("fal:view:shown", () => this.show(), {count: this.spotCount});
    timed("fal:view:order", () => this.reorder());
    this.version++;
    this.front = new Map();
    this.picked = null;
    this.fan = null;
    const sel = this.selected;
    if (sel && this.shown[sel.spot] < 0) this.selected = null;
    else if (sel && !this.ok[sel.row]) this.selected = this.selection(sel.spot, this.shown[sel.spot]);
    this.look();
  }

  private pass() {
    const m = this.model, f = m.filters, s = m.state, lift = m.data.lift, c = m.data.columns, over = c.over;
    const ok = this.ok, top = this.top, topOnly = this.topOnly, n = this.count;
    // passes() reads every filter but these two (the group size has no meaning here: the spots are fixed)
    const none = (Object.keys(NO_FILTERS) as (keyof Filters)[])
      .every((k) => k === "groupMin" || k === "favOnly" || f[k] === NO_FILTERS[k]);
    const favOnly = f.favOnly && m.favouritesOn, favourites = this.favourites, cursor = new LineCursor(c);
    let lines = 0, topHidden = 0;
    for (let i = 0; i < n; i++) {
      let p = over[i] ? s.showOver : s.showClean;
      if (p && !none) { cursor.i = i; p = passesFilters(cursor, f, lift); }
      if (p && favOnly) p = favourites.has(i);
      if (p && top[i] === 0) { topHidden++; if (topOnly) p = false; }
      ok[i] = p ? 1 : 0;
      if (p) lines++;
    }
    this.counts = {spots: 0, lines, hidden: n - lines, topHidden, total: n};
  }

  private show() {
    const {ok, bySpot, start, shown, passing, favourites} = this, S = this.spotCount;
    let spots = 0;
    for (let p = 0; p < S; p++) {
      let first = -1, favourite = -1, c = 0;
      for (let k = start[p]; k < start[p + 1]; k++) {
        const row = bySpot[k];
        if (!ok[row]) continue;
        c++;
        if (first < 0) first = row;
        if (favourite < 0 && favourites.size && favourites.has(row)) favourite = row;
      }
      shown[p] = favourite >= 0 ? favourite : first;
      passing[p] = c;
      if (c) spots++;
    }
    this.counts.spots = spots;
  }

  private reorder() {
    const {shown, passing, values, sort} = this, S = this.spotCount;
    const of = sort === "n" ? null : values[sort], value = new Float64Array(S);
    const order = new Uint32Array(this.counts.spots);
    let n = 0;
    for (let p = 0; p < S; p++) {
      if (shown[p] < 0) continue;
      value[p] = of ? of[shown[p]] : passing[p];
      order[n++] = p;
    }
    order.sort((a, b) => down(value[a], value[b]) || a - b);
    this.order = order;
    // the sectors in the order of their best spot, each with its spots in the order and its passing lines' values
    const heads = (this.model.data.sectors || []).map((s, k): SectorRow & {first: number} =>
      ({n: k, word: s.word, spots: [], lines: 0, hmeanMax: NaN, len: [NaN, NaN], first: -1}));
    for (let r = 0; r < order.length; r++) {
      const p = order[r], head = heads[this.sectorAt[p]];
      if (head.first < 0) head.first = r;
      head.spots.push(p);
      head.lines += passing[p];
    }
    const {ok, bySpot, start, sectorStart} = this, {hmean, len} = values;
    for (const head of heads) {
      if (head.first < 0) continue;
      let high = -Infinity, short = Infinity, long = -Infinity;
      for (let k = start[sectorStart[head.n]]; k < start[sectorStart[head.n + 1]]; k++) {
        const row = bySpot[k];
        if (!ok[row]) continue;
        if (hmean[row] > high) high = hmean[row];
        if (len[row] < short) short = len[row];
        if (len[row] > long) long = len[row];
      }
      head.hmeanMax = high > -Infinity ? high : NaN;
      head.len = [short, long];
    }
    this.sectors = heads.filter((h) => h.first >= 0).sort((a, b) => a.first - b.first)
      .map(({first: _, ...head}) => head);
  }

  picks(): Pick[] {
    if (!this.picked) this.picked = timed("fal:view:picks", () => this.pick());
    return this.picked;
  }

  private pick(): Pick[] {
    const {ok, values: {hmean, clr, len, hmax, x1, y1, x2, y2}, spot, shown, passing} = this, n = this.count;
    const c = this.model.data.columns, marked = this.model.hasAccess;
    let mean = -1, long3 = -1, high = -1, edge = -1;
    for (let i = 0; i < n; i++) {
      if (!ok[i]) continue;
      if (hmean[i] === hmean[i] && (mean < 0 || hmean[i] > hmean[mean])) mean = i;
      if (clr[i] >= 3 && (long3 < 0 || len[i] > len[long3])) long3 = i;
      if (hmax[i] === hmax[i] && (high < 0 || hmax[i] > hmax[high])) high = i;
      if (marked && hmean[i] === hmean[i] && (edge < 0 || hmean[i] > hmean[edge]) &&
          c.access1.at(i) === ACCESS_EASY && c.access2.at(i) === ACCESS_EASY) edge = i;
    }
    let most = -1;
    for (let p = 0; p < this.spotCount; p++) if (passing[p] && (most < 0 || passing[p] > passing[most])) most = p;
    const out: Pick[] = [];
    const midX = (i: number) => (x1[i] + x2[i]) / 2, midY = (i: number) => (y1[i] + y2[i]) / 2;
    const kinds: PickKind[] = ["mean", "long3", "high", "most"];
    [mean, long3, high, most < 0 ? -1 : shown[most]].forEach((row, k) => {
      if (row < 0) return;
      const far = out.every((o) => o.spot !== spot[row] &&
                                   Math.hypot(midX(o.row) - midX(row), midY(o.row) - midY(row)) >= PICK_APART);
      if (far) out.push({kind: kinds[k], row, spot: spot[row], n: out.length + 1});
    });
    // "From a top edge" comes last, also near an earlier pick; left out only when it is an earlier pick's line
    if (edge >= 0 && out.every((o) => o.row !== edge)) out.push({kind: "edge", row: edge, spot: spot[edge], n: out.length + 1});
    return out;
  }

  // --- the map's state ---

  get level(): Level { return this.held ?? this.autoNow ?? "area"; }
  get auto(): boolean { return this.held === null; }

  setLevel(l: Level | "auto") {
    if (l === "auto") {
      this.held = null;
      this.autoNow = this.mpp === this.mpp ? autoLevel(this.mpp, null) : null;  // from the zoom at once
    } else this.held = l;
    this.look();
    this.notify();
  }

  setBest(b: Best) {
    if (b === this.best) return;
    this.best = b;
    this.look();
    this.notify();
  }

  setView(view: Quad, mpp: number) {
    const was = this.quad;
    if (was && mpp === this.mpp && was.every((p, k) => p[0] === view[k][0] && p[1] === view[k][1])) return;
    this.quad = view;
    this.mpp = mpp;
    this.autoNow = autoLevel(mpp, this.autoNow);
    this.look();
    this.notify();
  }

  /** The spots in view, the best of them, their numbers and the thin lines of the Lines level, again. */
  private look() {
    if (!this.quad) return;
    this.inView = timed("fal:view:inview", () => this.seen(this.quad!));
    this.refan();
  }

  /** The numbers a line can carry on the map now, as one text: at Area the picks (they follow what passes), else
   *  the best spots in view by their numbers. */
  private marksKey(): string {
    if (this.level === "area") return `P${this.version}`;
    const v = this.inView;
    return v.numbered ? `B${this.version}:${v.best.join()}` : "-";
  }

  /** The view may have changed the numbers on the map (a move, a zoom, Best, the list's sort): when the numbers a
   *  row of the open fan could carry are others than at its last derivation (marksKey), the fan is derived again
   *  in full for its point or anchor: which of its lines carry a number now, their order, their rows, the L
   *  numbers (B.2 item 11: "a line that is a B or P line now"); the person's sort of it is kept. A move that
   *  changes no number costs nothing, and nothing is derived while the map shows no part of the run (the fan is
   *  not seen; it follows when the run is in view again). The Fan stays the same object: the canvas moves the map
   *  only for a fan newly opened. Timed as "fal:view:refan". */
  private refan() {
    const fan = this.fan;
    if (!fan || this.away) return;
    const key = this.marksKey();
    if (key === this.fanMarks) return;
    this.fanMarks = key;
    timed("fal:view:refan", () => {
      const next = this.fanAt(fan.at, this.fanAnchor ?? undefined);
      if (next) {
        Object.assign(fan, next, {sort: fan.sort});
        if (this.fanSorted) this.sortRows(fan);
      }
      this.relabel();
    }, {count: this.count});
  }

  private seen(quad: Quad): InView {
    this.away = quadArea(quad) < QUAD_MIN;
    if (this.away) {  // the map's view lies off the run: nothing is in view, and no line is asked
      this.num.fill(0);
      return {...NO_VIEW};
    }
    const cross = clipper(quad), {order, shown, num, ok} = this, {x1, y1, x2, y2} = this.values;
    const inside = (row: number) => cross(x1[row], y1[row], x2[row], y2[row]);
    const spots = new Uint32Array(order.length);
    let m = 0;
    for (let k = 0; k < order.length; k++) if (inside(shown[order[k]])) spots[m++] = order[k];
    const all = this.best === "all", level = this.level;
    const best = spots.subarray(0, all ? m : Math.min(this.best as number, m));
    let thin: Uint32Array | null = null, strokes = 0, refused = 0;
    if (level === "lines") {
      const rows: number[] = [];
      if (all) {
        for (let i = 0; i < this.count; i++) {
          if (!ok[i] || !inside(i)) continue;
          if (++strokes <= LIMIT) rows.push(i);
        }
      } else {
        for (let k = 0; k < best.length; k++) {
          const kept = this.notBeatenOf(best[k]);
          for (let j = 0; j < kept.length; j++) {
            if (!inside(kept[j])) continue;
            if (++strokes <= LIMIT) rows.push(kept[j]);
          }
        }
      }
      if (strokes > LIMIT) refused = strokes; else thin = Uint32Array.from(rows);
    }
    const numbered = level !== "area" && !all && !refused && best.length <= BEST_ROWS;
    num.fill(0);
    if (numbered) for (let r = 0; r < best.length; r++) num[best[r]] = r + 1;
    return {spots: spots.subarray(0, m), best, m, numbered, refused, strokes, thin};
  }

  markOf(spot: number): Mark | null {
    if (this.level === "area") {
      const pick = this.picks().find((p) => p.spot === spot);
      return pick ? {kind: "P", n: pick.n, row: pick.row} : null;
    }
    const n = this.num[spot];
    return n ? {kind: "B", n, row: this.shown[spot]} : null;
  }

  markOfRow(row: number): Mark | null {
    if (this.level === "area") {
      const pick = this.picks().find((p) => p.row === row);
      return pick ? {kind: "P", n: pick.n, row} : null;
    }
    const mark = this.markOf(this.spot[row]);
    return mark && mark.row === row ? mark : null;
  }

  numberOf(spot: number): number {
    return this.markOf(spot)?.n ?? 0;
  }

  // --- selection ---

  private selection(spot: number, row: number): {spot: number; row: number; line: Line} {
    return {spot, row, line: this.model.lineAt(row)};
  }

  select(spot: number | null, row?: number) {
    if (spot === null) {
      if (!this.selected && !this.fan) return;
      this.selected = null;
      this.fan = null;
      this.notify();
      return;
    }
    if (!(spot >= 0 && spot < this.spotCount) || this.shown[spot] < 0) return;
    const of = row !== undefined && this.ok[row] === 1 && this.spot[row] === spot ? row : this.shown[spot];
    this.selected = this.selection(spot, of);
    this.fan = null;
    this.model.profileClosed = false;
    this.notify();
  }

  get selectedIndex(): number {
    const sel = this.selected;
    return sel ? this.passingOf(sel.spot).indexOf(sel.row) : -1;
  }

  step(by: 1 | -1): boolean {
    const sel = this.selected;
    if (!sel) return false;
    const rows = this.passingOf(sel.spot), k = rows.indexOf(sel.row) + by;
    if (k < 0 || k >= rows.length) return false;
    this.selected = this.selection(sel.spot, rows[k]);
    this.model.profileClosed = false;
    this.notify();
    return true;
  }

  // --- Lines from here ---

  openFan(at: L.LatLng, anchor?: {row: number; end: 1 | 2}) {
    const fan = timed("fal:view:fan", () => this.fanAt(at, anchor), {count: this.count});
    if (!fan) {
      this.fanMisses++;
      return;
    }
    this.fan = fan;
    this.fanAnchor = anchor ?? null;
    this.fanSorted = false;
    this.fanMarks = this.marksKey();
    this.relabel();
    this.notify();
  }

  private fanAt(at: L.LatLng, anchor?: {row: number; end: 1 | 2}): Fan | null {
    const {x1, y1, x2, y2, hmean} = this.values, {ok, spot} = this, n = this.count, c = this.model.data.columns;
    const xy: [number, number] = anchor ? (anchor.end === 1 ? [x1[anchor.row], y1[anchor.row]] : [x2[anchor.row], y2[anchor.row]])
      : this.fit.toGrid(at.lat, at.lng);
    const [x, y] = xy, reach2 = FAN_HERE * FAN_HERE;
    const found: {row: number; near: 1 | 2; d: number}[] = [];
    for (let i = 0; i < n; i++) {
      if (!ok[i]) continue;
      const d1 = (x1[i] - x) * (x1[i] - x) + (y1[i] - y) * (y1[i] - y), d2 = (x2[i] - x) * (x2[i] - x) + (y2[i] - y) * (y2[i] - y);
      if (d1 <= reach2 || d2 <= reach2) found.push({row: i, near: d1 <= d2 ? 1 : 2, d: Math.sqrt(Math.min(d1, d2))});
    }
    if (!found.length) return null;
    found.sort((a, b) => down(hmean[a.row], hmean[b.row]) || a.row - b.row);
    const groups: {row: number; rows: number[]; near: 1 | 2; fx: number; fy: number; numbered: boolean}[] = [];
    const group = (l: {row: number; near: 1 | 2}, numbered: boolean) => {
      const i = l.row, fx = l.near === 1 ? x2[i] : x1[i], fy = l.near === 1 ? y2[i] : y1[i];
      if (!numbered) {
        for (const g of groups) {
          if (Math.hypot(g.fx - fx, g.fy - fy) <= FAN_GROUP) { g.rows.push(i); return; }
        }
      }
      groups.push({row: i, rows: [i], near: l.near, fx, fy, numbered});
    };
    // a line that carries a number on the map now and starts here comes first, under that number: the one that
    // starts nearest to the point first, then the lower number
    const seeded = new Set<number>();
    found.filter((l) => this.markOfRow(l.row) !== null)
      .sort((a, b) => Math.round(a.d) - Math.round(b.d) || this.markOfRow(a.row)!.n - this.markOfRow(b.row)!.n)
      .forEach((l) => { seeded.add(l.row); group(l, true); });
    for (const l of found) if (!seeded.has(l.row)) group(l, false);
    const rows = groups.slice(0, FAN_MAX).map((g): FanRow => {
      const i = g.row, near = g.near;
      const lat = [c.lat1.at(i)!, c.lat2.at(i)!], lon = [c.lon1.at(i)!, c.lon2.at(i)!], e = [c.e1.at(i)!, c.e2.at(i)!];
      const a = near - 1, b = 1 - a;  // the near and the far end
      const east = (lon[b] - lon[a]) * Math.cos((lat[a] + lat[b]) / 2 * DEG), north = lat[b] - lat[a];
      return {row: i, rows: Uint32Array.from(g.rows), label: "", numbered: g.numbered, near, dh: e[b] - e[a],
              bearing: (Math.atan2(east, north) / DEG + 360) % 360};
    });
    return {at, xy, rows, lines: found.length, farEnds: groups.length, capped: groups.length > rows.length, sort: "hmean"};
  }

  /** The labels of the rows of "Lines from here" as the map numbers its lines now: a line that carries a number
   *  keeps it, the others are L1, L2 … in the rows' order. */
  private relabel() {
    if (!this.fan) return;
    let n = 0;
    for (const row of this.fan.rows) {
      const mark = this.markOfRow(row.row);
      row.label = mark ? mark.kind + mark.n : "L" + (++n);
    }
  }

  sortFan(by: FanSort) {
    const fan = this.fan;
    if (!fan) return;
    fan.sort = by;
    this.fanSorted = true;
    this.sortRows(fan);
    this.relabel();
    this.notify();
  }

  /** A fan's rows by its sort, the numbered rows first. */
  private sortRows(fan: Fan) {
    const {hmean, clr, len} = this.values, by = fan.sort;
    fan.rows.sort((a, b) => (+b.numbered - +a.numbered) ||
      (by === "len" ? down(len[a.row], len[b.row]) : by === "clr" ? down(clr[a.row], clr[b.row])
        : by === "dh" ? Math.abs(a.dh) - Math.abs(b.dh) : by === "dir" ? a.bearing - b.bearing
          : down(hmean[a.row], hmean[b.row])));
  }

  closeFan() {
    if (!this.fan) return;
    this.fan = null;
    this.notify();
  }

  escape(): boolean {
    if (this.fan) { this.closeFan(); return true; }
    if (this.selected) { this.select(null); return true; }
    return false;
  }

  // --- links ---

  topOnlyHides(row: number): boolean {
    if (!this.topOnly || !(row >= 0 && row < this.count) || this.top[row] !== 0) return false;
    // the other filters as pass() reads them, for this one line
    const m = this.model, f = m.filters, s = m.state, c = m.data.columns;
    const none = (Object.keys(NO_FILTERS) as (keyof Filters)[])
      .every((k) => k === "groupMin" || k === "favOnly" || f[k] === NO_FILTERS[k]);
    let p = c.over[row] ? s.showOver : s.showClean;
    if (p && !none) {
      const cursor = new LineCursor(c);
      cursor.i = row;
      p = passesFilters(cursor, f, m.data.lift);
    }
    if (p && f.favOnly && m.favouritesOn) p = this.favourites.has(row);
    return p;
  }

  isFavourite(row: number): boolean {
    return this.favourites.has(row);
  }
}

/** The result view's model of a run: `model` built with ResultOptions.ungrouped on a run that viewOf accepts
 *  (it throws the reason otherwise: the caller asks viewOf before it builds the model). */
export function createSpotView(model: ResultModel): SpotView {
  const base = viewOf(model.data);
  if (typeof base === "string") throw new Error(base);
  return new Spots(model, base);
}
