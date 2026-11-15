// The result of a run without its UI: lines, filters, groups, the list's rows and order, the chosen
// line of each group, favourites, the selection, other runs shown with it, links to lines and
// profiles: filters first, then the grouping, then the group size. The app's shells and a run's map.html
// draw it with ResultMap and their own panels. Plain TypeScript (no DOM but fetch), so tests run it
// under Node.
//
// The lines are columns (types.ts lineColumns: this run's and each other run's), known by their index among the
// runs shown (`lineAt`): the filters, the grouping, the ranges and the counts read the columns through a LineCursor,
// and the spots (LineGroup) hold indices. A Line object is made (lineAt) only for a line drawn, listed, selected,
// opened, compared or saved as a favourite: a spot's shown line, the members of a spot asked for (the selected
// spot's, an unfolded row's), a link's line, the favourites. It is kept while it is in use, so the same index gives
// the same object (the selection, the choices and the views compare them); after a change of the groups the made
// lines are dropped when they are many more than the rows (prune).

import { dh, drop, lowerAnchor, needClass, NO_FILTERS, passes, prominence, Ranger, saveFilters, savedFilters,
         upperAnchor, wallAngle, type FilterRanges, type Filters, type LinesState, type Range } from "../filters";
import { groupIndices, type Group, type GroupInput } from "../grouping";
import { detailMessage } from "../i18n";
import { addFolder, loadRunFavourites, moveFavourite, saveFavourite, type FavouriteFolder,
         type RunFavourites } from "../favourites";
import { FolderTree } from "../folders";
import { lineCoords, lineKey, runLineKey } from "../keys";
import { hasSavedList, saveList, savedList, sortKey, sortRows, type ListState, type Row } from "../list";
import { colorOf, localPlane } from "../others";
import { nextPaint } from "../paint";
import { timed } from "../perf";
import { lineAt, lineColumns, LineCursor, runData, type Line, type LineColumns, type LineValues, type OtherRun,
         type Profile, type RunData, type RunInfo, type RunLines, type RunScript } from "../types";
import type { OnProgress } from "./load";
import { measuredLine } from "./measured";

export { measuredLine };

export type { Filters, Group, LinesState, ListState, FilterRanges };
export { NO_FILTERS };

/** A spot of the model (one line without grouping): its lines by their index among the runs shown (ResultModel.lineAt),
 *  flat[start] .. flat[end - 1] of the grouping's array, in the grouping's order. Its Line objects are made only when
 *  asked for: `rep`, and `members` (every one: a spot drawn with its lines, unfolded in the list or selected). */
export class LineGroup implements Group<Line> {
  constructor(private readonly model: ResultModel, readonly flat: Int32Array, readonly start: number,
              readonly end: number, readonly repAt: number, readonly over: boolean) {}

  /** How many lines the spot holds. */
  get size(): number { return this.end - this.start; }
  /** Its representative (the grouping's best line). */
  get rep(): Line { return this.model.lineAt(this.repAt); }
  /** Its lines in the grouping's order, as Lines (one made for each). */
  get members(): Line[] { return this.model.linesOf(this); }
  /** Does it hold the line of index `at`. */
  has(at: number): boolean {
    for (let k = this.start; k < this.end; k++) if (this.flat[k] === at) return true;
    return false;
  }
}

/** A row of the list: a group (one line without grouping) and the line shown for it. */
export type Spot = Row & {group: LineGroup};

/** A message for the user above the results (a link to a line, an error), with an optional action. */
export interface Note {
  text: string;
  action?: string;
  onAction?(): void;
}

/** Another run shown with this one (in its colour): its area, and its lines: `count` of them, from index `start`
 *  among the runs shown (ResultModel.lineAt). */
export interface ShownRun {
  info: RunInfo;
  color: string;
  crs: string;
  area: RunLines["area"];
  start: number;
  count: number;
}

/** A run's lines among the runs shown: the indices start .. start + cols.length - 1. */
interface Table {
  cols: LineColumns;
  start: number;
  run?: OtherRun;  // another run's
}

/** The made lines are kept, however many more they are than the rows, up to this many (prune). */
const PRUNE_MIN = 50_000;

/** What the model asks the server; replaced in tests. */
export interface ResultApi {
  /** The user's favourites of a run with their folders (the lines alone: no folders known). */
  loadFavourites(runId: string): Promise<RunFavourites | string[]>;
  saveFavourite(runId: string, line: Line, on: boolean, folder?: number | null): Promise<void>;
  moveFavourite?(runId: string, line: string, folder: number | null): Promise<void>;
  addFolder?(name: string, parent: number | null): Promise<number>;
  /** The terrain profile of `line` ("lat1,lon1,lat2,lon2") of a run, computed by the server. */
  profile(runId: string, line: string): Promise<Profile>;
}

/** web.py /api/profile, with the header it wants. */
export async function fetchProfile(runId: string, line: string): Promise<Profile> {
  const response = await fetch("/api/profile?run=" + encodeURIComponent(runId) + "&line=" + line,
                               {headers: {"X-Findaline-Profile": "1"}});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailMessage(body.detail, response.statusText || "error"));
  return body as Profile;
}

export const SERVER_API: ResultApi = {
  loadFavourites: loadRunFavourites, saveFavourite: (runId, l, on, folder) => saveFavourite(runId, l, on, undefined, folder),
  moveFavourite: (runId, line, folder) => moveFavourite(runId, line, folder), addFolder: (name, parent) => addFolder(name, parent),
  profile: fetchProfile};

const LAST_FOLDER = "findaline.lastFolder";  // the folder a new favourite goes to: this browser's convenience

