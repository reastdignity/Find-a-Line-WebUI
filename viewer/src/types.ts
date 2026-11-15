import type { Geometry } from "geojson";

// The data of one run, written by mapping.save_map into <run>/data.js
// (window.FINDALINE_RUN), and the list of runs in runs/runs.js (window.FINDALINE_RUNS).

export interface Rigging {
  pretension: number;      // kN
  stretch: number;         // % at 10 kN
  webbing_weight: number;  // g/m
  athlete_mass: number;    // kg
  fall_zone: number;       // m
}

/** Terrain profile of a line (helpers.line_profile). */
export interface Profile {
  d: number[];                    // distance from anchor 1, m
  z: (number | null)[];           // terrain
  s?: (number | null)[] | null;   // trees/buildings
  w?: number[] | null;            // 1: water
  g?: number[] | null;            // 1: filled gap
  min: [number, number];          // (distance, clearance) of the smallest clearance over terrain
  min_nmpt?: [number, number] | null;
  max_height?: [number, number];  // (distance, height) of the webbing highest above the terrain
  water_m: number;
  filled_m: number;
  // a profile made with the run's end zone or A-frames (helpers.line_profile): the zone's metres at each end
  // (min(end_zone, 0.25 · length), to 0.1 m) and the A-frame height; "min" is then the rule's smallest
  // clearance and "max_height" the webbing on the A-frames
  zone?: number;
  lift?: number;
}

// One line as an array (compact):
// [lat1, lon1, lat2, lon2, x1, y1, x2, y2, length, clearance, clearance_nmpt, elev1, elev2, over,
//  metres over water, metres over filled gaps, largest and mean height of the webbing above the
//  terrain, % of the line at least high_above, wall angle at anchor 1 and 2 (degrees from the
//  downslope direction), prominence of anchor 1 and 2, drop below anchor 1 and 2 (null: not
//  known), then the values its head's `ends` names (in a run with an end zone or A-frames END_VALUES, in a
//  run made with the square rule STANDS_FOR last), profile] (lines.js leaves out the profile)
export type LineRow = [number, number, number, number, number, number, number, number, number, number,
  number | null, number, number, boolean, number, number, number, number, number, number, number,
  number | null, number | null, number | null, number | null, ...(number | Profile | null)[]];

/** The values of a row before its profile (LineRow: after the drop below anchor 2). */
const ROW_VALUES = 25;
/** The extra values of a run with an end zone or A-frames, in the order its head's `ends` gives them
 *  (helpers.END_VALUES): the A-frame height each line needs with the run's zone, and without a zone. */
export const END_VALUES = ["lift_needed", "lift_no_zone"];
/** The last of a head's `ends` in a run made with the square rule (--same-line-square; runs.STANDS_FOR): the
 *  found lines between the same two anchor squares that the row's line stands for (itself among them). */
export const STANDS_FOR = "stands_for";

export interface Line {
  lat1: number; lon1: number; lat2: number; lon2: number;
  x1: number; y1: number; x2: number; y2: number;  // metres in the grid CRS, for grouping
  len: number; clr: number; clrN: number | null; e1: number; e2: number;
  over: boolean; water: number; filled: number;  // metres over water and over filled gaps
  hmax: number; hmean: number; highPct: number;  // webbing above the terrain (NaN: not known)
  angle1: number; angle2: number;  // degrees between the line and the downslope direction at the anchors
  prom1: number | null; prom2: number | null;  // prominence of the anchors, m
  drop1: number | null; drop2: number | null;  // drop below the anchors, m
  // percentile rank of each anchor's height in its run's search area (percentileRank; null: the run has no
  // terrain statistics). Derived in the browser: never saved with a favourite
  pct1: number | null; pct2: number | null;
  // the A-frame height (m, both ends) the line needs with its run's end zone, and without a zone (it may
  // exceed the run's A-frames: the line then needs the zone); null or missing: a run without the options
  lift_needed?: number | null; lift_no_zone?: number | null;
  // the found lines this line stands for (the square rule: one line kept per pair of anchor squares); null or
  // missing: a run without the rule. Not saved with a favourite
  stands_for?: number | null;
  prof: Profile | null;
  run?: OtherRun;  // set for the lines of another run
}

