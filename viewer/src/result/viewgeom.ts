// The result view's pure parts (docs/line-volume/spec-view.md B.2): the level the zoom gives, whether a line crosses
// the view, the squares of the Area level and their classes, a direction's word, and the fit between a run's grid
// and the map. Plain TypeScript without the DOM or Leaflet, so tests run it under Node (tests/test_view_units.py).
//
// Everything here is in the run's grid metres (x east, y north, as the lines' anchors are stored): the view is the
// map's visible part taken into the grid by the fit (a Quad: on the web map the grid stands slightly turned), a
// square is a cell of the grid.

import type { LineColumns } from "../types";
import type { SpotView } from "./spots";

/** How much the map draws: squares, one line per spot, or the lines of the best spots. */
export type Level = "area" | "spots" | "lines";
export type Point = readonly [number, number];
/** A convex four-sided area in grid metres: its corners in order around it (either way round). */
export type Quad = readonly [Point, Point, Point, Point];
/** What the squares of the Area level show: the spots or the lines anchored in a square, the best clearance or the
 *  longest line among them (B.2 item 3). */
export type SquareBy = "spots" | "lines" | "clr" | "len";

/** Above this many thin lines the Lines level draws none (B.2 item 7); the rows and the far ends "Lines from here"
 *  shows at most; its reach around the point and the distance within which far ends form one row, m; how far apart
 *  the middles of two picks of "Start here" lie at least, m; the rows of "In view" with All at most. */
export const LIMIT = 5000, FAN_MAX = 40, FAN_HERE = 10, FAN_GROUP = 20, PICK_APART = 100, BEST_ROWS = 100;
/** Auto: Area above AUTO_AREA metres per pixel, Lines below AUTO_LINES, Spots between; a level changes only once the
 *  zoom is AUTO_BAND beyond a threshold. */
export const AUTO_AREA = 2, AUTO_LINES = 0.6, AUTO_BAND = 0.07;
/** A square's side, m, and the pixels the smallest drawn side has at least. */
export const SQUARE_SIDES = [25, 50, 100, 200] as const, SQUARE_PX = 26;

/** The level Auto shows at `mpp` metres per pixel when it shows `now`: it enters a level only below 0.93 of the
 *  threshold and leaves it only above 1.07 of it. `now` null (Auto just pressed, or the first view): the level of
 *  the zoom itself, without the band. */
export function autoLevel(mpp: number, now: Level | null): Level {
  const hi = AUTO_AREA, lo = AUTO_LINES, enter = 1 - AUTO_BAND, leave = 1 + AUTO_BAND;
  if (now === null) return mpp > hi ? "area" : mpp > lo ? "spots" : "lines";
  if (now === "area") return mpp < hi * enter ? (mpp < lo * enter ? "lines" : "spots") : "area";
  if (now === "spots") return mpp > hi * leave ? "area" : mpp < lo * enter ? "lines" : "spots";
  return mpp > lo * leave ? (mpp > hi * leave ? "area" : "spots") : "lines";
}

/** A test "does the segment (x1, y1)-(x2, y2) cross `r`" for many segments: more than a point of it lies in `r`
 *  (a segment that only touches a corner or an edge at one point does not cross; one along an edge does). */