export interface ResultOptions {
  /** Load and mark the user's favourites (default: FINDALINE_APP.favourites, else from a server). */
  favourites?: boolean;
  /** May the server compute profiles and measure (default: FINDALINE_APP.profiles, else from a server). */
  profiles?: boolean;
  api?: ResultApi;
  /** The list's sorting while the user has kept no choice of their own (default: list.ts LIST_DEFAULTS);
   *  not saved until the user changes the list. */
  list?: Partial<ListState>;
}

/** "Show per spot" (LinesState.by) of the highest line on average: the spots are the run's grouping (`data.by`),
 *  a spot shows its line with the highest mean height and orders its lines so (byMean). The other choices
 *  ("clearance", "longest", "height") group by that rank and show the group's representative first. */
export const BY_MEAN = "mean";

const known = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** A spot's order of its lines under BY_MEAN, best first: the highest mean height (not known: last), then the
 *  most clearance, the longest, then the line's row in its run (`row`). */
export function byMean<T extends Pick<LineValues, "hmean" | "clr" | "len">>(row: (l: T) => number) {
  return (a: T, b: T): number => {
    const ka = known(a.hmean), kb = known(b.hmean);
    if (ka !== kb) return ka ? -1 : 1;
    return (ka ? b.hmean - a.hmean : 0) || (b.clr - a.clr) || (b.len - a.len) || (row(a) - row(b));
  };
}

const fromServer = () => typeof location !== "undefined" && location.protocol.startsWith("http");
const appFlags = () => typeof window !== "undefined" ? window.FINDALINE_APP : undefined;
const finite = (v: number) => isFinite(v) ? v : null;

/** The range over two ranges (either may be null). */
const both = (a: Range | null, b: Range | null): Range | null =>
  a && b ? {min: Math.min(a.min, b.min), max: Math.max(a.max, b.max)} : a || b;

/** The ranges of the lines' values the filters offer, in one pass over the lines (`each` calls its function with
 *  every line). */
function lineRanges(each: (f: (l: LineValues) => void) => void, highAbove: number, largestGroup: number,
                    favourites: boolean, lift: FilterRanges["lift"] = null): FilterRanges {
  const r = {len: new Ranger(), clr: new Ranger(), clrN: new Ranger(), dh: new Ranger(), elev: new Ranger(),
             elevHigh: new Ranger(), pct1: new Ranger(), pct2: new Ranger(), hmax: new Ranger(), hmean: new Ranger(),
             highPct: new Ranger(), angle: new Ranger(), prom: new Ranger(), drop: new Ranger()};
  let water = false, filled = false;
  each((l) => {
    r.len.add(l.len); r.clr.add(l.clr); r.clrN.add(l.clrN); r.dh.add(dh(l));
    r.elev.add(lowerAnchor(l)); r.elevHigh.add(upperAnchor(l)); r.pct1.add(l.pct1); r.pct2.add(l.pct2);
    r.hmax.add(l.hmax); r.hmean.add(l.hmean); r.highPct.add(l.highPct); r.angle.add(wallAngle(l));
    r.prom.add(finite(prominence(l, Math.max))); r.drop.add(finite(drop(l)));
    if (!water && l.water > 0) water = true;
    if (!filled && l.filled > 0) filled = true;
  });
  return {lift, len: r.len.range, clr: r.clr.range, clrN: r.clrN.range, dh: r.dh.range, elev: r.elev.range,
          elevHigh: r.elevHigh.range, pct: both(r.pct1.range, r.pct2.range), hmax: r.hmax.range,
          hmean: r.hmean.range, highPct: r.highPct.range, highAbove, angle: r.angle.range, prom: r.prom.range,
          drop: r.drop.range, group: largestGroup > 1 ? {min: 1, max: largestGroup} : null, water, filled,
          favourites};
}

/** The two points ([lat, lon]) of a link's line "lat1,lon1,lat2,lon2"; null when it is not four finite numbers. */
function linkPoints(key: string): [[number, number], [number, number]] | null {
  const parts = key.split(",");
  if (parts.length !== 4 || parts.some((v) => v.trim() === "")) return null;
  const [lat1, lon1, lat2, lon2] = parts.map(Number);
  return [lat1, lon1, lat2, lon2].every(isFinite) ? [[lat1, lon1], [lat2, lon2]] : null;
}

export class ResultModel {
  readonly data: RunData;
  readonly runId: string;
  state: LinesState;
  filters: Filters;
  list: ListState;
  /** The groups shown (filters, grouping, group size), clear ones first, best first: the map's order. */
  groups: LineGroup[] = [];
  /** The groups as rows in the map's order (clear first); `rows` is them sorted as the list says. */
  baseRows: Spot[] = [];
  rows: Spot[] = [];
  shown = {spots: 0, lines: 0};
  largestGroup = 1;
  ranges!: FilterRanges;
  /** The other runs shown, by id. */
  readonly others = new Map<string, ShownRun>();
  /** The user's favourites are known (the server keeps them for this page). */
  favouritesOn = false;
  note: Note | null = null;
  /** The selected group and the line shown for it; null: none. */
  selected: {group: LineGroup; line: Line} | null = null;
  /** The key of a link's line outside this run being measured or shown as measured (`openLinked`), else null. */
  measuredLink: string | null = null;
  /** The profile of the selected line was closed (ProfileDock); selecting again, or another line, shows it. */
  profileClosed = false;
  /** Shows every region of coarser terrain on the map (coarserLayer.addCoarser, the head's "Show on map"); null
   *  without a map or without such regions. */
  coarserFit: (() => void) | null = null;
  /** How many Line objects the model made (lineAt): for tests and measurements. */
  madeLines = 0;