/** A line's values without its profile and run: what the filters, the list's keys and the ranking read, from a
 *  Line or from a LineCursor on the columns. */
export type LineValues = Omit<Line, "prof" | "run">;

/** Another run shown with this one ("Other runs"). */
export interface OtherRun {
  info: RunInfo;
  color: string;
}

/** The terrain of a run's search area (hypsometry.statistics): the heights of its land with data. */
export interface Terrain {
  mean: number;         // m
  quantiles: number[];  // 101: quantiles[p] the lower edge (0.1 m) of the first bin holding p % of the land
  km2: number;          // land with data
}

/** <run>/lines.js: window.FINDALINE_LINES[id], the lines without profiles. */
export interface RunLines {
  crs: string;
  area: Geometry;
  terrain?: Terrain | null;  // runs saved before 2026-11-03 have none
  ends?: string[];  // the names of the rows' values before the profile (RunData.ends)
  square?: number;  // RunData.square
  found?: number;   // RunData.found
  lines: LineRow[];  // without the profile at the end
}

export interface Ortho {
  name: string;
  url: string | null;   // WMS; null: the base tiles only
  layer: string;
  attribution: string;
  attribution_url?: string;  // a link for the attribution (OrthoService.attribution_url; maps of before have none)
  wms_version?: string;  // "1.1.1": the WMS takes EPSG:4326 in lon-lat order only (OrthoService.wms_version); none: 1.3.0
  wms_crs?: string;  // "EPSG:3857": the WMS is asked in Web Mercator (OrthoService.wms_crs); none: EPSG:4326
  // tiles ({z}/{x}/{y}) with full coverage under the WMS, where it has no imagery (the WMS
  // is then requested as a transparent PNG; cached tiles have both already), or the
  // orthophoto itself without a WMS
  base: {url: string; max_zoom: number} | null;
  cache: string | null; // {z}/{x}/{y}.jpg folder relative to the map, or null
}

/** Licence and notice of a dataset a run used (sources.Credit; run.json "attribution"). */
export interface Credit {
  data: string;
  attribution: string;  // plain text
  licence: string;
  url: string;          // of the licence or terms, may be ""
  notice: string;       // more for ATTRIBUTION.txt (citation, disclaimer)
}

/** run.json's block `store` (linestore.write): the run keeps its lines as an Arrow store (lines.arrow, profiles.arrow),
 *  which the page reads (result/load.ts); a run without it (saved before 2026-11-15, or whose store failed or was
 *  left by a stopped save) is read from its data.js. */
export interface StoreInfo {
  format: number;  // linestore.FORMAT; a page reads up to load.ts STORE_FORMAT
  lines: number;
  bytes: number;   // lines.arrow and profiles.arrow
  sha256: string;  // of lines.arrow, its first 16 hex digits
}

export interface RunInfo {
  id: string;
  name: string;
  created: string;
  description: string;
  has_map?: boolean;
  has_lines?: boolean;  // lines.arrow or lines.js (runs.list_runs)
  center?: {lat: number; lon: number};
  bbox?: [number, number, number, number] | null;  // west, south, east, north
  store?: StoreInfo;    // in runs.js (runs._listed keeps run.json's block)
}

export type ShoreKind = "surface" | "sea";

/** A segment of the uncertain shore (sources.filling.shore_segments, shore.ts): where the terrain model had no
 *  data at the foot of the shore, the face taken from the surface model ("surface") or the sea fill standing
 *  in for it ("sea"); `m` about its length along the shore, `ring` its outline as lon, lat. */
export interface ShoreSegment { kind: ShoreKind; px: number; m: number; ring: [number, number][] }

