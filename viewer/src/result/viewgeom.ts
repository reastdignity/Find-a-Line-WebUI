// The result view's pure parts (docs/line-volume/spec-view.md B.2): the level the zoom gives, whether a line crosses
// the view, the squares of the Area level and their classes, a direction's word, and the fit between a run's grid
// and the map. Plain TypeScript without the DOM or Leaflet, so tests run it under Node (tests/test_view_units.py).
//
// Everything here is in the run's grid metres (x east, y north, as the lines' anchors are stored): the view is the
// map's visible part taken into the grid by the fit (a Quad: on the web map the grid stands slightly turned), a
// square is a cell of the grid.

import type { LineColumns, NumberColumn } from "../types";
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
// The page has no projection library; every anchor is stored both ways (latitude and longitude, grid metres), so
// the grid's place of a point of the map is a polynomial fitted to the run's own anchors: of the lowest degree, 1
// to 3, whose farthest anchor lies within `max` of its stored place (measured 2026-11-16 on five grids: a flat,
// degree 1, map is 0.2 m off over 2 km, 1 m over 5 km and 10 m over 15 km, because a grid's east grows with the
// longitude times the cosine of the latitude; degree 2 holds 6 mm over 15 km and 0.2 m over 50 km; degree 3 13 mm
// over 100 km). A degree is tried only with at least three times as many distinct anchors as it has numbers per
// axis (FIT_ANCHORS: its residual at the anchors then says something), and a polynomial must not be asked far
// outside its anchors: every point is first clamped to the anchors' box widened by FIT_MARGIN (the view's
// corners when the map is zoomed far out, a pressed point, a square's corner).

/** A run's grid metres from latitudes and longitudes and back (gridFit). `degree`: of the polynomial (0: a turn and
 *  one scale, of a run whose anchors are too few or on one line for more); `residual`: the farthest any anchor's
 *  stored grid place lies from the fit's of its latitude and longitude, m; `rms` their root mean square; `back`: the
 *  farthest an anchor's grid place comes back from its latitude and longitude through both ways, m; `anchors` how
 *  many there are; `turn` the grid north's direction on the map at the run's middle, degrees clockwise from true
 *  north. toGrid and toLatLng clamp their point to the anchors' box widened by `margin` metres first; `scale` is
 *  the grid's metres per metre on the ground (along the east) at a point so clamped. */
export interface GridFit {
  toGrid(lat: number, lon: number): [number, number];
  toLatLng(x: number, y: number): [number, number];
  scale(lat: number, lon: number): number;
  degree: 0 | 1 | 2 | 3;
  residual: number;
  rms: number;
  back: number;
  anchors: number;
  turn: number;
  margin: number;
}

/** The distinct anchors a degree needs: three times its numbers per axis (3, 6, 10). */
export const FIT_ANCHORS = [2, 9, 18, 30];
/** The margin around the anchors' box inside which the fit is asked: the larger of this many metres (the largest
 *  square's side, so no square is cut) and this share of the box's longer side. */
export const FIT_MARGIN = 200, FIT_MARGIN_SHARE = 0.1;
const FIT_SAMPLE = 25000;  // the fit is solved on at most this many lines, taken evenly; its residual is of them all
/** Anchors whose scatter is narrower than this, m (its standard deviation across their longest direction), count
 *  as lying on one line: a polynomial would fit their rounding across it. */
export const FIT_FLAT = 5;

const DEG = Math.PI / 180, EARTH = 6371008.8;

/** A column's value by row without its checks, where it holds every value (the anchors always do). */
export function reader(c: NumberColumn): (i: number) => number {
  const v = c.values, s = c.scale;
  if (c.valid !== null || c.nulls !== null) return (i) => c.at(i) as number;
  return s === 0 ? (i) => v[i] : (i) => v[i] / s;
}

/** The exponents (of u, of v) of a polynomial's terms up to `degree`. */
function terms(degree: number): [number, number][] {
  const out: [number, number][] = [];
  for (let d = 0; d <= degree; d++) for (let i = d; i >= 0; i--) out.push([i, d - i]);
  return out;
}

/** The solution of the normal equations a·x = b (a: n × n, symmetric, row by row; b: n × 2), or null when they are
 *  singular (Gauss with pivots). */