  // Runs of millions of lines: what goes through every line reads the columns, is done only when it changes, and
  // the lines are known by their index among the runs shown (lineAt)
  private readonly favourites = new Set<string>();  // keyOf
  private readonly favouriteSet = new Set<number>();   // the indices of `favourites` among the runs shown
  private readonly inFolder = new Map<string, number | null>();  // keyOf -> the favourite's folder
  /** The user's folders of favourites (from the server with the run's favourites). */
  folders: FavouriteFolder[] = [];
  tree = new FolderTree([]);
  private readonly chosen = new Set<number>();      // the line shown of a group, chosen by the user (its index)
  private readonly computed = new Map<string, Profile>();  // by lineCoords (this run's lines only)
  private readonly listeners = new Set<() => void>();
  private readonly api: ResultApi;
  private readonly wantFavourites: boolean;
  readonly canCompute: boolean;
  private selectedLine: Line | null = null;
  // This run's lines (the first) and the other runs', each from its own index on; indices are never given twice
  // (a run shown again gets new ones), so a Line's index (`index`) never names another line
  private readonly tables: Table[] = [];
  private nextStart = 0;
  private version = 0;  // of the runs shown (gather)
  private made = new Map<number, Line>();           // the Lines made, by index (lineAt)
  private readonly index = new WeakMap<Line, number>();  // a made Line's index
  private counts = {clean: 0, over: 0};
  private grouped: LineGroup[] = [];  // the grouping's groups, before the group size filter
  // a line's group among `groups` before sorting (shownGroups), else -1: an array per run shown, by the line's row
  private groupAt = new Map<Table, Int32Array>();
  private shownGroups: LineGroup[] = [];
  private special: Set<LineGroup> | null = null;  // the groups shown holding a chosen line or a favourite
  private valueRanges: {of: number; ranges: FilterRanges} | null = null;  // lineRanges of the runs shown (version)
  // A spot's best line (its index) and its lines in the spot's order (BY_MEAN) or the grouping's, per group
  private best = new WeakMap<LineGroup, number>();
  private ordered = new WeakMap<LineGroup, Line[]>();
  private inOrder = new WeakMap<LineGroup, Line[]>();
  private readonly compareMean = byMean<LineCursor>((c) => c.i);  // c.i: the line's row in its run
  private readonly cursorA = new LineCursor(lineColumns([]));
  private readonly cursorB = new LineCursor(lineColumns([]));

  /** `data`: a run with its lines as columns (result/load.ts), or data.js's value with its rows (read into columns
   *  here; the rows are left as they are). */
  constructor(data: RunData | RunScript, options: ResultOptions = {}) {
    this.data = "columns" in data ? data
      : timed("fal:run:lines", () => runData(data as RunScript), {count: (data as RunScript).lines.length});
    this.runId = data.run.id;
    this.tables.push({cols: this.data.columns, start: 0});
    this.nextStart = this.data.columns.length;
    this.gather();
    this.api = options.api || SERVER_API;
    const app = appFlags();
    this.wantFavourites = options.favourites ?? app?.favourites ?? fromServer();
    this.canCompute = options.profiles ?? app?.profiles ?? fromServer();
    this.state = {group: true, distance: this.data.distance, by: BY_MEAN, showClean: true, showOver: true};
    this.filters = savedFilters();
    this.list = options.list && !hasSavedList() ? {...savedList(), ...options.list} : savedList();
    this.compute();
    this.loadRunFavourites(this.runId);
  }

  // --- notifications ---

  /** Call `listener` after every change; returns the function that stops it. */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  private notify() {
    this.listeners.forEach((f) => f());
  }

  // --- lines and keys ---

  /** How many lines this run has. */
  get count(): number {
    return this.data.columns.length;
  }

  /** How many lines the runs shown have (this run's and the other runs'). */
  get total(): number {
    return this.tables.reduce((n, t) => n + t.cols.length, 0);
  }

  get nClean(): number { return this.counts.clean; }
  get nOver(): number { return this.counts.over; }

  /** The lines of run `id` (this run's or another run's shown), found by the run: a run of no lines shares its
   *  start index with the next one. */
  private tableOfRun(id: string): Table | undefined {
    return id === this.runId ? this.tables[0] : this.tables.find((t) => t.run?.info.id === id);
  }

  /** The run holding index `at`. */
  private tableOf(at: number): Table | undefined {
    for (const t of this.tables) if (at >= t.start && at < t.start + t.cols.length) return t;
    return undefined;
  }

  /** The line of index `at` among the runs shown (this run's line k is index k) as a Line: the same object while it
   *  is kept (prune), made from the columns when it is not. */
  lineAt(at: number): Line {
    let l = this.made.get(at);
    if (l) return l;
    const t = this.tableOf(at);
    if (!t) throw new RangeError("no line " + at);
    l = lineAt(t.cols, at - t.start, t.run);
    if (!l.prof && !t.run && this.computed.size) l.prof = this.computed.get(lineCoords(l)) ?? null;
    this.madeLines++;
    this.made.set(at, l);
    this.index.set(l, at);
    return l;
  }

  /** The index of a Line the model made (lineAt), else -1 (a measured line, a copy). */
  indexOf(l: Line): number {
    return this.index.get(l) ?? -1;
  }

  /** Call `f` with each of this run's lines (a cursor on the columns, valid only during the call). */
  forEachLine(f: (l: LineValues) => void) {
    this.eachOf(this.tables[0], f);
  }

  private eachOf(t: Table, f: (l: LineValues, at: number) => void) {
    const cursor = new LineCursor(t.cols);
    for (let i = 0; i < t.cols.length; i++) {
      cursor.i = i;
      f(cursor, t.start + i);
    }
  }

