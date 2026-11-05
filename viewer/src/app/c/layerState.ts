// The state of the highline layer's page (LayerPage.tsx) and its form in the address's hash:
// #layer[&country=<id>][&view=<lat>,<lon>,<zoom>][&mode=lines|spots][&length=<lo>-<hi>][&prominence=<p>][&wall=<w>]
// [&clearance=<c>][&height=<h>][&trees=all|no|only][&water=all|land|water][&level=auto|1|2|4|8][&scale=fit|fixed].
// Absent is the default (lines, the full range, no thresholds, auto, fit); an invalid value falls back to it
// (checked against the first cube's edges). Also the rules without a DOM: the automatic level of a view, the
// cells it holds and the breaks fitted to the view's densities.

import type { CountryCube } from "../api";
import type { LayerMode } from "./cellsLayer";

export type LayerLevel = "auto" | "1" | "2" | "4" | "8";
export type LayerScale = "fit" | "fixed";
export interface View { lat: number; lon: number; zoom: number }

export interface LayerState {
  country: string | null;
  view: View | null;
  mode: LayerMode;
  length: [number, number];
  prominence: number;
  wall: number | null;
  clearance: number;
  height: number;
  trees: "all" | "no" | "only";
  water: "all" | "land" | "water";
  level: LayerLevel;
  scale: LayerScale;
}

export function defaults(cube: CountryCube): LayerState {
  const length = cube.edges.length;
  return {country: null, view: null, mode: "lines", length: [length[0], length[length.length - 1]], prominence: 0, wall: null,
          clearance: 0, height: 0, trees: "all", water: "all", level: "auto", scale: "fit"};
}

const one = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
  value !== null && (allowed as readonly string[]).includes(value) ? value as T : fallback;
const edge = (value: string | null, edges: number[], fallback: number): number =>
  value !== null && /^-?\d+(\.\d+)?$/.test(value) && edges.includes(Number(value)) ? Number(value) : fallback;

/** The state of a hash's parameters; what is absent or invalid takes its default. */
export function parseState(params: URLSearchParams, cube: CountryCube): LayerState {
  const d = defaults(cube), edges = cube.edges;
  const state: LayerState = {...d, country: params.get("country") || null};
  const view = (params.get("view") || "").split(",").map(Number);
  if (view.length === 3 && view.every(Number.isFinite) && Math.abs(view[0]) <= 90 && Math.abs(view[1]) <= 180
      && view[2] >= 0 && view[2] <= 22) state.view = {lat: view[0], lon: view[1], zoom: view[2]};
  state.mode = one(params.get("mode"), ["lines", "spots"], "lines");
  const length = (params.get("length") || "").split("-").map(Number);
  if (length.length === 2 && edges.length.includes(length[0]) && edges.length.includes(length[1]) && length[0] < length[1]) {
    state.length = [length[0], length[1]];
  }
  state.prominence = edge(params.get("prominence"), edges.prominence, 0);
  const wall = params.get("wall");
  state.wall = wall !== null && edges.wall.includes(Number(wall)) && Number(wall) > 0 ? Number(wall) : null;
  state.clearance = edge(params.get("clearance"), edges.clearance, 0);
  state.height = edge(params.get("height"), edges.height, 0);
  state.trees = one(params.get("trees"), ["all", "no", "only"], "all");
  state.water = one(params.get("water"), ["all", "land", "water"], "all");
  state.level = one(params.get("level"), ["auto", ...cube.levels.map(String)] as LayerLevel[], "auto");
  state.scale = one(params.get("scale"), ["fit", "fixed"], "fit");
  return state;
}

/** The hash's parameters of a state: what differs from the default (route.ts layerHash leaves empty values out). */
export function stateParams(state: LayerState, cube: CountryCube): Record<string, string> {
  const d = defaults(cube);
  const full = state.length[0] === d.length[0] && state.length[1] === d.length[1];
  return {
    country: state.country || "",
    view: state.view ? `${state.view.lat.toFixed(4)},${state.view.lon.toFixed(4)},${+state.view.zoom.toFixed(2)}` : "",
    mode: state.mode === "lines" ? "" : state.mode,
    length: full ? "" : `${state.length[0]}-${state.length[1]}`,
    prominence: state.prominence ? String(state.prominence) : "",
    wall: state.wall === null ? "" : String(state.wall),
    clearance: state.clearance ? String(state.clearance) : "",
    height: state.height ? String(state.height) : "",
    trees: state.trees === "all" ? "" : state.trees,
    water: state.water === "all" ? "" : state.water,
    level: state.level === "auto" ? "" : state.level,
    scale: state.scale === "fit" ? "" : state.scale,
  };
}

/** The filters of /api/countries/<id>/cells and /histogram (without bbox and level). */
export function filtersQuery(f: LayerState): Record<string, string> {
  const query: Record<string, string> = {mode: f.mode, length: `${f.length[0]}-${f.length[1]}`,
                                         prominence: String(f.prominence), clearance: String(f.clearance),
                                         height: String(f.height), trees: f.trees, water: f.water};
  if (f.wall !== null) query.wall = String(f.wall);
  return query;
}

/** Which filters are set (for the notes): the length range narrowed, each threshold, the flags. */
export function filtersSet(f: LayerState, cube: CountryCube): number {
  const d = defaults(cube);
  const full = f.length[0] === d.length[0] && f.length[1] === d.length[1];
  return [!full, f.prominence > 0, f.wall !== null, f.clearance > 0, f.height > 0, f.trees !== "all", f.water !== "all"]
    .filter(Boolean).length;
}

