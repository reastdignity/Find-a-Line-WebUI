// The imagery's tiles of the 3D view, pure (tested in Node: tests/test_view3d_tiles.py; docs/3d-view-contract.md,
// "Wave 2", V2b): which Web Mercator tiles cover a chunk at a zoom, the zoom of each chunk within its canvas
// (2048 px) and the budget of textures, the tiles' URLs (our cache, the orthophoto's WMS over its base tiles, the
// base tiles alone, Esri's World Imagery) as the 2D map asks for them (baselayers.ts), and the texture's UV of
// grid metres (the meta's affine, then Web Mercator).

import { ESRI_MAX_ZOOM, esriTileUrl } from "../layers";
import type { Ortho } from "../types";
import type { Anchor3d, PatchMeta } from "./decode";
import { lonLat, mercator } from "./geometry";
import type { Level } from "./page";
import type { GridBounds } from "./scene-api";

export const TILE_PX = 256;
/** The largest side of a chunk's canvas. */
export const MAX_CANVAS = 2048;
/** Bytes of textures (RGBA with mipmaps) per level (docs/3d-view-contract.md, "Budgets"). */
export const BUDGET: Record<Level, number> = {full: 60e6, phone: 18e6};
/** The zoom of chunks without the line, and of every chunk on phones. */
export const OVERVIEW_ZOOM = 17;
/** The finest zoom of chunks the line crosses (the run caches zoom 17–21 around its best groups). */
export const LINE_ZOOM = 19;
/** Half the width of the corridor along the line where our cache may hold the finer zooms. */
export const CORRIDOR_M = 60;

/** Half the Web Mercator world's width in metres. */
const HALF = Math.PI * 6378137;

type Affine = PatchMeta["affine"];

/** Grid metres to world pixels (x right, y down) at zoom `z`. */
export function worldPixel(affine: Affine, x: number, y: number, z: number): [number, number] {
  const [lon, lat] = lonLat(affine, x, y), [mx, my] = mercator(lon, lat);
  const scale = TILE_PX * 2 ** z / (2 * HALF);
  return [(mx + HALF) * scale, (HALF - my) * scale];
}

/** The texture of a chunk: its canvas covers world pixels [px0, px0 + width) × [py0, py0 + height) at zoom z. */
export interface TexturePlan {
  z: number;
  px0: number;
  py0: number;
  width: number;
  height: number;
}

/** A chunk's bounds within the patch's samples (chunks are padded with no data), null when none is left. */
export function dataBounds(meta: Pick<PatchMeta, "left" | "top" | "width" | "height" | "res">,
                           b: GridBounds): GridBounds | null {
  const x0 = Math.max(b.x0, meta.left), x1 = Math.min(b.x1, meta.left + meta.width * meta.res);
  const y0 = Math.max(b.y0, meta.top - meta.height * meta.res), y1 = Math.min(b.y1, meta.top);
  return x1 > x0 && y1 > y0 ? {x0, y0, x1, y1} : null;
}

/** The canvas of `bounds` at zoom `z`: the world pixels around its corners (the affine is a plane, so the
 *  corners hold the extremes; Web Mercator keeps their order). */
export function planAt(affine: Affine, b: GridBounds, z: number): TexturePlan {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of [[b.x0, b.y0], [b.x1, b.y0], [b.x0, b.y1], [b.x1, b.y1]]) {
    const [px, py] = worldPixel(affine, x, y, z);
    minX = Math.min(minX, px); maxX = Math.max(maxX, px); minY = Math.min(minY, py); maxY = Math.max(maxY, py);
  }
  const px0 = Math.floor(minX), py0 = Math.floor(minY);
  return {z, px0, py0, width: Math.max(1, Math.ceil(maxX) - px0), height: Math.max(1, Math.ceil(maxY) - py0)};
}

/** The finest zoom up to `maxZoom` whose canvas fits MAX_CANVAS on both sides. */
export function zoomFor(affine: Affine, b: GridBounds, maxZoom: number): TexturePlan {
  let plan = planAt(affine, b, maxZoom);
  while (plan.z > 0 && (plan.width > MAX_CANVAS || plan.height > MAX_CANVAS)) plan = planAt(affine, b, plan.z - 1);
  return plan;
}

/** Bytes of a plan's texture on the GPU: RGBA, a third more for the mipmaps. */
export function textureBytes(p: TexturePlan): number {
  return p.width * p.height * 4 * 4 / 3;
}

/** The finest zoom a chunk may take: the line's chunks LINE_ZOOM on the desktop, the others and phones
 *  OVERVIEW_ZOOM. */