  /** The cursor `c` on the line of index `at`. */
  private place(c: LineCursor, at: number): LineCursor {
    const t = this.tableOf(at)!;
    c.c = t.cols;
    c.i = at - t.start;
    return c;
  }

  /** byMean of the lines of two indices. */
  private compareAt(a: number, b: number): number {
    return this.compareMean(this.place(this.cursorA, a), this.place(this.cursorB, b));
  }

  /** The runs shown changed: their counts again. */
  private gather() {
    let over = 0, all = 0;
    for (const t of this.tables) {
      const o = t.cols.over;
      for (let i = 0; i < o.length; i++) over += o[i];
      all += o.length;
    }
    this.counts = {clean: all - over, over};
    this.version++;
  }

  /** The key of a line among the runs shown (keys.lineKey). */
  keyOf = (l: Line): string => lineKey(l, this.runId);

  /** The run a line belongs to. */
  runOf(l: Line): string {
    return l.run ? l.run.info.id : this.runId;
  }

  /** The A-frame height of a line's run, for the words of the tight mark: this run's (`data.lift`; none without
   *  A-frames); another run's line has none known here. */
  liftOf(l: Line): number | undefined {
    return l.run ? undefined : this.data.lift || undefined;
  }

  /** The `#line=` value of a link to a line of this run (keys.lineCoords). */
  lineLink(l: Line): string {
    return lineCoords(l);
  }

  /** The index of this run's line whose link (keys.lineCoords) is `link`, else -1. */
  private findLink(link: string): number {
    const lat1 = Number(link.split(",")[0]), c = this.data.columns, cursor = new LineCursor(c);
    for (let i = 0; i < c.length; i++) {
      if (c.lat1.at(i) !== lat1) continue;  // the same text has the same first number
      cursor.i = i;
      if (lineCoords(cursor) === link) return i;
    }
    return -1;
  }

  /** This run's line whose link (keys.lineCoords) is `link`, else null. */
  linkedLine(link: string): Line | null {
    const at = this.findLink(link);
    return at < 0 ? null : this.lineAt(at);
  }

  // --- what is shown ---

  /** The line a group shows: the one chosen in it, else the user's favourite in it, else its best (bestOf). */
  shownOf(g: LineGroup): Line {
    if (this.chosen.size === 0 && this.favouriteSet.size === 0) return this.bestOf(g);
    if (!this.specialGroups().has(g)) return this.bestOf(g);
    for (let k = g.start; k < g.end; k++) if (this.chosen.has(g.flat[k])) return this.lineAt(g.flat[k]);
    for (let k = g.start; k < g.end; k++) if (this.favouriteSet.has(g.flat[k])) return this.lineAt(g.flat[k]);
    return this.bestOf(g);
  }

  /** The groups shown that hold a chosen line or a favourite. */
  private specialGroups(): Set<LineGroup> {
    if (!this.special) {
      const special = new Set<LineGroup>();
      for (const of of [this.chosen, this.favouriteSet]) {
        of.forEach((at) => {
          const q = this.groupIndex(at);
          if (q >= 0) special.add(this.shownGroups[q]);
        });
      }
      this.special = special;
    }
    return this.special;
  }

  /** The first line of a spot: under BY_MEAN its line with the highest mean height (byMean), else the
   *  representative of the grouping. */
  bestOf(g: LineGroup): Line {
    if (this.state.by !== BY_MEAN || g.size < 2) return this.lineAt(g.repAt);
    let best = this.best.get(g);
    if (best === undefined) {
      best = g.flat[g.start];
      for (let k = g.start + 1; k < g.end; k++) if (this.compareAt(g.flat[k], best) < 0) best = g.flat[k];
      this.best.set(g, best);
    }
    return this.lineAt(best);
  }

  /** A spot's lines in the grouping's order (the representative first), as Lines. */
  linesOf(g: LineGroup): Line[] {
    let lines = this.inOrder.get(g);
    if (!lines) {
      lines = Array.from(g.flat.subarray(g.start, g.end), (at) => this.lineAt(at));
      this.inOrder.set(g, lines);
    }
    return lines;
  }

  /** A spot's lines in the order the page shows them (the stepper, the unfolded rows, `alsoOf`), best first:
   *  under BY_MEAN by byMean, else the grouping's order (the representative first). The members of the groups
   *  stay those of the grouping, in its order. */
  membersOf(g: LineGroup): Line[] {
    if (this.state.by !== BY_MEAN || g.size < 2) return this.linesOf(g);
    let lines = this.ordered.get(g);
    if (!lines) {
      const order = Array.from(g.flat.subarray(g.start, g.end)).sort((a, b) => this.compareAt(a, b));
      lines = order.map((at) => this.lineAt(at));
      this.ordered.set(g, lines);
    }
    return lines;
  }

  /** The grouping's rank: the run's (`data.by`) under BY_MEAN. */
  private groupBy(): string {
    return this.state.by === BY_MEAN ? this.data.by : this.state.by;
  }

  /** Is the line shown for its group the user's favourite rather than a choice. */
  shownAsFavourite(g: LineGroup): boolean {
    const at = this.indexOf(this.shownOf(g));
    return this.favouriteSet.has(at) && !this.chosen.has(at);
  }

  /** The indices of the lines the filters pass among the runs shown, in their order. */
  private visibleLines(): Int32Array {
    const f = this.filters, s = this.state, lift = this.data.lift;
    const favOnly = f.favOnly && this.favouritesOn;
    const out = new Int32Array(this.total);
    let n = 0;
    for (const t of this.tables) {
      const over = t.cols.over, cursor = new LineCursor(t.cols);
      for (let i = 0; i < over.length; i++) {
        if (over[i] ? !s.showOver : !s.showClean) continue;
        cursor.i = i;
        if (!passes(cursor, f, lift)) continue;
        if (favOnly && !this.favouriteSet.has(t.start + i)) continue;
        out[n++] = t.start + i;
      }
    }
    return out.subarray(0, n);
  }

