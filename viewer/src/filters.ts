// Filters of the lines on the map, applied before grouping (the group size after it).
// null means no limit. Kept in the browser for every map (but "only favourites": the map's own).

import type { LineValues } from "./types";

export interface Filters {
  lenMin: number | null;
  lenMax: number | null;
  clrMin: number | null;      // clearance over terrain
  clrNMin: number | null;     // clearance over trees/buildings (lines without the surface model pass)
  dhMax: number | null;       // height difference of the anchors
  elevMin: number | null;     // height of the lower anchor
  elevMax: number | null;     // height of the upper anchor
  pctMin: number | null;      // percentile of the lower anchor in its run's area (lines without one pass)
  pctMax: number | null;      // ... of the upper anchor
  heightMin: number | null;   // largest height of the webbing above the terrain
  meanMin: number | null;     // its mean along the line
  highPctMin: number | null;  // % of the line at least high_above over the terrain
  angleMax: number | null;    // angle to the wall at both anchors
  promMin: number | null;     // prominence of the more prominent anchor
  promBothMin: number | null; // ... of the less prominent one
  dropMin: number | null;     // drop below both anchors
  water: "all" | "water" | "land";
  hideFilled: boolean;        // hide lines over gaps filled from another source
  groupMin: number | null;    // similar lines in a group (with grouping on)
  liftMax: number | null;     // A-frame height needed at most (null: the run's own, everything shown; lines of a
                              // run without the options pass)
  liftNoZone: boolean;        // ... without the no-fall zone (lift_no_zone instead of lift_needed)
  // The classes of rigging a line needs (needClass), hidden by the head's "Why so many?" box of a run made with
  // the square rule; lines without the values pass. The page's own, like favOnly: not kept in the browser
  hideNeedNone: boolean;      // lines that need no no-fall zone and no A-frames
  hideNeedZone: boolean;      // lines that need the no-fall zone (no A-frames)
  hideNeedLift: boolean;      // lines that need A-frames
  favOnly: boolean;           // only favourite lines (applied by result/model.ts, which knows them)
}

export const NO_FILTERS: Filters = {lenMin: null, lenMax: null, clrMin: null, clrNMin: null, dhMax: null,
                                    elevMin: null, elevMax: null, pctMin: null, pctMax: null, heightMin: null, meanMin: null, highPctMin: null,
                                    angleMax: null, promMin: null, promBothMin: null, dropMin: null, water: "all", hideFilled: false, groupMin: null,
                                    liftMax: null, liftNoZone: false, hideNeedNone: false, hideNeedZone: false, hideNeedLift: false,
                                    favOnly: false};
/** The filters of the rigging classes, in needClass's order. */
export const NEED_FILTERS = ["hideNeedNone", "hideNeedZone", "hideNeedLift"] as const;
const STORAGE_KEY = "findaline.filters";

export const dh = (l: LineValues) => Math.abs(l.e1 - l.e2);
export const lowerAnchor = (l: LineValues) => Math.min(l.e1, l.e2);
export const upperAnchor = (l: LineValues) => Math.max(l.e1, l.e2);
export const wallAngle = (l: LineValues) => Math.max(l.angle1, l.angle2);
const known = (v: number | null) => v === null ? NaN : v;  // NaN fails every limit
/** The prominence of the more (Math.max) or less (Math.min) prominent anchor; NaN if not known. */
export const prominence = (l: LineValues, pick: (a: number, b: number) => number) => pick(known(l.prom1), known(l.prom2));
export const drop = (l: LineValues) => Math.min(known(l.drop1), known(l.drop2));

/** The A-frame height a line needs as the filter reads it: with the run's zone, or without it; null: not known. */
export const liftNeed = (l: LineValues, noZone: boolean): number | null => {
  const v = noZone ? l.lift_no_zone : l.lift_needed;
  return typeof v === "number" ? v : null;
};

/** The rigging a line needs, as the head's "Why so many?" box counts it: 0 no no-fall zone and no A-frames
 *  (`lift_no_zone` 0), 1 the no-fall zone (`lift_no_zone` > 0, `lift_needed` 0), 2 A-frames (`lift_needed` > 0);
 *  null: a line without the values (a run without the zone and the A-frames). */
export function needClass(l: LineValues): 0 | 1 | 2 | null {
  if (typeof l.lift_needed !== "number") return null;
  if (l.lift_needed > 0) return 2;
  return typeof l.lift_no_zone === "number" && l.lift_no_zone > 0 ? 1 : 0;
}