/** A box in WGS84: [west, south, east, north]. */
export type Box = [number, number, number, number];
const KM_PER_DEG = 111.32;

/** The km² of the intersection of two boxes. */
export function overlapKm2(a: Box, b: Box): number {
  const w = Math.max(a[0], b[0]), s = Math.max(a[1], b[1]), e = Math.min(a[2], b[2]), n = Math.min(a[3], b[3]);
  if (e <= w || n <= s) return 0;
  const mid = (s + n) / 2;
  return (e - w) * KM_PER_DEG * Math.cos(mid * Math.PI / 180) * (n - s) * KM_PER_DEG;
}

export function intersects(a: Box, b: Box): boolean {
  return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
}

/** The cubes whose bounds reach a box. */
export function cubesIn(cubes: CountryCube[], box: Box): CountryCube[] {
  return cubes.filter((c) => intersects(c.bounds_wgs84, box));
}

/** The countries first: the first of the list is the one a page opens on, and an id may sort a study area first. */
export function countriesFirst(cubes: CountryCube[]): CountryCube[] {
  return [...cubes.filter((c) => !c.study), ...cubes.filter((c) => c.study)];
}

/** The cubes the page counts: every country, or a study area alone when it is the one chosen (cubes of study areas
 *  only: the first). A study area is a part of a country: added to it, its lines would count twice. */
export function activeCubes(cubes: CountryCube[], country: string | null): CountryCube[] {
  const chosen = cubes.find((c) => c.id === country);
  if (chosen?.study) return [chosen];
  const countries = cubes.filter((c) => !c.study);
  return countries.length ? countries : cubes.slice(0, 1);
}

/** How many cells of level L (its cells of cell_m each) a box holds over the cubes in it. */
export function cellsAt(cubes: CountryCube[], box: Box, level: number): number {
  return cubes.reduce((s, c) => s + overlapKm2(c.bounds_wgs84, box) / (level * c.cell_m / 1000) ** 2, 0);
}

/** The cells the server counts against its limit (web.COUNTRY_CELLS_MAX, 20000) for one cube's request over a
 *  box: the box clipped to the cube's bounds grown by a degree (countcube.Cube.box), not to the bounds alone. */
export function requestCells(cube: CountryCube, box: Box, level: number): number {
  const b = cube.bounds_wgs84;
  return overlapKm2(box, [b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1]) / (level * cube.cell_m / 1000) ** 2;
}

/** The largest request of the cubes reaching a box (each cube is asked on its own). */
export function largestRequest(cubes: CountryCube[], box: Box, level: number): number {
  return Math.max(0, ...cubesIn(cubes, box).map((c) => requestCells(c, box, level)));
}

/** A request stays under this (the server's 20000 with a margin: its box in the cube's CRS is a little larger). */
export const REQUEST_CELLS_MAX = 16000;

export const CELLS_FIRST = 4000;   // a first view: the finest level with at most so many cells
export const CELLS_FINER = 900;    // go finer only when the finer level stays under this
export const CELLS_COARSER = 2400; // go coarser only above this (hysteresis: zooming does not flip the level)

/** The automatic level of a view: `current` kept unless the view asks for another (hysteresis); null at first. */
export function autoLevel(current: number | null, count: (level: number) => number, levels: number[]): number {
  const sorted = [...levels].sort((a, b) => a - b);
  if (current === null || !sorted.includes(current)) {
    return sorted.find((l) => count(l) <= CELLS_FIRST) ?? sorted[sorted.length - 1];
  }
  let k = sorted.indexOf(current);
  while (k < sorted.length - 1 && count(sorted[k]) > CELLS_COARSER) k++;
  while (k > 0 && count(sorted[k - 1]) <= CELLS_FINER) k--;
  return sorted[k];
}

/** Four breaks evenly spaced in log10 between the 2nd and 98th percentile of the densities (one hot cell does
 *  not move them), to two significant digits; `fallback` without any density above 0. */
export function quantileBreaks(densities: number[], fallback: number[]): number[] {
  const ds = densities.filter((d) => d > 0).sort((a, b) => a - b);
  if (!ds.length) return fallback;
  const q = (p: number) => ds[Math.min(ds.length - 1, Math.floor(p * (ds.length - 1)))];
  const lo = Math.log10(q(0.02));
  let hi = Math.log10(q(0.98));
  if (hi <= lo + 0.2) hi = lo + 0.2;
  const out: number[] = [];
  for (let i = 1; i <= 4; i++) out.push(Number(Math.pow(10, lo + (hi - lo) * i / 5).toPrecision(2)));
  return out;
}

/** The breaks eased from `from` to `to` in log10 at t (0 … 1, a cubic ease in-out). */
export function easedBreaks(from: number[], to: number[], t: number): number[] {
  const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  return to.map((b, k) => Math.pow(10, Math.log10(from[k]) + (Math.log10(b) - Math.log10(from[k])) * e));
}

/** The metres per pixel of a Web Mercator map at a zoom and latitude. */
export function metresPerPixel(lat: number, zoom: number): number {
  return 40075016.686 * Math.cos(lat * Math.PI / 180) / (256 * Math.pow(2, zoom));
}

/** The outlines instead of cells: an 8 km cell under 4 px on screen. */
export const OUTLINE_MPP = 2000;