  /** The grouping of the lines of indices `visible`: runs in another coordinate system are grouped in a local plane
   *  around this run (their anchors' metres from their latitudes and longitudes). */
  private groupVisible(visible: Int32Array): LineGroup[] {
    const m = visible.length;
    const framed = Array.from(this.others.values()).some((r) => r.crs !== this.data.crs);
    const plane = framed ? localPlane(this.data.center[0], this.data.center[1]) : null;
    const input: GroupInput = {x1: new Float64Array(m), y1: new Float64Array(m), x2: new Float64Array(m),
                               y2: new Float64Array(m), len: new Float64Array(m), clr: new Float64Array(m),
                               hmax: new Float64Array(m), over: new Uint8Array(m)};
    let t = this.tables[0];
    for (let k = 0; k < m; k++) {
      const at = visible[k];
      if (at < t.start || at >= t.start + t.cols.length) t = this.tableOf(at)!;
      const c = t.cols, i = at - t.start;
      if (plane) {
        input.x1[k] = plane.x(c.lon1.at(i)!); input.y1[k] = plane.y(c.lat1.at(i)!);
        input.x2[k] = plane.x(c.lon2.at(i)!); input.y2[k] = plane.y(c.lat2.at(i)!);
      } else {
        input.x1[k] = c.x1.at(i)!; input.y1[k] = c.y1.at(i)!; input.x2[k] = c.x2.at(i)!; input.y2[k] = c.y2.at(i)!;
      }
      // null as a Float64Array stores it (0), as the grouping read the lines' values before
      input.len[k] = c.len.at(i)!; input.clr[k] = c.clr.at(i)!; input.hmax[k] = c.hmax.at(i)!;
      input.over[k] = c.over[i];
    }
    const {reps, members, starts} = groupIndices(input, this.state.distance, this.groupBy());
    for (let k = 0; k < members.length; k++) members[k] = visible[members[k]];
    return Array.from(reps, (rep, g) => new LineGroup(this, members, starts[g], starts[g + 1], visible[rep],
                                                        input.over[rep] === 1));
  }

  /** The groups and rows again: after a change of the filters, of the grouping
   *  or of the runs shown. */
  private compute() {
    const s = this.state;
    const visible = timed("fal:run:filter", () => this.visibleLines());
    this.grouped = timed("fal:run:group", () => s.group ? this.groupVisible(visible)
      : Array.from(visible, (at, k) => new LineGroup(this, visible, k, k + 1, at, this.isOver(at))), {count: visible.length});
    this.largestGroup = this.grouped.reduce((m, g) => Math.max(m, g.size), 1);
    this.ranges = timed("fal:run:ranges", () => this.rangesNow());
    timed("fal:run:rows", () => this.showGroups(), {count: this.grouped.length});
    this.prune();
  }

  private isOver(at: number): boolean {
    const t = this.tableOf(at)!;
    return t.cols.over[at - t.start] === 1;
  }

  /** Forget the made lines that nothing shown holds when they are many more than the rows (PRUNE_MIN): kept are
   *  the rows' lines, the selected line, the chosen lines and the favourites. */
  private prune() {
    if (this.made.size <= Math.max(PRUNE_MIN, 2 * this.baseRows.length)) return;
    const keep = new Map<number, Line>(), made = this.made;
    const hold = (at: number) => { const l = made.get(at); if (l) keep.set(at, l); };
    this.baseRows.forEach((r) => hold(this.indexOf(r.line)));
    if (this.selectedLine) hold(this.indexOf(this.selectedLine));
    this.chosen.forEach(hold);
    this.favouriteSet.forEach(hold);
    this.made = keep;
  }

  /** The filters' ranges: of the values only when the runs shown changed. */
  private rangesNow(): FilterRanges {
    if (this.valueRanges?.of !== this.version) {
      const each = (f: (l: LineValues) => void) => this.tables.forEach((t) => this.eachOf(t, f));
      this.valueRanges = {of: this.version, ranges: lineRanges(each, this.data.high_above, 1, false, this.liftRange())};
    }
    const largest = this.largestGroup;
    return {...this.valueRanges.ranges, group: largest > 1 ? {min: 1, max: largest} : null, favourites: this.favouritesOn};
  }

  /** The filter "A-frame needed at most" of a run with a no-fall zone or A-frames: the run's options and the
   *  largest values of this run's lines (null: a run without the options, no filter). */
  private liftRange(): FilterRanges["lift"] {
    const d = this.data;
    if (!d.end_zone && !d.lift) return null;
    let needed = 0, noZone = 0;
    this.forEachLine((l) => {
      if (typeof l.lift_needed === "number" && l.lift_needed > needed) needed = l.lift_needed;
      if (typeof l.lift_no_zone === "number" && l.lift_no_zone > noZone) noZone = l.lift_no_zone;
    });
    return {lift: d.lift || 0, zone: d.end_zone || 0, needed, noZone};
  }

  /** How many of this run's lines need at most `max` metres of A-frames (with the zone, or without it: `noZone`). */
  liftCount(max: number, noZone: boolean): number {
    let n = 0;
    this.forEachLine((l) => {
      const v = noZone ? l.lift_no_zone : l.lift_needed;
      if (typeof v !== "number" || v <= max + 1e-9) n++;
    });
    return n;
  }