export interface Shore {
  rim_min: number;  // m: the sea fill next to terrain standing more than this above it is "sea"
  segments: ShoreSegment[];
  totals: Record<string, number>;  // surface_m, sea_m, surface_px, sea_px
}

/** Where the terrain of a run's land came from (sources.filling.terrain_origins, coarser.ts): each layer's share of
 *  the land (the source's own data, the neighbours', each fallback's) and the regions the fallbacks filled, each an
 *  outline with its holes as lon, lat (`layer` its index in `layers`). */
export interface TerrainLayer { role: "source" | "neighbour" | "fallback"; name: string; resolution: number | null; share: number }
export interface CoarserRegion { layer: number; km2: number; rings: [number, number][][] }
export interface TerrainSources {
  land_km2: number;
  fallback_share: number;  // the fallbacks' share of the land
  layers: TerrainLayer[];
  regions: CoarserRegion[];  // the largest first, the small ones left out (counted in totals)
  totals: {fallback_km2: number; listed_km2: number};
}

/** A run's head: everything of its data.js but the lines. */
export interface RunHead {
  run: RunInfo;
  center: [number, number];
  area: Geometry;
  crs: string;                    // of x1, y1, x2, y2
  ortho: Ortho | null;
  attribution?: Credit[];         // the data used; runs saved before 2026-10-27 have none
  distance: number;               // grouping distance, m
  by: "clearance" | "longest" | "height";
  model: "formula" | "sag";
  rigging: Rigging;
  slope: number;                  // formula: metres of drop per metre from the nearer anchor
  leash_fall: number;
  high_above: number;             // m: from this height above the terrain a part of a line is high
  max_zoom: number;
  terrain?: Terrain | null;       // runs saved before 2026-11-03 have none
  shore?: Shore | null;           // the uncertain shore; runs saved before 2026-11-05 have none
  terrain_sources?: TerrainSources;  // where the land's terrain came from; only when something was filled
  end_zone?: number;              // m: the run's no-fall zone at the ends (none: off)
  lift?: number;                  // m: the run's A-frame height (none: off)
  ends?: string[];                // the names of the rows' values before the profile (END_VALUES, STANDS_FOR); none: no such
  square?: number;                // m: the side of the anchor squares of a run made with the square rule (none: off)
  found?: number;                 // the lines such a run found, which its lines stand for (the sum of their counts)
}

/** data.js's value (window.FINDALINE_RUN) as the file holds it: the head and a row per line. */
export interface RunScript extends RunHead {
  lines: LineRow[];
}

/** A run as the page keeps it (result/load.ts): the head and its lines as columns (lineColumns), the rows dropped. */
export interface RunData extends RunHead {
  columns: LineColumns;
}

declare global {
  interface Window {
    FINDALINE_RUN?: RunScript;
    FINDALINE_RUNS?: RunInfo[];
    FINDALINE_LINES?: Record<string, RunLines>;
    // Set by the server's runs.js (web.py): whether this map may compute profiles and measure, and mark
    // favourite lines (the public site; undefined: from disk no, from a local server yes), and the
    // operator's key of the satellite map (esri_key: settings.WebKeys; none from disk)
    FINDALINE_APP?: {profiles?: boolean; favourites?: boolean; esri_key?: string};
  }
}

/** The percentile rank of height z among quantiles q: the largest p with q[p] <= z, 0 below q[0]
 * (hypsometry.statistics' bins: exactly floor(100 * share of the land at or below z's bin)). */
export function percentileRank(z: number, q: number[]): number {
  if (!(z >= q[0])) return 0;
  let lo = 0, hi = q.length - 1;  // q[lo] <= z
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (q[mid] <= z) lo = mid; else hi = mid - 1;
  }
  return lo;
}

/** A row of data.js or lines.js as a Line. The profile is the row's last value when that is an object or
 *  null (data.js; lines.js has none); the values between the drop below anchor 2 and it are named by `ends`
 *  (the run's head; a row longer than ROW_VALUES read without it takes END_VALUES, the only such values). */
