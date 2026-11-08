// The state of the highline layer's page (LayerPage.tsx) and its form in the address's hash:
// #layer[&country=<id>][&view=<lat>,<lon>,<zoom>][&mode=lines|spots][&length=<lo>-<hi>][&<dimension>=<edge>]...
// [&trees=all|no|only][&water=all|land|water][&border=all|own][&level=auto|1|2|4|8][&scale=fit|fixed], a dimension
// of the cube's `kinds` by its name (prominence, wall, clearance, height, water_m, elevation_low, elevation_high,
// height_mean, prominence_high, drop, high_pct, height_diff, clearance_trees, lift_needed, lift_no_zone: the keys
// countcube.Filters.parse reads). Absent is the default (lines, the full range, no limits, all, auto, fit); an
// invalid value falls back to it (checked against the first cube's edges and kinds). Also the rules without a DOM:
// the cells of the lattice a view holds, the automatic level, a cell's size and km², the breaks fitted to the view's
// densities.

import type { CountryCube, DimensionKind } from "../api";
import type { LayerMode } from "./cellsLayer";

export type LayerLevel = "auto" | "1" | "2" | "4" | "8";
export type LayerScale = "fit" | "fixed";
export type LayerBorder = "all" | "own";
export interface View { lat: number; lon: number; zoom: number }

export interface LayerState {
  country: string | null;
  view: View | null;
  mode: LayerMode;
  length: [number, number];
  /** Each dimension's limit: an edge of its bins, or null for none (a floor's off value is its first edge). */
  limits: Record<string, number | null>;
  trees: "all" | "no" | "only";
  water: "all" | "land" | "water";
  border: LayerBorder;
  level: LayerLevel;
  scale: LayerScale;
}

/** The dimensions of a cube with a limit (cube.json's kinds, in their order) and their kinds. */
export function dimensions(cube: CountryCube): [string, DimensionKind][] {
  return Object.entries(cube.kinds || {}).filter(([d]) => Array.isArray(cube.edges[d]));
}

/** A dimension's limit that is no limit: a floor's first edge, else null. */
export function offLimit(cube: CountryCube, dimension: string): number | null {
  return cube.kinds[dimension] === "floor" ? cube.edges[dimension][0] : null;
}

/** Whether a dimension's limit is on (countcube.Filters.active: a floor above its first edge; a "below" at an
 *  edge, but the first for any but the wall, whose 0 keeps today's meaning; an at_most at any edge, 0 too). */
export function limitOn(cube: CountryCube, dimension: string, value: number | null): boolean {
  const kind = cube.kinds[dimension], first = cube.edges[dimension]?.[0];
  if (kind === "floor") return value !== null && value !== first;
  if (value === null) return false;
  return !(kind === "below" && dimension !== "wall" && value === first);
}

/** The edges a dimension's limit may take besides none, in the order of its choices. */
export function limitEdges(cube: CountryCube, dimension: string): number[] {
  const e = cube.edges[dimension], kind = cube.kinds[dimension];
  return kind === "below" ? e.filter((v, k) => k > 0 && v > 0) : [...e];
}

export function defaults(cube: CountryCube): LayerState {
  const length = cube.edges.length;
  const limits: Record<string, number | null> = {};
  for (const [d] of dimensions(cube)) limits[d] = offLimit(cube, d);
  return {country: null, view: null, mode: "lines", length: [length[0], length[length.length - 1]], limits,
          trees: "all", water: "all", border: "all", level: "auto", scale: "fit"};
}

const one = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
  value !== null && (allowed as readonly string[]).includes(value) ? value as T : fallback;
const NUMBER = /^-?\d+(\.\d+)?$/;

/** The state of a hash's parameters; what is absent or invalid takes its default. */
export function parseState(params: URLSearchParams, cube: CountryCube): LayerState {
  const d = defaults(cube), edges = cube.edges;
  const state: LayerState = {...d, limits: {...d.limits}, country: params.get("country") || null};
  const view = (params.get("view") || "").split(",").map(Number);
  if (view.length === 3 && view.every(Number.isFinite) && Math.abs(view[0]) <= 90 && Math.abs(view[1]) <= 180
      && view[2] >= 0 && view[2] <= 22) state.view = {lat: view[0], lon: view[1], zoom: view[2]};
  state.mode = one(params.get("mode"), ["lines", "spots"], "lines");
  const length = (params.get("length") || "").split("-").map(Number);
  if (length.length === 2 && edges.length.includes(length[0]) && edges.length.includes(length[1]) && length[0] < length[1]) {
    state.length = [length[0], length[1]];
  }
  for (const [dim] of dimensions(cube)) {
    const text = params.get(dim);
    if (text === null || !NUMBER.test(text)) continue;
    const value = Number(text);
    if (limitEdges(cube, dim).includes(value)) state.limits[dim] = value;
  }
  state.trees = one(params.get("trees"), ["all", "no", "only"], "all");
  state.water = one(params.get("water"), ["all", "land", "water"], "all");
  state.border = one(params.get("border"), ["all", "own"], "all");
  state.level = one(params.get("level"), ["auto", ...cube.levels.map(String)] as LayerLevel[], "auto");
  state.scale = one(params.get("scale"), ["fit", "fixed"], "fit");
  return state;
}