  /** The groups shown (the group size filter) and their rows again. */
  private showGroups() {
    const f = this.filters, s = this.state;
    let groups = this.grouped;
    if (s.group && f.groupMin !== null) groups = groups.filter((g) => g.size >= f.groupMin!);
    const groupAt = new Map(this.tables.map((t) => [t, new Int32Array(t.cols.length).fill(-1)]));
    let t = this.tables[0], rows = groupAt.get(t)!;
    groups.forEach((g, q) => {
      for (let k = g.start; k < g.end; k++) {
        const at = g.flat[k];
        if (at < t.start || at >= t.start + t.cols.length) { t = this.tableOf(at)!; rows = groupAt.get(t)!; }
        rows[at - t.start] = q;
      }
    });
    this.groupAt = groupAt;
    this.shownGroups = groups;
    this.special = null;
    // the grouping gives clear groups first; without grouping the lines come in their order, so the
    // rows (clear first) keep that order within each kind
    this.baseRows = groups.map((g) => ({line: this.shownOf(g), n: g.size, group: g}))
      .sort((a, b) => +a.group.over - +b.group.over);
    this.groups = this.baseRows.map((r) => r.group);
    this.shown = {spots: groups.length, lines: groups.reduce((n, g) => n + g.size, 0)};
    this.sortRows();
    this.reselect();
  }

  /** The rows' lines again after a choice (the groups stay). */
  private refreshRows() {
    this.special = null;
    this.baseRows.forEach((r) => { r.line = this.shownOf(r.group); });
    this.sortRows();
    this.reselect();
  }

  private sortRows() {
    // "Lines in the group" without grouping sorts by length
    const key = sortKey(this.list.sort === "n" && !this.state.group ? "len" : this.list.sort);
    this.rows = sortRows(this.baseRows, key, this.list.desc);
  }

  /** The selection on the groups shown now: the group holding the selected line, else none. */
  private reselect() {
    const group = this.selectedLine && this.groupOf(this.selectedLine);
    if (!group) { this.selected = null; this.selectedLine = null; return; }
    const line = this.shownOf(group);
    this.selected = {group, line};
    this.selectedLine = line;
  }

  /** The position among shownGroups of the group holding the line of index `at`, else -1. */
  private groupIndex(at: number): number {
    const t = at >= 0 ? this.tableOf(at) : undefined, rows = t && this.groupAt.get(t);
    return rows ? rows[at - t!.start] : -1;
  }

  /** The group (shown now) holding a line, or undefined. */
  groupOf(l: Line): LineGroup | undefined {
    const at = this.indexOf(l);
    const q = this.groupIndex(at);
    return q >= 0 ? this.shownGroups[q] : undefined;
  }

  /** The other lines of the spot of `l` (its group among the groups shown) that belong to its run, in the spot's
   *  order (membersOf: the highest on average first), at most `max`: what the 3D view's link hands over besides
   *  the line itself (`&also=`). A line alone in its spot, or not among the groups shown, has none. */
  alsoOf(l: Line, max = 20): Line[] {
    const group = this.groupOf(l);
    if (!group) return [];
    const run = this.runOf(l);
    return this.membersOf(group).filter((m) => m !== l && this.runOf(m) === run).slice(0, max);
  }

  // --- changes ---

  setState(next: LinesState) {
    this.state = next;
    this.compute();
    this.notify();
  }

  setFilters(next: Filters) {
    this.filters = next;
    saveFilters(next);
    this.compute();
    this.notify();
  }

  clearFilters() {
    this.setFilters({...NO_FILTERS});
  }

  /** The list's state (sorting, unfolded, in view): kept in the browser. */
  setList(next: ListState) {
    this.list = next;
    saveList(next);
    this.sortRows();
    this.notify();
  }

  /** Select a group, or a line (shown for its group: chosen if it is not), or nothing. */
  select(target: LineGroup | Line | null) {
    this.profileClosed = false;
    if (target === null) {
      this.selectedLine = null;
    } else if (target instanceof LineGroup) {
      this.selectedLine = this.shownOf(target);
    } else {
      const group = this.groupOf(target);
      if (!group) return;
      if (this.shownOf(group) !== target) this.setChosen(group, target);
      this.selectedLine = target;
      this.refreshRows();
      this.notify();
      return;
    }
    this.reselect();
    this.notify();
  }

  /** The position of the selected spot in the rows' order (-1: none selected or not in the rows). */
  get position(): number {
    const sel = this.selected;
    return sel ? this.rows.findIndex((r) => r.group === sel.group) : -1;
  }

  /** Select the next spot of the rows' order (the first without a selection); false at the end. */
  next(): boolean {
    return this.step(1);
  }

  /** Select the previous spot (the last without a selection); false at the start. */
  prev(): boolean {
    return this.step(-1);
  }

  private step(by: 1 | -1): boolean {
    const k = this.position, target = k < 0 ? (by > 0 ? 0 : this.rows.length - 1) : k + by;
    if (target < 0 || target >= this.rows.length) return false;
    this.select(this.rows[target].group);
    return true;
  }

  private setChosen(g: LineGroup, line: Line) {
    for (let k = g.start; k < g.end; k++) this.chosen.delete(g.flat[k]);
    this.chosen.add(this.indexOf(line));
    this.special = null;
  }

  /** Show another line of a group (the representative too is a choice: it wins over a favourite in it);
   * the groups stay those of the grouping. A selected group keeps its selection on the new line. */
  choose(g: LineGroup, line: Line) {
    if (!g.has(this.indexOf(line))) return;
    const wasSelected = this.selected?.group === g;
    this.profileClosed = false;
    this.setChosen(g, line);
    if (wasSelected) this.selectedLine = line;
    this.refreshRows();
    this.notify();
  }

  /** Close the selected line's profile (until a line is selected again: select, choose, showProfile). */
  closeProfile() {
    this.profileClosed = true;
    this.notify();
  }