function solve(a: Float64Array, b: Float64Array, n: number): Float64Array | null {
  const m = Float64Array.from(a), r = Float64Array.from(b);
  let scale = 0;
  for (let k = 0; k < n; k++) scale = Math.max(scale, Math.abs(m[k * n + k]));
  for (let k = 0; k < n; k++) {
    let p = k;
    for (let i = k + 1; i < n; i++) if (Math.abs(m[i * n + k]) > Math.abs(m[p * n + k])) p = i;
    if (!(Math.abs(m[p * n + k]) > 1e-10 * scale)) return null;
    if (p !== k) {
      for (let j = 0; j < n; j++) { const t = m[k * n + j]; m[k * n + j] = m[p * n + j]; m[p * n + j] = t; }
      for (let j = 0; j < 2; j++) { const t = r[k * 2 + j]; r[k * 2 + j] = r[p * 2 + j]; r[p * 2 + j] = t; }
    }
    for (let i = k + 1; i < n; i++) {
      const f = m[i * n + k] / m[k * n + k];
      if (f === 0) continue;
      for (let j = k; j < n; j++) m[i * n + j] -= f * m[k * n + j];
      r[i * 2] -= f * r[k * 2]; r[i * 2 + 1] -= f * r[k * 2 + 1];
    }
  }
  for (let k = n - 1; k >= 0; k--) {
    for (let j = 0; j < 2; j++) {
      let s = r[k * 2 + j];
      for (let i = k + 1; i < n; i++) s -= m[k * n + i] * r[i * 2 + j];
      r[k * 2 + j] = s / m[k * n + k];
    }
  }
  return r;
}

/** A polynomial map (p, q) -> (a, b) of two numbers each within about -1 … 1: `c` its terms' two coefficients. */
interface Poly { c: Float64Array; e: [number, number][] }

function evaluate(poly: Poly, p: number, q: number, out: [number, number]) {
  const {c, e} = poly, p2 = p * p, q2 = q * q, pw = [1, p, p2, p2 * p], qw = [1, q, q2, q2 * q];
  let a = 0, b = 0;
  for (let k = 0; k < e.length; k++) {
    const t = pw[e[k][0]] * qw[e[k][1]];
    a += c[2 * k] * t; b += c[2 * k + 1] * t;
  }
  out[0] = a; out[1] = b;
}

/** The least-squares polynomial of `degree` through the points `each` gives ((p, q) -> (a, b)), or null. */
function fitPoly(degree: number, each: (f: (p: number, q: number, a: number, b: number) => void) => void): Poly | null {
  const e = terms(degree), n = e.length, ata = new Float64Array(n * n), atb = new Float64Array(n * 2), t = new Float64Array(n);
  each((p, q, a, b) => {
    const p2 = p * p, q2 = q * q, pw = [1, p, p2, p2 * p], qw = [1, q, q2, q2 * q];
    for (let k = 0; k < n; k++) t[k] = pw[e[k][0]] * qw[e[k][1]];
    for (let k = 0; k < n; k++) {
      const tk = t[k];
      for (let j = k; j < n; j++) ata[k * n + j] += tk * t[j];
      atb[2 * k] += tk * a; atb[2 * k + 1] += tk * b;
    }
  });
  for (let k = 0; k < n; k++) for (let j = 0; j < k; j++) ata[k * n + j] = ata[j * n + k];
  const c = solve(ata, atb, n);
  return c && {c, e};
}

/** The fit of a run's lines (GridFit) over both anchors of every line: of the lowest degree that FIT_ANCHORS allows
 *  whose residual is at most `max`; when none is, the last one tried (its residual says by how much: the caller
 *  compares). A run whose anchors are fewer than degree 1 needs, or lie on one straight line, is fitted by a turn
 *  and one scale (two anchors give them). Null without two anchors apart. */