export function maxZoomOf(hasLine: boolean, level: Level): number {
  return level === "full" && hasLine ? LINE_ZOOM : OVERVIEW_ZOOM;
}

/** The textures of the chunks (`bounds` within the patch's data, null: no texture): each at the finest zoom
 *  that fits its canvas, then the largest made coarser, one zoom at a time, until all fit the level's budget. */
export function planTextures(affine: Affine, chunks: {bounds: GridBounds | null; hasLine: boolean}[],
                             level: Level): (TexturePlan | null)[] {
  const plans = chunks.map((c) => c.bounds ? zoomFor(affine, c.bounds, maxZoomOf(c.hasLine, level)) : null);
  const total = () => plans.reduce((sum, p) => sum + (p ? textureBytes(p) : 0), 0);
  while (total() > BUDGET[level]) {
    let k = -1;
    plans.forEach((p, i) => { if (p && p.z > 0 && (k < 0 || textureBytes(p) > textureBytes(plans[k]!))) k = i; });
    if (k < 0) break;
    plans[k] = planAt(affine, chunks[k].bounds!, plans[k]!.z - 1);
  }
  return plans;
}

/** The tiles (x, y) a plan's canvas covers, rows from the top. */
export function tilesOf(p: TexturePlan): [number, number][] {
  const n = 2 ** p.z, tiles: [number, number][] = [];
  const x0 = Math.floor(p.px0 / TILE_PX), x1 = Math.floor((p.px0 + p.width - 1) / TILE_PX);
  const y0 = Math.max(0, Math.floor(p.py0 / TILE_PX)), y1 = Math.min(n - 1, Math.floor((p.py0 + p.height - 1) / TILE_PX));
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) tiles.push([x, y]);
  return tiles;
}

/** Grid metres to the texture's (u, v) of a plan: three.js's convention (flipY: v = 1 at the canvas's top). */
export function uvOf(affine: Affine, p: TexturePlan): (x: number, y: number) => [number, number] {
  return (x, y) => {
    const [px, py] = worldPixel(affine, x, y, p.z);
    return [(px - p.px0) / p.width, 1 - (py - p.py0) / p.height];
  };
}

/** An image drawn into a tile: from `url`, or the square [sx, sy, size] of it enlarged (a coarser tile); `white`:
 *  drawn over white (a WMS asked for a JPEG may answer a PNG, transparent where it has no imagery, which our cache
 *  keeps white: orthophoto.tile_content). */
export interface TileImage { url: string; crop?: [number, number, number]; white?: boolean }

/** A WMS over base tiles composed as orthophoto.tile_content composes our cache's tile: `jpeg` first; all white
 *  (no imagery there) → `base` instead; any white 8×8 block (the coverage's edge) → `base` with `png` (the WMS
 *  transparent where it has no imagery) over it; else `jpeg` alone. */
export interface Composed { jpeg: TileImage; base: TileImage; png: TileImage }

/** How one tile is drawn: `cache` (our cache's tile, which has every layer already) when it is worth trying,
 *  else (or when it fails) `composed` when set, otherwise `layers` bottom first, each from the service (a failed
 *  one is left out). */
export interface TileDraw { x: number; y: number; cache: string | null; layers: TileImage[]; composed?: Composed }

/** A tile of a {z}/{x}/{y} template; above `maxZoom`, the part of its tile there, enlarged. */
export function templateTile(template: string, z: number, x: number, y: number, maxZoom: number): TileImage {
  const up = Math.max(0, z - maxZoom);
  const url = template.replace(/\{z\}/g, String(z - up)).replace(/\{x\}/g, String(x >> up))
                      .replace(/\{y\}/g, String(y >> up));
  if (!up) return {url};
  const n = 2 ** up, part = TILE_PX / n;
  return {url, crop: [(x % n) * part, (y % n) * part, part]};
}

/** WGS84 bounds of a tile in WMS 1.3.0's order for EPSG:4326: south, west, north, east (orthophoto.py _wms_bbox). */
export function wmsBbox(z: number, x: number, y: number): string {
  const n = 2 ** z, lat = (row: number) => Math.atan(Math.sinh(Math.PI * (1 - 2 * row / n))) * 180 / Math.PI;
  return [lat(y + 1), x / n * 360 - 180, lat(y), (x + 1) / n * 360 - 180].join(",");
}

/** (left, bottom, right, top) of a tile in Web Mercator metres (orthophoto.py mercator_box). */
export function mercatorBox(z: number, x: number, y: number): [number, number, number, number] {
  const size = 2 * HALF / 2 ** z;
  return [x * size - HALF, HALF - (y + 1) * size, (x + 1) * size - HALF, HALF - y * size];
}