/** The hash's parameters of a state: what differs from the default (route.ts layerHash leaves empty values out). */
export function stateParams(state: LayerState, cube: CountryCube): Record<string, string> {
  const d = defaults(cube);
  const full = state.length[0] === d.length[0] && state.length[1] === d.length[1];
  const out: Record<string, string> = {
    country: state.country || "",
    view: state.view ? `${state.view.lat.toFixed(4)},${state.view.lon.toFixed(4)},${+state.view.zoom.toFixed(2)}` : "",
    mode: state.mode === "lines" ? "" : state.mode,
    length: full ? "" : `${state.length[0]}-${state.length[1]}`,
  };
  for (const [dim] of dimensions(cube)) {
    const value = state.limits[dim] ?? null;
    out[dim] = value === null || value === offLimit(cube, dim) ? "" : String(value);
  }
  return {...out, trees: state.trees === "all" ? "" : state.trees, water: state.water === "all" ? "" : state.water,
          border: state.border === "all" ? "" : state.border, level: state.level === "auto" ? "" : state.level,
          scale: state.scale === "fit" ? "" : state.scale};
}

/** The filters of /api/countries/<id>/cells and /histogram (without bbox and level): the mode, the length, every
 *  limit that is on, the flags and the border. */
export function filtersQuery(f: LayerState, cube: CountryCube): Record<string, string> {
  const query: Record<string, string> = {mode: f.mode, length: `${f.length[0]}-${f.length[1]}`};
  for (const [dim, value] of Object.entries(f.limits)) {
    if (limitOn(cube, dim, value)) query[dim] = String(value);
  }
  query.trees = f.trees;
  query.water = f.water;
  query.border = f.border;
  return query;
}

/** The filters set (for the notes and the rail): the length range narrowed, each limit on, the flags. */
export function filtersSet(f: LayerState, cube: CountryCube): number {
  const d = defaults(cube);
  const full = f.length[0] === d.length[0] && f.length[1] === d.length[1];
  const limits = dimensions(cube).filter(([dim]) => limitOn(cube, dim, f.limits[dim] ?? null)).length;
  return [!full, f.trees !== "all", f.water !== "all"].filter(Boolean).length + limits;
}

/** The topics of the filters' fold and of the charts, in one order (the length chart leads), and the dimensions
 *  of each; a dimension of the cube in no topic goes to the last. The seven of the open form: SEVEN. */
export const TOPICS: {id: string; charts: string[]}[] = [
  {id: "line", charts: ["length", "clearance", "height", "height_mean", "high_pct", "clearance_trees", "water_m"]},
  {id: "terrain", charts: ["prominence", "prominence_high", "wall", "drop", "elevation_low", "elevation_high"]},
  {id: "rigging", charts: ["lift_needed", "lift_no_zone", "height_diff"]},
];
export const SEVEN = ["length", "prominence", "wall", "clearance", "height", "trees", "water"];

/** The charts of each topic for a cube: the topics' dimensions it has, the others of its kinds appended to the last. */
export function topicsOf(cube: CountryCube): {id: string; charts: string[]}[] {
  const known = new Set(["length", ...dimensions(cube).map(([d]) => d)]);
  const placed = new Set(TOPICS.flatMap((t) => t.charts));
  const rest = [...known].filter((d) => !placed.has(d));
  return TOPICS.map((t, k) => ({id: t.id, charts: [...t.charts.filter((d) => known.has(d)), ...(k === TOPICS.length - 1 ? rest : [])]}));
}

/** A box in WGS84: [west, south, east, north]. */
export type Box = [number, number, number, number];

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

/** Whether a cube is summed with the first country: no study area, of the same layer profile (R7: cube.json's
 *  "profile"; none before it, the same for all). */
export function summedWith(first: CountryCube | undefined, cube: CountryCube): boolean {
  return !cube.study && (!first || (first.profile ?? null) === (cube.profile ?? null));
}

/** The cubes the page counts: every country of the first country's profile, or a cube that is not summed with it (a
 *  study area, a part of a country, whose lines would count twice; a country of another profile) alone when it is
 *  the one chosen (cubes of study areas only: the first). */
export function activeCubes(cubes: CountryCube[], country: string | null): CountryCube[] {
  const first = cubes.find((c) => !c.study);
  const chosen = cubes.find((c) => c.id === country);
  if (chosen && !summedWith(first, chosen)) return [chosen];
  const countries = cubes.filter((c) => summedWith(first, c));
  return countries.length ? countries : cubes.slice(0, 1);
}