export function toLine(d: LineRow, run?: OtherRun, terrain?: Terrain | null, ends: string[] = END_VALUES): Line {
  const q = terrain ? terrain.quantiles : null;
  const last = d.length > ROW_VALUES ? d[d.length - 1] : undefined;
  const profiled = last === null || typeof last === "object";
  const extras = d.slice(ROW_VALUES, profiled ? d.length - 1 : d.length);
  const extra = (name: string): number | null => {
    const at = extras.length ? ends.indexOf(name) : -1;
    const value = at >= 0 && at < extras.length ? extras[at] : null;
    return typeof value === "number" ? value : null;
  };
  return {lat1: d[0], lon1: d[1], lat2: d[2], lon2: d[3], x1: d[4], y1: d[5], x2: d[6], y2: d[7],
          len: d[8], clr: d[9], clrN: d[10], e1: d[11], e2: d[12], over: d[13], water: d[14], filled: d[15],
          hmax: d[16], hmean: d[17], highPct: d[18], angle1: d[19], angle2: d[20], prom1: d[21], prom2: d[22],
          drop1: d[23], drop2: d[24],
          pct1: q ? percentileRank(d[11], q) : null, pct2: q ? percentileRank(d[12], q) : null,
          lift_needed: extra("lift_needed"), lift_no_zone: extra("lift_no_zone"), stands_for: extra(STANDS_FOR),
          prof: profiled ? (last as Profile | null) || null : null, run};
}

// --- A run's lines as columns (docs/line-volume/spec-store.md 1.2: store wave 1) ---
// The page keeps a run's lines as one typed array per value, not as an object per line: lineColumns reads them from
// data.js's or lines.js's rows, which are dropped then. A Line is made (lineAt) only for a line the page draws, lists,
// selects, opens or saves as a favourite; the filters, the grouping and the counts read the columns through a
// LineCursor. Every value reads back as the very double the row held (null, NaN and a value past a short row's end
// as toLine gives them), so the page shows the same numbers and keys.lineCoords gives the same keys as from the rows.
// One difference: a row of before 2026-10-27 has its profile where `hmax` is now, which toLine reads as `hmax` (an
// object) and the columns as NaN, which compares, groups, filters and shows ("–") as that object does.
// A run with a store (store wave 2) gets the same columns from it without a copy (storedColumns): NumberColumn over
// the store's own arrays, its missing values from their validity bits.

type IntArray = Int8Array | Int16Array | Int32Array;
/** An integer array of a store's column: int8/16/32 of value × 10^decimals, uint32 of a count (linestore.COLUMNS). */
type StoredInts = IntArray | Uint32Array;
const INT32_MAX = 2147483647;
// What an integer array of a column keeps instead of a number, from its type's smallest value on: null, NaN, and a
// value the row does not have (undefined, as toLine reads a value past a short row's end: the runs saved before
// 2026-10-27 have 16 values); its numbers start above them
const NULL = 0, NAN = 1, MISSING = 2, CODES = 3;

/** The smallest value of an integer array of a column (its code of null). */
const lowest = (values: IntArray) => values instanceof Int8Array ? -128 : values instanceof Int16Array ? -32768
  : -INT32_MAX - 1;

/** One value of every line: `values[i] / scale` in the narrowest integer array that holds every value exactly
 *  (null, NaN and a missing value as the array's three smallest numbers; `negZero` the rows of a -0), or the values
 *  themselves in a Float64Array (scale 0; NaN as it is, null where `nulls` is 1, missing where it is 2). `at` gives
 *  back the value the row held: the very double, null, NaN, or undefined for a value past the row's end.
 *  A store's column (NumberColumn.stored) has no such codes: every number of its array is a value, and a missing
 *  one is a 0 bit of `valid` (Arrow's validity bits), read as `missing` (null or NaN, as data.js shows it). */