export function gridFit(c: LineColumns, max = Infinity): GridFit | null {
  const n = c.length;
  if (!n) return null;
  const lat = [reader(c.lat1), reader(c.lat2)], lon = [reader(c.lon1), reader(c.lon2)];
  const gx = [reader(c.x1), reader(c.x2)], gy = [reader(c.y1), reader(c.y2)];
  // the anchors' boxes both ways, and whether they are enough for each degree
  let la0 = Infinity, la1 = -Infinity, lo0 = Infinity, lo1 = -Infinity, x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  let count = 0, a0 = NaN, o0 = NaN, sp = 0, sq = 0, spp = 0, spq = 0, sqq = 0;
  const distinct = new Set<string>(), enough = FIT_ANCHORS[3];
  for (let e = 0; e < 2; e++) {
    for (let i = 0; i < n; i++) {
      const a = lat[e](i), o = lon[e](i), x = gx[e](i), y = gy[e](i);
      if (!(isFinite(a) && isFinite(o) && isFinite(x) && isFinite(y))) continue;
      if (!count) { a0 = a; o0 = o; }
      count++;
      if (a < la0) la0 = a; if (a > la1) la1 = a; if (o < lo0) lo0 = o; if (o > lo1) lo1 = o;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      if (distinct.size < enough) distinct.add(x + "," + y);
      const p = (o - o0) * DEG * EARTH * Math.cos(a0 * DEG), q = (a - a0) * DEG * EARTH;  // metres from the first anchor
      sp += p; sq += q; spp += p * p; spq += p * q; sqq += q * q;
    }
  }
  if (distinct.size < FIT_ANCHORS[0]) return null;
  // how far the anchors spread across their own longest direction (the smaller axis of their scatter): on one
  // straight line, or nearly, nothing can be said across it but by a turn and a scale
  const vpp = spp / count - (sp / count) ** 2, vqq = sqq / count - (sq / count) ** 2, vpq = spq / count - sp * sq / (count * count);
  const across = Math.sqrt(Math.max(0, (vpp + vqq) / 2 - Math.hypot((vpp - vqq) / 2, vpq)));
  const flat = !(across >= FIT_FLAT);
  // both sides about zero and within about -1 … 1: (u, v) of a latitude and longitude, (s, t) of a grid place
  const mLat = (la0 + la1) / 2, mLon = (lo0 + lo1) / 2, hLat = (la1 - la0) / 2 || 1e-6, hLon = (lo1 - lo0) / 2 || 1e-6;
  const mX = (x0 + x1) / 2, mY = (y0 + y1) / 2, half = Math.max(x1 - x0, y1 - y0) / 2 || 1;
  const margin = Math.max(FIT_MARGIN, FIT_MARGIN_SHARE * 2 * half);
  const dLat = margin / (EARTH * DEG), dLon = margin / (EARTH * DEG * Math.cos(mLat * DEG));
  const step = Math.max(1, Math.ceil(n / FIT_SAMPLE));
  const anchors = (every: number) => (f: (u: number, v: number, s: number, t: number) => void) => {
    for (let e = 0; e < 2; e++) {
      for (let i = 0; i < n; i += every) {
        const a = lat[e](i), o = lon[e](i), x = gx[e](i), y = gy[e](i);
        if (!(isFinite(a) && isFinite(o) && isFinite(x) && isFinite(y))) continue;
        f((o - mLon) / hLon, (a - mLat) / hLat, (x - mX) / half, (y - mY) / half);
      }
    }
  };
  /** A turn and one scale through the sampled anchors, as polynomials of degree 1 both ways. */
  const similar = (): [Poly, Poly] | null => {
    // in local metres east (p) and north (q) of the middle: x = a·p - b·q, y = b·p + a·q
    const kp = hLon * DEG * EARTH * Math.cos(mLat * DEG), kq = hLat * DEG * EARTH;
    let pp = 0, px = 0, py = 0, qx = 0, qy = 0, mp = 0, mq = 0, ms = 0, mt = 0, m = 0;
    anchors(step)((u, v, s, t) => { mp += u * kp; mq += v * kq; ms += s; mt += t; m++; });
    mp /= m; mq /= m; ms /= m; mt /= m;
    anchors(step)((u, v, s, t) => {
      const p = u * kp - mp, q = v * kq - mq, x = (s - ms) * half, y = (t - mt) * half;
      pp += p * p + q * q; px += p * x; py += p * y; qx += q * x; qy += q * y;
    });
    if (!(pp > 0)) return null;
    const a = (px + qy) / pp, b = (py - qx) / pp, det = a * a + b * b;
    if (!(det > 0)) return null;
    // forward: s = ms + (a·(u·kp - mp) - b·(v·kq - mq)) / half …; back: the inverse turn and scale
    const e = terms(1), fs = (a * -mp + b * mq) / half + ms, ft = (b * -mp - a * mq) / half + mt;
    const forward = {e, c: Float64Array.from([fs, ft, a * kp / half, b * kp / half, -b * kq / half, a * kq / half])};
    const bu = (-a * ms - b * mt) * half / det, bv = (b * ms - a * mt) * half / det;
    const back = {e, c: Float64Array.from([(bu + mp) / kp, (bv + mq) / kq, a * half / det / kp, -b * half / det / kq,
                                           b * half / det / kp, a * half / det / kq])};
    return [forward, back];
  };
  const pair = (degree: number): [Poly, Poly] | null => {
    if (degree === 0) return similar();
    const forward = fitPoly(degree, anchors(step));
    const back = forward && fitPoly(degree, (f) => anchors(step)((u, v, s, t) => f(s, t, u, v)));
    return forward && back ? [forward, back] : null;
  };
  const made = (degree: 0 | 1 | 2 | 3, [forward, back]: [Poly, Poly]): GridFit => {
    const out: [number, number] = [0, 0];
    // the residual at every anchor (on the sample first: a degree that fails there is not measured further)
    const measure = (every: number) => {
      let worst = 0, sum = 0, there = 0, m = 0;
      anchors(every)((u, v, s, t) => {
        evaluate(forward, u, v, out);
        const d2 = ((out[0] - s) * (out[0] - s) + (out[1] - t) * (out[1] - t)) * half * half;
        if (d2 > worst) worst = d2;
        sum += d2; m++;
        evaluate(back, s, t, out);
        evaluate(forward, out[0], out[1], out);
        const b2 = ((out[0] - s) * (out[0] - s) + (out[1] - t) * (out[1] - t)) * half * half;
        if (b2 > there) there = b2;
      });
      return {residual: Math.sqrt(worst), rms: Math.sqrt(sum / Math.max(1, m)), back: Math.sqrt(there)};
    };
    let found = measure(step);
    if (step > 1 && found.residual <= max && found.back <= max) found = measure(1);
    const raw = (la: number, lo: number): [number, number] => {
      const at: [number, number] = [0, 0];
      evaluate(forward, (lo - mLon) / hLon, (la - mLat) / hLat, at);
      return [mX + at[0] * half, mY + at[1] * half];
    };
    const clampLat = (la: number) => Math.min(la1 + dLat, Math.max(la0 - dLat, la));
    const clampLon = (lo: number) => Math.min(lo1 + dLon, Math.max(lo0 - dLon, lo));
    // the grid's north on the map: the direction in which a step north in the grid moves, from the back way
    const up: [number, number] = [0, 0], here: [number, number] = [0, 0];
    evaluate(back, 0, 0, here);
    evaluate(back, 0, 1e-4, up);
    const east = (up[0] - here[0]) * hLon * Math.cos(mLat * DEG), northward = (up[1] - here[1]) * hLat;
    return {
      degree, anchors: count, margin, ...found,
      turn: (Math.atan2(east, northward) / DEG + 360) % 360,
      toGrid: (la, lo) => raw(clampLat(la), clampLon(lo)),
      toLatLng: (x, y) => {
        const at: [number, number] = [0, 0];
        evaluate(back, (Math.min(x1 + margin, Math.max(x0 - margin, x)) - mX) / half,
                 (Math.min(y1 + margin, Math.max(y0 - margin, y)) - mY) / half, at);
        return [mLat + at[1] * hLat, mLon + at[0] * hLon];
      },
      scale: (la, lo) => {
        const a = clampLat(la), o = Math.min(lo1, Math.max(lo0, lo)), d = 1e-4;  // about 10 m, inwards of the box
        const from = raw(a, o - d / 2), to = raw(a, o + d / 2);
        return Math.hypot(to[0] - from[0], to[1] - from[1]) / (d * DEG * EARTH * Math.cos(a * DEG));
      },
    };
  };
  let last: GridFit | null = null;
  const degrees: (0 | 1 | 2 | 3)[] = distinct.size >= FIT_ANCHORS[1] && !flat ? [1, 2, 3] : [0];
  for (const degree of degrees) {
    if (distinct.size < FIT_ANCHORS[degree]) break;
    let both = pair(degree);
    if (!both && degree === 1) {  // the anchors on one straight line: a turn and a scale, and no higher degree
      both = pair(0);
      return both && made(0, both);
    }
    if (!both) break;
    last = made(degree, both);
    if (last.residual <= max && last.back <= max) return last;
  }
  return last;
}