export function clipper(r: Quad): (x1: number, y1: number, x2: number, y2: number) => boolean {
  let area = 0;
  for (let k = 0; k < 4; k++) {
    const a = r[k], b = r[(k + 1) % 4];
    area += a[0] * b[1] - b[0] * a[1];
  }
  const sign = area >= 0 ? 1 : -1;
  // each edge as (ax, ay, ex, ey), the inside on its left once `sign` is applied
  const e = new Float64Array(16);
  for (let k = 0; k < 4; k++) {
    const a = r[k], b = r[(k + 1) % 4];
    e[4 * k] = a[0]; e[4 * k + 1] = a[1]; e[4 * k + 2] = sign * (b[0] - a[0]); e[4 * k + 3] = sign * (b[1] - a[1]);
  }
  return (x1, y1, x2, y2) => {
    let t0 = 0, t1 = 1;
    const dx = x2 - x1, dy = y2 - y1;
    for (let k = 0; k < 16; k += 4) {
      const ex = e[k + 2], ey = e[k + 3];
      const q = ex * (y1 - e[k + 1]) - ey * (x1 - e[k]);  // how far inside this edge the start lies
      const p = ex * dy - ey * dx;                         // and how that grows along the segment
      if (p === 0) {
        if (q < 0) return false;
        continue;
      }
      const t = -q / p;
      if (p > 0) { if (t > t1) return false; if (t > t0) t0 = t; }
      else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
    return t1 > t0;
  };
}

/** Does the segment (x1, y1)-(x2, y2) cross the view `r` (clipper: strict, a touch does not). */
export function crosses(x1: number, y1: number, x2: number, y2: number, r: Quad): boolean {
  return clipper(r)(x1, y1, x2, y2);
}

/** The side of the squares at `mpp` metres per pixel: the smallest whose side is at least 26 px, else 200 m. */
export function squareSide(mpp: number): 25 | 50 | 100 | 200 {
  for (const side of SQUARE_SIDES) if (side / mpp >= SQUARE_PX) return side;
  return 200;
}

/** The squares of one side that hold an anchor of a passing line: cell (i, j) spans x0 + i·side … and y0 + j·side …
 *  (the grid's cells from (0, 0), as the mock-up counts); `cells` the squares as j·nx + i, ascending, `values` the
 *  value of `by` in each. */
export interface SquareGrid {
  side: number;
  by: SquareBy;
  x0: number; y0: number;
  nx: number; ny: number;
  cells: Uint32Array;
  values: Float64Array;
}

interface Counted { version: number; side: number; x0: number; y0: number; nx: number; ny: number; cells: Uint32Array;
                    spots: Float64Array; lines: Float64Array; clr: Float64Array; len: Float64Array }
const counted = new WeakMap<SpotView, Counted>();
const DENSE_CELLS = 1 << 24;  // a typed index of the box's cells up to this many, a Map above (a very wide run)

function countSquares(v: SpotView, side: number): Counted {
  const box = v.model.data.box, {x1, y1, x2, y2, clr, len} = v.values;
  const ix0 = box ? Math.floor(box[0] / side) : 0, iy0 = box ? Math.floor(box[1] / side) : 0;
  const nx = box ? Math.floor(box[2] / side) - ix0 + 1 : 0, ny = box ? Math.floor(box[3] / side) - iy0 + 1 : 0;
  const dense = nx * ny <= DENSE_CELLS ? new Int32Array(nx * ny).fill(-1) : null, sparse = new Map<number, number>();
  let size = 0, room = 1024;
  let cell = new Uint32Array(room), spots = new Float64Array(room), lines = new Float64Array(room);
  let best = new Float64Array(room), longest = new Float64Array(room), last = new Int32Array(room);
  const grow = () => {
    const more = <T extends Uint32Array | Float64Array | Int32Array>(a: T): T => {
      const b = new (a.constructor as new (n: number) => T)(room * 2);
      b.set(a);
      return b;
    };
    cell = more(cell); spots = more(spots); lines = more(lines); best = more(best); longest = more(longest); last = more(last);
    room *= 2;
  };
  /** The slot of the square holding (x, y), with the line `row` of `spot` counted in it; -1 outside the box. */
  const add = (x: number, y: number, row: number, spot: number, skip: number): number => {
    const i = Math.floor(x / side) - ix0, j = Math.floor(y / side) - iy0;
    if (!(i >= 0 && i < nx && j >= 0 && j < ny)) return -1;
    const key = j * nx + i;
    let at = dense ? dense[key] : sparse.get(key) ?? -1;
    if (at === skip) return at;  // both anchors in one square: the line counts once
    if (at < 0) {
      if (size === room) grow();
      at = size++;
      if (dense) dense[key] = at; else sparse.set(key, at);
      cell[at] = key; best[at] = -Infinity; last[at] = -1;
    }
    if (last[at] !== spot) { last[at] = spot; spots[at]++; }
    lines[at]++;
    if (clr[row] > best[at]) best[at] = clr[row];
    if (len[row] > longest[at]) longest[at] = len[row];
    return at;
  };
  for (let spot = 0; spot < v.spotCount; spot++) {  // spot by spot, so a spot is counted once per square
    const rows = v.linesOf(spot);
    for (let k = 0; k < rows.length; k++) {
      const row = rows[k];
      if (!v.passes(row)) continue;
      const first = add(x1[row], y1[row], row, spot, -2);
      add(x2[row], y2[row], row, spot, first);
    }
  }
  const order = Array.from({length: size}, (_, k) => k).sort((a, b) => cell[a] - cell[b]);
  const take = (a: Float64Array) => Float64Array.from(order, (k) => a[k]);
  return {version: v.version, side, x0: ix0 * side, y0: iy0 * side, nx, ny, cells: Uint32Array.from(order, (k) => cell[k]),
          spots: take(spots), lines: take(lines), clr: take(best), len: take(longest)};
}

/** The squares of `side` metres of the lines that pass the filters now: a line counts in the squares of both its
 *  anchors (once when both lie in one), a spot once per square. Counted once per change of the filters and side
 *  (kept for the view's `version`), so another `by` costs nothing. */
export function squareValues(v: SpotView, side: number, by: SquareBy): SquareGrid {
  let c = counted.get(v);
  if (!c || c.version !== v.version || c.side !== side) {
    c = countSquares(v, side);
    counted.set(v, c);
  }
  return {side, by, x0: c.x0, y0: c.y0, nx: c.nx, ny: c.ny, cells: c.cells, values: c[by]};
}

/** The slot in `grid.cells` of the square holding (x, y), else -1. */
export function squareAt(grid: SquareGrid, x: number, y: number): number {
  const i = Math.floor((x - grid.x0) / grid.side), j = Math.floor((y - grid.y0) / grid.side);
  if (!(i >= 0 && i < grid.nx && j >= 0 && j < grid.ny)) return -1;
  const key = j * grid.nx + i, cells = grid.cells;
  let lo = 0, hi = cells.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (cells[mid] === key) return mid;
    if (cells[mid] < key) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}

/** The four breaks of the squares' five classes: evenly in log10 between the 2nd and the 98th percentile of the
 *  values above 0, each to two digits; `counts`: whole numbers, each above the one before. No value: 1, 2, 3, 4. */
export function breaks(values: Float64Array, counts: boolean): number[] {
  const ds = Array.from(values).filter((d) => d > 0).sort((a, b) => a - b);
  if (!ds.length) return [1, 2, 3, 4];
  const at = (q: number) => ds[Math.min(ds.length - 1, Math.floor(q * (ds.length - 1)))];
  const lo = Math.log10(at(0.02));
  let hi = Math.log10(at(0.98));
  if (hi <= lo + 0.2) hi = lo + 0.2;
  const out: number[] = [];
  for (let k = 1; k <= 4; k++) {
    const b = Number(Math.pow(10, lo + (hi - lo) * k / 5).toPrecision(2));
    out.push(counts ? Math.max(Math.round(b), (out[k - 2] || 0) + 1) : b);
  }
  return out;
}

/** The class 0 … 4 of a value under four breaks. */
export function classOf(v: number, b: number[]): number {
  let k = 0;
  for (let j = 0; j < 4; j++) if (v >= b[j]) k++;
  return k;
}

const WORDS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** The direction of (dx east, dy north): degrees clockwise from north, 0 … 360, and its word of eight. */
export function bearing(dx: number, dy: number): {deg: number; word: string} {
  const deg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
  return {deg, word: WORDS[Math.round(deg / 45) % 8]};
}

// --- the fit between the run's grid and the map ---

/** A run's grid metres from latitudes and longitudes and back: one affine map fitted to the run's anchors, which
 *  are stored both ways (no projection library in the page). `residual`: the farthest any anchor's stored grid
 *  place lies from the fit's of its latitude and longitude, m; `rms` their root mean square; `anchors` how many
 *  were fitted; `turn` the grid north's direction on the map, degrees clockwise from true north. */
export interface GridFit {
  toGrid(lat: number, lon: number): [number, number];
  toLatLng(x: number, y: number): [number, number];
  residual: number;
  rms: number;
  anchors: number;
  turn: number;
}

const DEG = Math.PI / 180, EARTH = 6371008.8;

/** The fit of a run's lines (GridFit): least squares over both anchors of every line, about their means (so the
 *  large numbers cancel). Anchors on one straight line (a run of one line) cannot give a turned and stretched grid:
 *  the fit is then a turn and one scale (which two points give). Null without two anchors apart. */
export function gridFit(c: LineColumns): GridFit | null {
  const n = c.length;
  if (!n) return null;
  const lat = [c.lat1, c.lat2], lon = [c.lon1, c.lon2], gx = [c.x1, c.x2], gy = [c.y1, c.y2];
  let mLat = 0, mLon = 0, mX = 0, mY = 0, count = 0;
  for (let e = 0; e < 2; e++) {
    for (let i = 0; i < n; i++) {
      const a = lat[e].at(i)!, o = lon[e].at(i)!, x = gx[e].at(i)!, y = gy[e].at(i)!;
      if (!(isFinite(a) && isFinite(o) && isFinite(x) && isFinite(y))) continue;
      mLat += a; mLon += o; mX += x; mY += y; count++;
    }
  }
  if (count < 2) return null;
  mLat /= count; mLon /= count; mX /= count; mY /= count;
  // local metres east (u) and north (v) of the mean, so both sides of the fit are metres about zero
  const ku = DEG * EARTH * Math.cos(mLat * DEG), kv = DEG * EARTH;
  let uu = 0, uv = 0, vv = 0, ux = 0, vx = 0, uy = 0, vy = 0;
  for (let e = 0; e < 2; e++) {
    for (let i = 0; i < n; i++) {
      const a = lat[e].at(i)!, o = lon[e].at(i)!, x = gx[e].at(i)!, y = gy[e].at(i)!;
      if (!(isFinite(a) && isFinite(o) && isFinite(x) && isFinite(y))) continue;
      const u = (o - mLon) * ku, v = (a - mLat) * kv;
      uu += u * u; uv += u * v; vv += v * v; ux += u * (x - mX); vx += v * (x - mX); uy += u * (y - mY); vy += v * (y - mY);
    }
  }
  if (!(uu + vv > 0)) return null;
  const det = uu * vv - uv * uv;
  let a11: number, a12: number, a21: number, a22: number;
  if (det > 1e-9 * uu * vv) {
    a11 = (ux * vv - vx * uv) / det; a12 = (vx * uu - ux * uv) / det;
    a21 = (uy * vv - vy * uv) / det; a22 = (vy * uu - uy * uv) / det;
  } else {  // the anchors on one line: x = p·u - q·v, y = q·u + p·v
    const p = (ux + vy) / (uu + vv), q = (uy - vx) / (uu + vv);
    a11 = p; a12 = -q; a21 = q; a22 = p;
  }
  const inv = a11 * a22 - a12 * a21;
  if (!(Math.abs(inv) > 1e-12)) return null;
  const toGrid = (la: number, lo: number): [number, number] => {
    const u = (lo - mLon) * ku, v = (la - mLat) * kv;
    return [mX + a11 * u + a12 * v, mY + a21 * u + a22 * v];
  };
  const toLatLng = (x: number, y: number): [number, number] => {
    const dx = x - mX, dy = y - mY;
    return [mLat + (a11 * dy - a21 * dx) / inv / kv, mLon + (a22 * dx - a12 * dy) / inv / ku];
  };
  let worst = 0, sum = 0;
  for (let e = 0; e < 2; e++) {
    for (let i = 0; i < n; i++) {
      const a = lat[e].at(i)!, o = lon[e].at(i)!, x = gx[e].at(i)!, y = gy[e].at(i)!;
      if (!(isFinite(a) && isFinite(o) && isFinite(x) && isFinite(y))) continue;
      const g = toGrid(a, o), d2 = (g[0] - x) * (g[0] - x) + (g[1] - y) * (g[1] - y);
      if (d2 > worst) worst = d2;
      sum += d2;
    }
  }
  // the grid's north (0, 1) on the map: its east and north parts in local metres
  const turn = (Math.atan2(-a12 / inv, a11 / inv) / DEG + 360) % 360;
  return {toGrid, toLatLng, residual: Math.sqrt(worst), rms: Math.sqrt(sum / count), anchors: count, turn};
}