export class NumberColumn {
  private readonly code: number;
  constructor(readonly values: Float64Array | StoredInts, readonly scale: number, readonly nulls: Uint8Array | null = null,
              readonly negZero: Set<number> | null = null, readonly valid: Uint8Array | null = null,
              readonly missing: number | null = null, coded = true) {
    this.code = scale && coded ? lowest(values as IntArray) : -Infinity;
  }

  /** A store's column: `values` as they are (no codes), `valid` its validity bits (null: none missing). */
  static stored(values: Float64Array | StoredInts, scale: number, valid: Uint8Array | null, missing: number | null,
                nulls: Uint8Array | null = null, negZero: Set<number> | null = null): NumberColumn {
    return new NumberColumn(values, scale, nulls, negZero, valid, missing, false);
  }

  at(i: number): number | null {
    if (this.valid !== null && (this.valid[i >> 3] & (1 << (i & 7))) === 0) return this.missing;
    const v = this.values[i];
    if (this.scale === 0) {
      const mark = this.nulls !== null ? this.nulls[i] : 0;
      return mark === 0 ? v : mark === 1 ? null : undefined as unknown as number;
    }
    if (v < this.code + CODES) return v === this.code + NULL ? null : v === this.code + NAN ? NaN : undefined as unknown as number;
    if (v === 0 && this.negZero !== null && this.negZero.has(i)) return -0;
    return v / this.scale;
  }
}

/** A NumberColumn filled value by value: as integers of `scale` (0: a Float64Array) while every value is one exactly
 *  (k / scale is the very double), else as doubles from then on; `finish` narrows the integers to Int16 or Int8 when
 *  they fit. `undefined` is a value the row does not have; anything else that is not a number is null (toLine's
 *  extra values; the rows hold numbers or null). */
class ColumnBuilder {
  private ints: Int32Array | null;
  private floats: Float64Array | null;
  private nulls: Uint8Array | null = null;
  private negZero: Set<number> | null = null;
  private min = Infinity;
  private max = -Infinity;
  private static readonly LOW = -INT32_MAX - 1;  // the Int32 codes: LOW + NULL, + NAN, + MISSING

  constructor(private readonly n: number, private readonly scale: number) {
    this.ints = scale ? new Int32Array(n) : null;
    this.floats = scale ? null : new Float64Array(n);
  }

  set(i: number, v: unknown) {
    if (typeof v !== "number") {
      const code = v === undefined ? MISSING : NULL;
      if (this.ints) this.ints[i] = ColumnBuilder.LOW + code;
      else { this.floats![i] = NaN; (this.nulls ??= new Uint8Array(this.n))[i] = code === NULL ? 1 : 2; }
      return;
    }
    if (this.ints) {
      if (v !== v) { this.ints[i] = ColumnBuilder.LOW + NAN; return; }
      const k = Math.round(v * this.scale);
      if (k / this.scale === v && k >= ColumnBuilder.LOW + CODES && k <= INT32_MAX) {
        this.ints[i] = k;
        if (k < this.min) this.min = k;
        if (k > this.max) this.max = k;
        if (k === 0 && 1 / v < 0) (this.negZero ??= new Set()).add(i);
        return;
      }
      this.toFloats(i);
    }
    this.floats![i] = v;
  }

  /** The integers before row `upTo` as doubles, and the doubles from then on. */
  private toFloats(upTo: number) {
    const ints = this.ints!, floats = new Float64Array(this.n), low = ColumnBuilder.LOW;
    for (let j = 0; j < upTo; j++) {
      const k = ints[j];
      if (k === low + NULL || k === low + MISSING) {
        floats[j] = NaN;
        (this.nulls ??= new Uint8Array(this.n))[j] = k === low + NULL ? 1 : 2;
      }
      else if (k === low + NAN) floats[j] = NaN;
      else floats[j] = k === 0 && this.negZero !== null && this.negZero.has(j) ? -0 : k / this.scale;
    }
    this.ints = null;
    this.floats = floats;
    this.negZero = null;
  }

