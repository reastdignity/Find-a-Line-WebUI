// The rows of a run's data.js and lines.js (window.FINDALINE_RUN, window.FINDALINE_LINES[id]) as the page read them
// before store wave 4's item 5, kept for the tests only (the page reads a run from its store alone): the Node units
// make up runs as rows (`made()`, the clip's rows of tests/old_scripts.py's frozen writer) and read them into the
// same columns the store gives (storedColumns), the reference of test_columns_give_the_rows_values.

import { ACCESS, ColumnBuilder, END_VALUES, EXTRA_FIELDS, OVER, percentileRank, ROW_FIELDS, ROW_VALUES, STANDS_FOR,
         type Line, type LineColumns, type OtherRun, type Profile, type RunData, type RunHead, type Terrain } from "../src/types";
import type { Geometry } from "geojson";

// One line as an array (compact):
// [lat1, lon1, lat2, lon2, x1, y1, x2, y2, length, clearance, clearance_nmpt, elev1, elev2, over,
//  metres over water, metres over filled gaps, largest and mean height of the webbing above the
//  terrain, % of the line at least high_above, wall angle at anchor 1 and 2 (degrees from the
//  downslope direction), prominence of anchor 1 and 2, drop below anchor 1 and 2 (null: not
//  known), then the values its head's `ends` names (in a run with an end zone or A-frames END_VALUES, in a
//  run made with the access mark ACCESS, in a run made with the square rule STANDS_FOR last), profile]
//  (lines.js leaves out the profile)
export type LineRow = [number, number, number, number, number, number, number, number, number, number,
  number | null, number, number, boolean, number, number, number, number, number, number, number,
  number | null, number | null, number | null, number | null, ...(number | Profile | null)[]];


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

/** data.js's value (window.FINDALINE_RUN) as the file holds it: the head and a row per line. */
export interface RunScript extends RunHead {
  lines: LineRow[];
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
          access1: extra(ACCESS[0]), access2: extra(ACCESS[1]),
          prof: profiled ? (last as Profile | null) || null : null, run};
}

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

/** A run as the page keeps it: data.js's head and its rows as columns (the caller drops the rows). */
export function runData(script: RunScript): RunData {
  const {lines, ...head} = script;
  return {...head, columns: lineColumns(lines, script.terrain, script.ends)};
}