  showProfile() {
    this.profileClosed = false;
    this.notify();
  }

  /** The index of the shown line among its spot's lines in their order (membersOf; the selected group's by
   *  default); -1: none. */
  variantIndex(g: LineGroup | undefined = this.selected?.group): number {
    return g ? this.membersOf(g).indexOf(this.shownOf(g)) : -1;
  }

  /** How many of this run's lines need each class of rigging (filters.needClass: none, the no-fall zone,
   *  A-frames); null for a run without the zone and the A-frames. */
  needCounts(): [number, number, number] | null {
    if (!this.data.end_zone && !this.data.lift) return null;
    if (!this.needs) {
      const n: [number, number, number] = [0, 0, 0];
      this.forEachLine((l) => {
        const k = needClass(l);
        if (k !== null) n[k]++;
      });
      this.needs = n;
    }
    return this.needs;
  }
  private needs: [number, number, number] | null = null;

  // --- favourites ---

  isFavourite = (l: Line): boolean => this.favourites.has(this.keyOf(l));

  /** The folder of a favourite (null: the top level); undefined: not a favourite. */
  folderOf(l: Line): number | null | undefined {
    const key = this.keyOf(l);
    return this.favourites.has(key) ? this.tree.known(this.inFolder.get(key)) : undefined;
  }

  /** The folder a new favourite goes to: the last one chosen in this browser, if it still exists. */
  get lastFolder(): number | null {
    try {
      const v = localStorage.getItem(LAST_FOLDER);
      return this.tree.known(v === null ? null : Number(v));
    } catch {
      return null;
    }
  }

  private setLastFolder(folder: number | null) {
    try {
      if (folder === null) localStorage.removeItem(LAST_FOLDER); else localStorage.setItem(LAST_FOLDER, String(folder));
    } catch { /* no storage: the top level next time */ }
  }

  /** The user's favourites of a run; none when the server keeps none for this page. */
  private loadRunFavourites(runId: string) {
    if (!this.wantFavourites) return;
    this.api.loadFavourites(runId).then((found) => {
      const body: {lines: string[]; in: Record<string, number | null>; folders: FavouriteFolder[] | null} =
        Array.isArray(found) ? {lines: found, in: {}, folders: null} : found;
      body.lines.forEach((coords) => {
        const key = runLineKey(runId, coords);
        this.favourites.add(key);
        this.inFolder.set(key, body.in[coords] ?? null);
      });
      if (body.folders) this.setFolders(body.folders);
      this.markFavourites(runId, body.lines);
      const regroup = this.filters.favOnly;
      this.favouritesOn = true;
      if (regroup) this.compute();
      else { this.ranges = this.rangesNow(); this.refreshRows(); }
      this.notify();
    }, () => {});
  }

  private setFolders(folders: FavouriteFolder[]) {
    this.folders = folders;
    this.tree = new FolderTree(folders);
  }

  /** A new folder of favourites in `parent` (null: the top level); its id, or null with a note. */
  async newFolder(name: string, parent: number | null): Promise<number | null> {
    if (!this.api.addFolder) return null;
    try {
      const id = await this.api.addFolder(name, parent);
      this.setFolders([...this.folders, {id, parent_id: parent, name: name.trim(), created: ""}]);
      this.notify();
      return id;
    } catch (e: any) {
      this.setNote({text: "The folder was not made: " + e.message});
      return null;
    }
  }

  /** Put a line into a folder of favourites: marked there when it is not a favourite, else moved. */
  saveTo(l: Line, folder: number | null): Promise<void> {
    this.setLastFolder(folder);
    const key = this.keyOf(l);
    if (!this.favourites.has(key)) return this.toggleFavourite(l, folder);
    const before = this.inFolder.get(key) ?? null;
    if (before === folder || !this.api.moveFavourite) return Promise.resolve();
    this.inFolder.set(key, folder);
    this.notify();
    return this.api.moveFavourite(this.runOf(l), lineCoords(l), folder).catch((e) => {
      this.inFolder.set(key, before);
      this.setNote({text: "The favourite was not moved: " + e.message});
    });
  }

  /** Mark or unmark a favourite at once (a new one into `folder`, by default the last folder used);
   *  rolled back with a note when the server does not save it. */
  toggleFavourite(l: Line, folder: number | null = this.lastFolder): Promise<void> {
    const key = this.keyOf(l), on = !this.favourites.has(key), at = this.indexOf(l);
    const flip = (to: boolean) => {
      if (to) { this.favourites.add(key); if (at >= 0) this.favouriteSet.add(at); this.inFolder.set(key, folder); }
      else { this.favourites.delete(key); this.favouriteSet.delete(at); this.inFolder.delete(key); }
      this.special = null;
    };
    // A line shown stays shown in its group
    const group = this.groupOf(l);
    if (!on && group && this.shownOf(group) === l) { this.chosen.add(at); this.special = null; }
    flip(on);
    this.note = null;
    this.afterFavourite();
    return this.api.saveFavourite(this.runOf(l), l, on, on ? folder : undefined).catch((e) => {
      flip(!on);
      this.note = {text: "The favourite was not saved: " + e.message};
      this.afterFavourite();
    });
  }

  /** The groups (only favourites shown) or the lines shown again after a favourite changed. */
  private afterFavourite() {
    if (this.filters.favOnly) this.compute(); else this.refreshRows();
    this.notify();
  }

  /** The lines of a run whose coordinates (keys.lineCoords) are among `found` become favourites
   *  (keys are built only for the lines whose first latitude is among theirs). */
  private markFavourites(runId: string, found: string[]) {
    const t = this.tableOfRun(runId);
    if (!t) return;
    const wanted = new Set(found), lat1 = new Set(found.map((coords) => Number(coords.split(",")[0])));
    this.eachOf(t, (l, at) => { if (lat1.has(l.lat1) && wanted.has(lineCoords(l))) this.favouriteSet.add(at); });
    this.special = null;
  }