  finish(): NumberColumn {
    const ints = this.ints, low = ColumnBuilder.LOW;
    if (!ints) return new NumberColumn(this.floats!, 0, this.nulls);
    for (const [make, top] of [[Int8Array, 127], [Int16Array, 32767]] as const) {
      if (this.min > this.max || (this.min >= -top - 1 + CODES && this.max <= top)) {
        const narrow = new make(this.n);
        for (let j = 0; j < this.n; j++) {
          const k = ints[j];
          narrow[j] = k < low + CODES ? -top - 1 + (k - low) : k;
        }
        return new NumberColumn(narrow, this.scale, null, this.negZero);
      }
    }
    return new NumberColumn(ints, this.scale, null, this.negZero);
  }
}

/** The values of a line kept as numbers (all of LineValues but `over`). */
export type NumberField = Exclude<keyof LineValues, "over">;

/** A run's saved profiles by row: data.js's (a Map), or the store's profiles.arrow, each made when it is asked for. */
export interface ProfileSource {
  get(row: number): Profile | undefined;
}

/** A run's lines as columns (lineColumns, storedColumns): a NumberColumn per value, `over` as 0/1, the saved
 *  profiles by row. */
export type LineColumns = {readonly [K in NumberField]: NumberColumn} & {
  readonly length: number;
  readonly over: Uint8Array;
  readonly profiles: ProfileSource;
};

// The values of a row (toLine) by their place, and the scale an integer column tries: the decimals mapping.map_rows
// writes (a value that is not exact at it makes its column doubles); 0: a value used for grouping, kept as doubles
const ROW_FIELDS: [NumberField, number, number][] = [
  ["lat1", 0, 1e7], ["lon1", 1, 1e7], ["lat2", 2, 1e7], ["lon2", 3, 1e7], ["x1", 4, 0], ["y1", 5, 0], ["x2", 6, 0],
  ["y2", 7, 0], ["len", 8, 0], ["clr", 9, 0], ["clrN", 10, 100], ["e1", 11, 100], ["e2", 12, 100], ["water", 14, 10],
  ["filled", 15, 10], ["hmax", 16, 0], ["hmean", 17, 100], ["highPct", 18, 10], ["angle1", 19, 10], ["angle2", 20, 10],
  ["prom1", 21, 10], ["prom2", 22, 10], ["drop1", 23, 10], ["drop2", 24, 10]];
const OVER = 13;
// The values a head's `ends` names (END_VALUES, then STANDS_FOR) and their scales
const EXTRA_FIELDS: [NumberField, number][] = [["lift_needed", 100], ["lift_no_zone", 100],
                                                     [STANDS_FOR as NumberField, 1]];

/** The rows of data.js or lines.js as columns, with the values toLine reads from each row: the anchors' percentile
 *  ranks from `terrain`, the values `ends` names, the profile (data.js) by its row. The rows are left as they are. */