/** A WMS GetMap of a tile: a JPEG (drawn over white), or with `transparent` a PNG transparent where the service has
 *  no imagery, asked as orthophoto.py _get_map asks: version 1.3.0 with CRS EPSG:4326 in its lat-lon order, or
 *  1.1.1 (`wms_version`, a service taking lon-lat only) with SRS in lon-lat order; with `wms_crs` EPSG:3857 the
 *  tile's Mercator box, x before y in both. */
export function wmsTile(ortho: Ortho, z: number, x: number, y: number, transparent = false): TileImage {
  const url = ortho.url!, version = ortho.wms_version ?? "1.3.0", mercator = ortho.wms_crs === "EPSG:3857";
  const [south, west, north, east] = wmsBbox(z, x, y).split(",");
  const bbox = mercator ? mercatorBox(z, x, y).join(",") : version === "1.1.1" ? [west, south, east, north].join(",")
    : wmsBbox(z, x, y);
  const params: [string, string][] = [
    ["service", "WMS"], ["request", "GetMap"], ["layers", ortho.layer], ["styles", ""],
    ["format", transparent ? "image/png" : "image/jpeg"], ["transparent", String(transparent)], ["version", version],
    ["width", String(TILE_PX)], ["height", String(TILE_PX)],
    [version === "1.1.1" ? "srs" : "crs", mercator ? "EPSG:3857" : "EPSG:4326"]];
  return {url: url + (url.includes("?") ? "&" : "?") +
    params.map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&") + "&bbox=" + bbox,
          ...(transparent ? {} : {white: true})};
}

/** The orthophoto's service for a tile with only one of a WMS (its JPEG) and base tiles. */
export function orthoLayers(ortho: Ortho, z: number, x: number, y: number): TileImage[] {
  return ortho.url ? [wmsTile(ortho, z, x, y)] : ortho.base ? [templateTile(ortho.base.url, z, x, y, ortho.base.max_zoom)] : [];
}

/** The parts of a tile of a WMS over base tiles (the base above its last zoom: the part of its tile there). */
export function orthoComposed(ortho: Ortho, z: number, x: number, y: number): Composed {
  return {jpeg: wmsTile(ortho, z, x, y), base: templateTile(ortho.base!.url, z, x, y, ortho.base!.max_zoom),
          png: wmsTile(ortho, z, x, y, true)};
}

/** A decoded pixel the browser takes for the WMS's white: every channel at least this (orthophoto._white_blocks
 *  asks for a grey of exactly 255; browsers' JPEG decoders may differ by a few levels). */
export const WHITE_MIN = 250;
/** The side of the white blocks that mark the coverage's edge (orthophoto._white_blocks). */
export const WHITE_BLOCK = 8;

/** (all white, any white WHITE_BLOCK × WHITE_BLOCK block on the block grid from the top left) of a tile's RGBA
 *  pixels, rows from the top: orthophoto._white_blocks on decoded pixels (tests/test_view3d_tiles.py compares
 *  them). */
export function whiteBlocks(rgba: ArrayLike<number>, width: number, height: number, min = WHITE_MIN): [boolean, boolean] {
  const white = (k: number) => rgba[4 * k] >= min && rgba[4 * k + 1] >= min && rgba[4 * k + 2] >= min;
  let all = true;
  for (let k = 0; k < width * height && all; k++) all = white(k);
  if (all) return [width * height > 0, width >= WHITE_BLOCK && height >= WHITE_BLOCK];
  const bw = Math.floor(width / WHITE_BLOCK), bh = Math.floor(height / WHITE_BLOCK);
  for (let by = 0; by < bh; by++) {
    for (let bx = 0; bx < bw; bx++) {
      let block = true;
      for (let r = by * WHITE_BLOCK; r < (by + 1) * WHITE_BLOCK && block; r++) {
        for (let c = bx * WHITE_BLOCK; c < (bx + 1) * WHITE_BLOCK && block; c++) block = white(r * width + c);
      }
      if (block) return [false, true];
    }
  }
  return [false, false];
}

/** Our cache's tile ({cache}/{z}/{x}/{y}.jpg, `cache` resolved for the page: result/load.ts orthoForApp). */
export function cacheTile(cache: string, z: number, x: number, y: number): string {
  return `${cache}/${z}/${x}/${y}.jpg`;
}

/** The corridor along the line in world pixels at zoom z: its ends and its half width. */
export interface Corridor { a: [number, number]; b: [number, number]; half: number }