/** Whether a line passes the filters (a Line, or a LineCursor on the columns: result/model.ts); `lift`: its run's A-frame height, the limit of "A-frame needed at most" while
 *  that is not set (with the switch "without the no-fall zone" on, the lines that need more without the zone go). */
export function passes(l: LineValues, f: Filters, lift?: number): boolean {
  if (f.liftMax !== null || f.liftNoZone) {
    const need = liftNeed(l, f.liftNoZone), max = f.liftMax ?? lift ?? Infinity;
    if (need !== null && need > max + 1e-9) return false;
  }
  if (f.hideNeedNone || f.hideNeedZone || f.hideNeedLift) {
    const k = needClass(l);
    if (k !== null && f[NEED_FILTERS[k]]) return false;
  }
  return (f.lenMin === null || l.len >= f.lenMin) && (f.lenMax === null || l.len <= f.lenMax) &&
    (f.clrMin === null || l.clr >= f.clrMin) &&
    (f.clrNMin === null || l.clrN === null || l.clrN >= f.clrNMin) &&
    (f.dhMax === null || dh(l) <= f.dhMax) && (f.elevMin === null || lowerAnchor(l) >= f.elevMin) &&
    (f.elevMax === null || upperAnchor(l) <= f.elevMax) &&
    (f.pctMin === null || l.pct1 === null || l.pct2 === null || Math.min(l.pct1, l.pct2) >= f.pctMin) &&
    (f.pctMax === null || l.pct1 === null || l.pct2 === null || Math.max(l.pct1, l.pct2) <= f.pctMax) &&
    (f.heightMin === null || l.hmax >= f.heightMin) && (f.meanMin === null || l.hmean >= f.meanMin) &&
    (f.highPctMin === null || l.highPct >= f.highPctMin) && (f.angleMax === null || wallAngle(l) <= f.angleMax) &&
    (f.promMin === null || prominence(l, Math.max) >= f.promMin) &&
    (f.promBothMin === null || prominence(l, Math.min) >= f.promBothMin) &&
    (f.dropMin === null || drop(l) >= f.dropMin) &&
    (f.water === "all" || (f.water === "water" ? l.water > 0 : l.water === 0)) &&
    (!f.hideFilled || l.filled === 0);
}

/** How many filters are set. */
export function active(f: Filters): number {
  return (Object.keys(NO_FILTERS) as (keyof Filters)[]).filter((k) => f[k] !== NO_FILTERS[k]).length;
}

export interface Range { min: number; max: number }

/** The ranges of the run's values the filters offer (null: no line has the value). */
export interface FilterRanges {
  len: Range | null;
  clr: Range | null;
  clrN: Range | null;
  dh: Range | null;
  elev: Range | null;
  elevHigh: Range | null;  // of the upper anchor
  pct: Range | null;       // of both anchors' percentiles (null: no line has them)
  hmax: Range | null;
  hmean: Range | null;
  highPct: Range | null;
  highAbove: number;  // m, the height of highPct
  angle: Range | null;
  prom: Range | null;
  drop: Range | null;
  group: Range | null;
  // a run with a no-fall zone or A-frames: its A-frame height and zone, the largest A-frame heights its lines need
  // with and without the zone (null: a run without the options)
  lift: {lift: number; zone: number; needed: number; noZone: number} | null;
  water: boolean;   // some lines are over water
  filled: boolean;  // some lines are over filled gaps
  favourites: boolean;  // the user's favourite lines are known
}

/** Which lines are shown and how they are grouped. */
export interface LinesState {
  group: boolean;
  distance: number;
  by: string;
  showClean: boolean;
  showOver: boolean;
}

/** The range of values (for the sliders): `add` each, then `range`, null without values. A null value is left out,
 *  and so is NaN (no comparison takes it). */
export class Ranger {
  private min = Infinity;
  private max = -Infinity;
  add(v: number | null) {
    if (v === null) return;
    if (v < this.min) this.min = v;
    if (v > this.max) this.max = v;
  }
  get range(): Range | null {
    return this.min <= this.max ? {min: this.min, max: this.max} : null;
  }
}

/** The range of a value over the lines (for the sliders); null without lines. */
export function range<T>(lines: Iterable<T>, value: (l: T) => number | null): Range | null {
  const r = new Ranger();
  for (const l of lines) r.add(value(l));
  return r.range;
}

export function savedFilters(): Filters {
  try {
    return {...NO_FILTERS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"), favOnly: false,
            hideNeedNone: false, hideNeedZone: false, hideNeedLift: false};
  } catch {
    return {...NO_FILTERS};
  }
}

export function saveFilters(f: Filters) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(f));
  } catch {
    // storage blocked: the filters are just not kept
  }
}