export function lineColumns(rows: LineRow[], terrain?: Terrain | null, ends: string[] = END_VALUES): LineColumns {
  const n = rows.length, q = terrain ? terrain.quantiles : null;
  const values = ROW_FIELDS.map(([, , scale]) => new ColumnBuilder(n, scale));
  const extras = EXTRA_FIELDS.map(([name, scale]) => ({at: ends.indexOf(name), column: new ColumnBuilder(n, scale)}));
  const pct1 = new ColumnBuilder(n, 1), pct2 = new ColumnBuilder(n, 1);
  const over = new Uint8Array(n), profiles = new Map<number, Profile>();
  for (let i = 0; i < n; i++) {
    const d = rows[i];
    for (let f = 0; f < ROW_FIELDS.length; f++) {
      const v = d[ROW_FIELDS[f][1]];
      values[f].set(i, v !== null && typeof v === "object" ? NaN : v);  // a profile in a short row's place (above)
    }
    over[i] = d[OVER] ? 1 : 0;
    const last = d.length > ROW_VALUES ? d[d.length - 1] : undefined;
    const profiled = last === null || typeof last === "object";
    const extra = (profiled ? d.length - 1 : d.length) - ROW_VALUES;
    for (const x of extras) x.column.set(i, x.at >= 0 && x.at < extra ? d[ROW_VALUES + x.at] : null);
    if (profiled && last) profiles.set(i, last as Profile);
    pct1.set(i, q ? percentileRank(d[11], q) : null);
    pct2.set(i, q ? percentileRank(d[12], q) : null);
  }
  const columns: Record<string, unknown> = {length: n, over, profiles, pct1: pct1.finish(), pct2: pct2.finish()};
  ROW_FIELDS.forEach(([name], f) => { columns[name] = values[f].finish(); });
  EXTRA_FIELDS.forEach(([name], f) => { columns[name] = extras[f].column.finish(); });
  return columns as LineColumns;
}

/** A column of a run's store as result/load.ts reads it: its array as the file holds it (no copy), the scale
 *  10^decimals (the field's `decimals`; 0: float64 as it is), its validity bits (null: none missing) and the rows
 *  of a -0 (the store's `negative_zero`). */
export interface StoredColumn {
  values: Float64Array | StoredInts;
  scale: number;
  valid: Uint8Array | null;
  negZero: number[];
}

// The values data.js writes as null when they miss (mapping.map_rows' empty_nan: clrN, prom1/2, drop1/2), so toLine
// reads null; any other value that misses (hmean, highPct, angle1/2: null in the store; e1 in a float64 column) is
// NaN in data.js. A store's missing value reads as data.js shows it.
export const NULL_WHEN_MISSING: readonly NumberField[] = ["clrN", "prom1", "prom2", "drop1", "drop2"];

/** A run's lines as columns from its store (linestore.COLUMNS by name, `n` rows): the same values lineColumns
 *  gives the run's data.js rows, read from the store's own arrays, the anchors' percentile ranks from `terrain`; a
 *  value of `ends` the store does not hold reads null, as toLine reads it. */
export function storedColumns(n: number, stored: Map<string, StoredColumn>, over: Uint8Array,
                              terrain: Terrain | null | undefined, profiles: ProfileSource): LineColumns {
  const columns: Record<string, unknown> = {length: n, over, profiles};
  const none = new Uint8Array((n + 7) >> 3);  // every bit 0: a column the store does not hold (`ends`), all null
  for (const name of [...ROW_FIELDS.map(([name]) => name), ...EXTRA_FIELDS.map(([name]) => name)]) {
    const c = stored.get(name);
    const asNull = NULL_WHEN_MISSING.includes(name);
    if (!c) {
      if (ROW_FIELDS.some(([field]) => field === name)) throw new Error(`the run's store has no column ${name}`);
      columns[name] = NumberColumn.stored(new Int8Array(0), 1, none, null);
      continue;
    }
    let nulls: Uint8Array | null = null;
    if (c.scale === 0 && asNull) {  // a float64 column of a value data.js writes as null when NaN
      const v = c.values;
      for (let i = 0; i < n; i++) if (v[i] !== v[i]) (nulls ??= new Uint8Array(n))[i] = 1;
    }
    columns[name] = NumberColumn.stored(c.values, c.scale, c.valid, asNull ? null : NaN, nulls,
                                        c.negZero.length ? new Set(c.negZero) : null);
  }
  const q = terrain ? terrain.quantiles : null, e1 = columns.e1 as NumberColumn, e2 = columns.e2 as NumberColumn;
  const pct1 = new ColumnBuilder(n, 1), pct2 = new ColumnBuilder(n, 1);
  for (let i = 0; i < n; i++) {
    pct1.set(i, q ? percentileRank(e1.at(i) as number, q) : null);
    pct2.set(i, q ? percentileRank(e2.at(i) as number, q) : null);
  }
  columns.pct1 = pct1.finish();
  columns.pct2 = pct2.finish();
  return columns as LineColumns;
}