  /** The favourite lines of the runs shown. */
  favouriteLines(): Line[] {
    return Array.from(this.favouriteSet).filter((at) => this.tableOf(at)).sort((a, b) => a - b)
      .map((at) => this.lineAt(at));
  }

  setNote(note: Note | null) {
    this.note = note;
    this.notify();
  }

  setCoarserFit(fit: (() => void) | null) {
    this.coarserFit = fit;
    this.notify();
  }

  // --- links ---

  /** A link's line that `openLinked` would measure: four numbers, this page can ask profiles, and the line is not
   *  among the run's. */
  measurableLink(link: string): boolean {
    return this.canCompute && linkPoints(link) !== null && this.findLink(link) < 0;
  }

  /** Show and select the line of a link ("#line=lat1,lon1,lat2,lon2" or the value alone) in its group;
   * returns it, or null with a note (not in this run; hidden by the filters, with an action that
   * clears them and tries again). A line that is not among the run's (the 3D view's moved anchors, a favourite
   * saved there) is measured where the page may ask profiles, as `measure` does for two points: with
   * `onMeasured`, which gets the measured line (the shell shows it), the link's key in `measuredLink` meanwhile,
   * and a note when the measurement fails; without it, or where profiles cannot be asked, today's note. */
  openLinked(hash: string, onMeasured?: (line: Line) => void): Line | null {
    const value = hash.startsWith("#line=") ? hash.slice("#line=".length) : hash.replace(/^#/, "");
    const wanted = decodeURIComponent(value);
    const line = this.linkedLine(wanted);
    if (!line) {
      const points = onMeasured && this.canCompute ? linkPoints(wanted) : null;
      if (points) {
        this.note = null;
        this.measuredLink = wanted;
        this.notify();
        this.measure(points[0], points[1]).then((measured) => {
          if (this.measuredLink === wanted) onMeasured!(measured);
        }, (e) => {
          if (this.measuredLink !== wanted) return;
          this.measuredLink = null;
          this.note = {text: "The line of the link could not be measured: " + (e as Error).message};
          this.notify();
        });
        return null;
      }
      this.note = {text: "The line of the link is not in this run."};
      this.notify();
      return null;
    }
    this.measuredLink = null;
    this.note = null;
    this.chosen.add(this.indexOf(line));
    this.refreshRows();
    if (this.groupOf(line)) {
      this.select(line);
      return line;
    }
    this.note = {text: "The line of the link is hidden by the filters.", action: "clear filters", onAction: () => {
      this.filters = {...NO_FILTERS};
      saveFilters(this.filters);
      this.state = {...this.state, showClean: true, showOver: true};
      this.compute();
      this.openLinked(hash);
    }};
    this.notify();
    return null;
  }

  // --- other runs ---

  /** Show another run's lines (lines.js, from others.loadLines) with this run's: its rows read into columns. */
  addRun(info: RunInfo, loaded: RunLines, color = colorOf(info.id)) {
    const cols = lineColumns(loaded.lines, loaded.terrain, loaded.ends), start = this.nextStart;
    this.nextStart += cols.length;
    this.tables.push({cols, start, run: {info, color}});
    this.others.set(info.id, {info, color, crs: loaded.crs, area: loaded.area, start, count: cols.length});
    this.gather();
    this.compute();
    this.notify();
    this.loadRunFavourites(info.id);
  }

  removeRun(id: string) {
    const run = this.others.get(id);
    if (!run) return;
    this.others.delete(id);
    this.tables.splice(this.tables.indexOf(this.tableOfRun(id)!), 1);
    const gone = (at: number) => at >= run.start && at < run.start + run.count;
    for (const of of [this.chosen, this.favouriteSet]) of.forEach((at) => { if (gone(at)) of.delete(at); });
    this.made.forEach((_, at) => { if (gone(at)) this.made.delete(at); });
    this.gather();
    this.compute();
    this.notify();
  }

  // --- profiles ---

  /** A line's profile: saved with it, computed before, or computed by the server (lines of this run only;
   * maps of areas keep a profile only for the line saved for each group). */
  async profile(l: Line): Promise<Profile> {
    if (l.prof) return l.prof;
    if (l.run) throw new Error("lines of other runs come without profiles");
    const key = lineCoords(l), known = this.computed.get(key);
    if (known) { l.prof = known; return known; }
    if (!this.canCompute) throw new Error("no profile saved for this line, and this page cannot compute one");
    const p = await this.api.profile(this.runId, key);
    this.computed.set(key, p);
    l.prof = p;
    this.notify();
    return p;
  }

  /** The profile between two points (lat, lon) as a line (anchors on the ground), computed by the server. */
  async measure(a: [number, number], b: [number, number]): Promise<Line> {
    if (!this.canCompute) throw new Error("this page cannot compute profiles");
    const key = [a[0], a[1], b[0], b[1]].map((v) => v.toFixed(7)).join(",");
    return measuredLine(a, b, await this.api.profile(this.runId, key), this.data.terrain);
  }
}

/** A run's model for a page showing its loading (result/view/RunLoading): "groups" reported, the page painted,
 *  then the model built (its lines, filters and groups at once: 0.7 s for 695 000 lines on a desktop,
 *  tools/perf_run_load.py, so not in slices). */
export async function buildModel(data: RunData, options: ResultOptions = {}, onProgress?: OnProgress): Promise<ResultModel> {
  onProgress?.({phase: "groups", fraction: null});
  await nextPaint();
  return new ResultModel(data, options);
}