/** The neighbours of a cube (cube.json's neighbours) whose own layer is shown with it: listed, summed with it, so
 *  their own lines replace its partner lines (web.Countries.replaced); by partner index (1-6). */
export function replacedPartners(cube: CountryCube, cubes: CountryCube[]): Set<number> {
  const out = new Set<number>();
  (cube.neighbours || []).forEach((id, k) => {
    const other = cubes.find((c) => c.id === id);
    if (k < 6 && other && id !== cube.id && !other.study && (other.profile ?? null) === (cube.profile ?? null)) out.add(k + 1);
  });
  return out;
}

/** The side of a level's cell in degrees. */
export const cellDeg = (cube: CountryCube, level: number) => level * cube.cell_deg;

/** How many cells of a level the box holds over the cubes in it (the box clipped to each cube's bounds). */
export function cellsAt(cubes: CountryCube[], box: Box, level: number): number {
  return cubes.reduce((s, c) => {
    const b = c.bounds_wgs84, side = cellDeg(c, level);
    const w = Math.max(box[0], b[0]), e = Math.min(box[2], b[2]), so = Math.max(box[1], b[1]), n = Math.min(box[3], b[3]);
    return s + (e > w && n > so ? ((e - w) / side) * ((n - so) / side) : 0);
  }, 0);
}

/** The cells the server counts against its limit (web.COUNTRY_CELLS_MAX, 20000) for one cube's request over a
 *  box: the box clipped to the cube's bounds grown by a degree (countcube.Cube.box), in cells of the lattice. */
export function requestCells(cube: CountryCube, box: Box, level: number): number {
  const b = cube.bounds_wgs84, side = cellDeg(cube, level);
  const w = Math.max(box[0], b[0] - 1), e = Math.min(box[2], b[2] + 1), s = Math.max(box[1], b[1] - 1), n = Math.min(box[3], b[3] + 1);
  return e > w && n > s ? (Math.floor(e / side) - Math.floor(w / side) + 1) * (Math.floor(n / side) - Math.floor(s / side) + 1) : 0;
}

/** The largest request of the cubes reaching a box (each cube is asked on its own). */
export function largestRequest(cubes: CountryCube[], box: Box, level: number): number {
  return Math.max(0, ...cubesIn(cubes, box).map((c) => requestCells(c, box, level)));
}

/** A request stays under this (the server's 20000 with a margin). */
export const REQUEST_CELLS_MAX = 16000;

export const CELLS_FIRST = 4000;   // a first view (and a view resized by a panel): the finest level with at most so many cells
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

// WGS84, as countcube's
const A = 6378137.0, F = 1 / 298.257223563, E2 = F * (2 - F), E = Math.sqrt(E2), B = A * (1 - F);
const RAD = Math.PI / 180;

/** Metres per degree of longitude and of latitude at a latitude (countcube._metres_per_degree). */
export function metresPerDegree(lat: number): [number, number] {
  const s = Math.sin(lat * RAD), w = Math.sqrt(1 - E2 * s * s);
  return [A / w * Math.cos(lat * RAD) * RAD, A * (1 - E2) / (w * w * w) * RAD];
}

/** The size (east-west, north-south) in km of a cell of `deg` degrees at a latitude. */
export function cellSizeKm(deg: number, lat: number): [number, number] {
  const [east, north] = metresPerDegree(lat);
  return [east * deg / 1000, north * deg / 1000];
}

/** (b² / 2) q(φ) of WGS84 (countcube._authalic): the area between the equator and φ per radian of longitude, m². */
function authalic(lat: number): number {
  const s = Math.sin(lat * RAD);
  return B * B / 2 * (s / (1 - E2 * s * s) + Math.log((1 + E * s) / (1 - E * s)) / (2 * E));
}

/** The km² of a lon/lat rectangle on the ellipsoid (countcube.lattice_km2 of a whole cell). */
export function rectKm2(south: number, north: number, west: number, east: number): number {
  return Math.abs(authalic(north) - authalic(south)) * Math.abs(east - west) * RAD / 1e6;
}

/** A level's name: its side in seconds (30″) or minutes (1′) of arc. */
export function levelName(deg: number): string {
  const seconds = Math.round(deg * 3600 * 100) / 100;
  return seconds < 60 ? `${seconds}″` : `${+(seconds / 60).toFixed(2)}′`;
}

/** A cell's size as text: "0.6 × 0.9 km". */
export function sizeText(deg: number, lat: number): string {
  const [w, h] = cellSizeKm(deg, lat);
  const f = (v: number) => v >= 10 ? v.toFixed(0) : v.toFixed(1);
  return `${f(w)} × ${f(h)} km`;
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

/** The outlines instead of cells: a coarse cell under 4 px on screen. */
export const OUTLINE_MPP = 2000;