/** Line `i` of the columns, with the values toLine gives its row (`run`: set for the lines of another run). */
export function lineAt(c: LineColumns, i: number, run?: OtherRun): Line {
  const v = (column: NumberColumn) => column.at(i) as number;
  return {lat1: v(c.lat1), lon1: v(c.lon1), lat2: v(c.lat2), lon2: v(c.lon2), x1: v(c.x1), y1: v(c.y1), x2: v(c.x2),
          y2: v(c.y2), len: v(c.len), clr: v(c.clr), clrN: c.clrN.at(i), e1: v(c.e1), e2: v(c.e2), over: c.over[i] === 1,
          water: v(c.water), filled: v(c.filled), hmax: v(c.hmax), hmean: v(c.hmean), highPct: v(c.highPct),
          angle1: v(c.angle1), angle2: v(c.angle2), prom1: c.prom1.at(i), prom2: c.prom2.at(i), drop1: c.drop1.at(i),
          drop2: c.drop2.at(i), pct1: c.pct1.at(i), pct2: c.pct2.at(i), lift_needed: c.lift_needed.at(i),
          lift_no_zone: c.lift_no_zone.at(i), stands_for: c.stands_for.at(i), prof: c.profiles.get(i) ?? null, run};
}

/** The values of line `i` of the columns, read as they are asked for (no Line made): the filters, the ranges, the
 *  ranking and the counts go through the lines with one cursor, moved by setting `i` (and `c`). */
export class LineCursor implements LineValues {
  i = 0;
  constructor(public c: LineColumns) {}
  get lat1() { return this.c.lat1.at(this.i) as number; }
  get lon1() { return this.c.lon1.at(this.i) as number; }
  get lat2() { return this.c.lat2.at(this.i) as number; }
  get lon2() { return this.c.lon2.at(this.i) as number; }
  get x1() { return this.c.x1.at(this.i) as number; }
  get y1() { return this.c.y1.at(this.i) as number; }
  get x2() { return this.c.x2.at(this.i) as number; }
  get y2() { return this.c.y2.at(this.i) as number; }
  get len() { return this.c.len.at(this.i) as number; }
  get clr() { return this.c.clr.at(this.i) as number; }
  get clrN() { return this.c.clrN.at(this.i); }
  get e1() { return this.c.e1.at(this.i) as number; }
  get e2() { return this.c.e2.at(this.i) as number; }
  get over() { return this.c.over[this.i] === 1; }
  get water() { return this.c.water.at(this.i) as number; }
  get filled() { return this.c.filled.at(this.i) as number; }
  get hmax() { return this.c.hmax.at(this.i) as number; }
  get hmean() { return this.c.hmean.at(this.i) as number; }
  get highPct() { return this.c.highPct.at(this.i) as number; }
  get angle1() { return this.c.angle1.at(this.i) as number; }
  get angle2() { return this.c.angle2.at(this.i) as number; }
  get prom1() { return this.c.prom1.at(this.i); }
  get prom2() { return this.c.prom2.at(this.i); }
  get drop1() { return this.c.drop1.at(this.i); }
  get drop2() { return this.c.drop2.at(this.i); }
  get pct1() { return this.c.pct1.at(this.i); }
  get pct2() { return this.c.pct2.at(this.i); }
  get lift_needed() { return this.c.lift_needed.at(this.i); }
  get lift_no_zone() { return this.c.lift_no_zone.at(this.i); }
  get stands_for() { return this.c.stands_for.at(this.i); }
}

/** A run as the page keeps it: data.js's head and its rows as columns (the caller drops the rows). */
export function runData(script: RunScript): RunData {
  const {lines, ...head} = script;
  return {...head, columns: lineColumns(lines, script.terrain, script.ends)};
}