export function corridorOf(affine: Affine, anchors: [Anchor3d, Anchor3d], z: number): Corridor {
  const [p, q] = anchors, a = worldPixel(affine, p.x, p.y, z), b = worldPixel(affine, q.x, q.y, z);
  const metres = Math.hypot(q.x - p.x, q.y - p.y);
  // world pixels per grid metre: along the line, or (one anchor) 1 m east of it
  const e = worldPixel(affine, p.x + 1, p.y, z);
  const scale = metres > 0 ? Math.hypot(b[0] - a[0], b[1] - a[1]) / metres : Math.hypot(e[0] - a[0], e[1] - a[1]);
  return {a, b, half: CORRIDOR_M * scale};
}

function pointSegment(px: number, py: number, a: [number, number], b: [number, number]): number {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = dx * dx + dy * dy;
  const t = len > 0 ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / len)) : 0;
  return Math.hypot(px - a[0] - t * dx, py - a[1] - t * dy);
}

/** The distance between a tile and the corridor's segment in world pixels (0 when they meet). */
export function tileDistance(c: Corridor, x: number, y: number): number {
  const x0 = x * TILE_PX, y0 = y * TILE_PX, x1 = x0 + TILE_PX, y1 = y0 + TILE_PX;
  const inside = (p: [number, number]) => p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
  if (inside(c.a) || inside(c.b)) return 0;
  const corners: [number, number][] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  // the segment crossing an edge of the tile
  const cross = (p: [number, number], q: [number, number], r: [number, number], s: [number, number]) => {
    const d = (q[0] - p[0]) * (s[1] - r[1]) - (q[1] - p[1]) * (s[0] - r[0]);
    if (d === 0) return false;
    const t = ((r[0] - p[0]) * (s[1] - r[1]) - (r[1] - p[1]) * (s[0] - r[0])) / d;
    const u = ((r[0] - p[0]) * (q[1] - p[1]) - (r[1] - p[1]) * (q[0] - p[0])) / d;
    return t >= 0 && t <= 1 && u >= 0 && u <= 1;
  };
  if (corners.some((r, i) => cross(c.a, c.b, r, corners[(i + 1) % 4]))) return 0;
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  return Math.min(...corners.map(([px, py]) => pointSegment(px, py, c.a, c.b)),
                  ...[c.a, c.b].map(([px, py]) => Math.hypot(px - clamp(px, x0, x1), py - clamp(py, y0, y1))));
}

/** Where our cache may have a tile (docs/3d-view-contract.md, "After wave 1"): the whole search area at
 *  zoom ≤ 16, only around the best groups at 17–21; so zoom ≤ 16 from the cache first, zoom 17 straight from
 *  the service, finer zooms from the cache first in the corridor of ±CORRIDOR_M along the line. */
export function cacheFirst(z: number, x: number, y: number, corridor: Corridor | null): boolean {
  if (z <= 16) return true;
  if (z === OVERVIEW_ZOOM || !corridor) return false;
  return tileDistance(corridor, x, y) <= corridor.half;
}

/** The orthophoto's tiles of a plan: a WMS over base tiles composed as our cache's tiles are (Composed: its JPEG,
 *  ~11 KB a tile at R2, where the transparent PNG over every base tile made 13 MB an open), a WMS or base tiles
 *  alone as they are. */
export function orthoDraws(ortho: Ortho, p: TexturePlan, corridor: Corridor | null): TileDraw[] {
  return tilesOf(p).map(([x, y]) => {
    const cache = ortho.cache && cacheFirst(p.z, x, y, corridor) ? cacheTile(ortho.cache, p.z, x, y) : null;
    return ortho.url && ortho.base ? {x, y, cache, layers: [], composed: orthoComposed(ortho, p.z, x, y)}
      : {x, y, cache, layers: orthoLayers(ortho, p.z, x, y)};
  });
}

/** Esri's tiles of a plan (never cached: Esri's terms). */
export function esriDraws(key: string, p: TexturePlan): TileDraw[] {
  const template = esriTileUrl(key);
  return tilesOf(p).map(([x, y]) => ({x, y, cache: null, layers: [templateTile(template, p.z, x, y, ESRI_MAX_ZOOM)]}));
}

/** A service's URL asked again past the browser's cache (a response the 2D map cached without `Vary: Origin`
 *  fails the CORS check of an anonymous request). */
export function cacheBusted(url: string, attempt = 1): string {
  return url + (url.includes("?") ? "&" : "?") + "_fal3d=" + attempt;
}

/** The meta's `ortho` as the run's Ortho, or null when it is none. */
export function orthoOf(value: unknown): Ortho | null {
  const o = value as Ortho | null;
  if (!o || typeof o !== "object" || typeof o.name !== "string" || typeof o.attribution !== "string") return null;
  if (!o.url && !(o.base && typeof o.base.url === "string")) return null;
  return o;
}
