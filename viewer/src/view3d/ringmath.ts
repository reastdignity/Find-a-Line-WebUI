// The coarse ring's geometry and choices, pure (tested in Node: tests/test_view3d_ring.py; docs/3d-view-contract.md,
// "Wave 3", V3b): the extent and the levels per page level, the frame from the tiles' Earth-centred coordinates
// (WGS84, Z to the north pole, as 3DTilesRendererJS places them) into the scene's (origin at the patch's centre,
// X east, Y up, Z south) through the meta's affine, the cut-out under the patch as clipping planes, the imagery's
// overlay per kind, and the samples along the patch's edge where the ring's heights are compared with the patch's.

import { esriTileUrl, ESRI_MAX_ZOOM } from "../layers";
import type { Ortho } from "../types";
import type { Patch, PatchMeta } from "./decode";
import type { Origin } from "./geometry";
import type { Level } from "./page";

/** Per page level: the ring's radius from the patch's centre (metres), the zoom of the elevation tiles read
 *  (even: the plugin fetches every second zoom), and the mesh's spacing wanted by distance (metres; each tile is
 *  a 32 × 32 mesh displaced by its elevation tile). */
export interface RingLevel {
  radius: number;
  zoom: number;
  spacing: [number, number][];  // [up to distance, spacing], the last for the rest
  /** Pixels of the imagery composed per tile (ImageOverlayPlugin's resolution). */
  imagery: number;
}

export const RING: Record<Level, RingLevel> = {
  full: {radius: 6000, zoom: 12, spacing: [[2000, 30], [4000, 60], [Infinity, 120]], imagery: 128},
  phone: {radius: 3000, zoom: 10, spacing: [[1500, 60], [Infinity, 120]], imagery: 128},
};

/** The deepest tile level of the ring's tree (meshes finer than the elevation tiles read). */
export const MESH_ZOOM = 15;
/** Segments of a tile's mesh (TerrainRGBMeshPlugin's MESH_SIZE). */
export const MESH_SEGMENTS = 32;
/** Tile pixels of the elevation tiles (Mapterhorn's: 512). */
export const TERRAIN_PX = 512;

/** The mesh spacing wanted at `distance` metres from the patch's centre. */
export function spacingAt(level: RingLevel, distance: number): number {
  for (const [upTo, s] of level.spacing) if (distance <= upTo) return s;
  return level.spacing[level.spacing.length - 1][1];
}

/** Whether a tile of the plugin (geometric error: its pixel's size in metres) is refined at `distance`: its
 *  mesh (TERRAIN_PX / MESH_SEGMENTS pixels a segment) is coarser than wanted there. */
export function refines(level: RingLevel, geometricError: number, distance: number): boolean {
  return geometricError * TERRAIN_PX / MESH_SEGMENTS > spacingAt(level, distance) * 1.0001;
}

// WGS84
const A = 6378137, F = 1 / 298.257223563, E2 = F * (2 - F);

/** Earth-centred coordinates of lon/lat (degrees) and the height above the ellipsoid (metres). */
export function ecef(lon: number, lat: number, h: number): [number, number, number] {
  const p = lat * Math.PI / 180, l = lon * Math.PI / 180, s = Math.sin(p), c = Math.cos(p);
  const n = A / Math.sqrt(1 - E2 * s * s);
  return [(n + h) * c * Math.cos(l), (n + h) * c * Math.sin(l), (n * (1 - E2) + h) * s];
}

/** The 4 × 4 matrix (row-major) from the tiles' Earth-centred frame into the scene's: east-north-up at the
 *  patch's centre at the origin's height above the ellipsoid, then east/north to grid metres by the inverse of
 *  the affine's derivative (the projection's scale and convergence there). Heights stay as the tiles give them
 *  (above the ellipsoid in the plugin, so as the patch's: the same datum assumed); the Earth's curvature remains
 *  (2.8 m below the plane at 6 km). */
export function ringFrame(meta: Pick<PatchMeta, "affine">, origin: Origin): number[] {
  const [a0, a1, a2, b0, b1, b2] = meta.affine;
  const lon = a0 + a1 * origin.cx + a2 * origin.cy, lat = b0 + b1 * origin.cx + b2 * origin.cy;
  const p = lat * Math.PI / 180, l = lon * Math.PI / 180, sp = Math.sin(p), cp = Math.cos(p);
  const sl = Math.sin(l), cl = Math.cos(l);
  const east = [-sl, cl, 0], north = [-sp * cl, -sp * sl, cp], up = [cp * cl, cp * sl, sp];
  const o = ecef(lon, lat, origin.h0);
  // metres per degree east and north at the origin's height (the grid's metres are the patch's there: a
  // kilometre of grid is 1400 m above the ellipsoid 22 cm more than on it)
  const w = Math.sqrt(1 - E2 * sp * sp), n = A / w, m = A * (1 - E2) / (w * w * w);
  const kE = Math.PI / 180 * (n + origin.h0) * cp, kN = Math.PI / 180 * (m + origin.h0);
  // (E, N) = D·J·(dx, dy); G = (D·J)⁻¹ gives grid metres of local east/north metres
  const j00 = kE * a1, j01 = kE * a2, j10 = kN * b1, j11 = kN * b2, det = j00 * j11 - j01 * j10;
  const g00 = j11 / det, g01 = -j01 / det, g10 = -j10 / det, g11 = j00 / det;
  // rows of the scene's X (= dx), Y (= up from h0), Z (= −dy) over (E, N, U)
  const rows = [[g00, g01, 0], [0, 0, 1], [-g10, -g11, 0]];
  const offsets = [0, 0, 0];  // up is from the origin's height already
  const out: number[] = [];
  for (let r = 0; r < 3; r++) {
    // the row over ECEF: Σ_k rows[r][k] · axis_k
    const v = [0, 1, 2].map((i) => rows[r][0] * east[i] + rows[r][1] * north[i] + rows[r][2] * up[i]);
    out.push(v[0], v[1], v[2], offsets[r] - (v[0] * o[0] + v[1] * o[1] + v[2] * o[2]));
  }
  out.push(0, 0, 0, 1);
  return out;
}

/** The patch's centre in the tiles' frame (on the ellipsoid at the origin's height). */
export function centreEcef(meta: Pick<PatchMeta, "affine">, origin: Origin): [number, number, number] {
  const [a0, a1, a2, b0, b1, b2] = meta.affine;
  return ecef(a0 + a1 * origin.cx + a2 * origin.cy, b0 + b1 * origin.cx + b2 * origin.cy, origin.h0);
}

/** Grid metres: x0 west, x1 east, y0 south, y1 north. */
export interface Rect { x0: number; y0: number; x1: number; y1: number }

/** The outer edges of the patch's samples with data (the whole patch when it has data everywhere); null
 *  without any. */
export function dataRect(patch: Pick<Patch, "meta" | "heights" | "cols">): Rect | null {
  const {left, top, res, width, height} = patch.meta;
  let i0 = Infinity, i1 = -1, j0 = Infinity, j1 = -1;
  for (let i = 0; i < height; i++) {
    const row = i * patch.cols;
    for (let j = 0; j < width; j++) {
      if (Number.isNaN(patch.heights[row + j])) continue;
      if (i < i0) i0 = i;
      if (i > i1) i1 = i;
      if (j < j0) j0 = j;
      if (j > j1) j1 = j;
    }
  }
  if (i1 < 0) return null;
  return {x0: left + j0 * res, x1: left + (j1 + 1) * res, y0: top - (i1 + 1) * res, y1: top - i0 * res};
}

/** A plane of the scene as three.js's: points p with normal·p + constant < 0 are clipped. */
export interface PlaneSpec { normal: [number, number, number]; constant: number }

/** The four planes that, with `clipIntersection` (a point is clipped only when on the clipped side of all),
 *  cut the ring out over the rectangle `r`: inside X ∈ (x0, x1), Z ∈ (−(y1 − cy), −(y0 − cy)). */
export function cutPlanes(r: Rect, origin: Origin): PlaneSpec[] {
  const X0 = r.x0 - origin.cx, X1 = r.x1 - origin.cx, Z0 = -(r.y1 - origin.cy), Z1 = -(r.y0 - origin.cy);
  return [{normal: [-1, 0, 0], constant: X0}, {normal: [1, 0, 0], constant: -X1},
          {normal: [0, 0, -1], constant: Z0}, {normal: [0, 0, 1], constant: -Z1}];
}

/** Whether a scene point is cut out by `planes` (all of them clip it). */
export function isCut(planes: PlaneSpec[], p: [number, number, number]): boolean {
  return planes.every((q) => q.normal[0] * p[0] + q.normal[1] * p[1] + q.normal[2] * p[2] + q.constant < 0);
}

/** One image overlay of the ring: XYZ tiles of a template, or a WMS (1.3.0, EPSG:4326). */
export type OverlaySpec =
  | {type: "xyz"; url: string; levels: number}
  | {type: "wms"; url: string; layer: string; format: string; transparent: boolean};

/** The overlays of an imagery kind, bottom first: Esri's tiles; the orthophoto's base tiles with its WMS over
 *  them (transparent where it has no imagery, as the 2D map asks), or either alone; none for the shaded
 *  terrain. Our cache is not used for the ring. */
export function overlaySpecs(kind: "ortho" | "esri" | "shaded", ortho: Ortho | null, esriKey: string | null):
    OverlaySpec[] {
  if (kind === "esri" && esriKey) return [{type: "xyz", url: esriTileUrl(esriKey), levels: ESRI_MAX_ZOOM + 1}];
  if (kind !== "ortho" || !ortho) return [];
  const specs: OverlaySpec[] = [];
  if (ortho.base) specs.push({type: "xyz", url: ortho.base.url, levels: ortho.base.max_zoom + 1});
  if (ortho.url) specs.push({type: "wms", url: ortho.url, layer: ortho.layer,
                             format: ortho.base ? "image/png" : "image/jpeg", transparent: !!ortho.base});
  return specs;
}

/** The elevation tiles (x, y) at zoom z whose squares come within `radius` metres of lon/lat: those the ring
 *  reads (for the budget: tiles × their size). */
export function tilesWithin(lon: number, lat: number, radius: number, z: number): [number, number][] {
  const n = 2 ** z, dLat = radius / 111320, dLon = radius / (111320 * Math.cos(lat * Math.PI / 180));
  const tx = (lo: number) => Math.floor((lo + 180) / 360 * n);
  const ty = (la: number) => {
    const p = la * Math.PI / 180;
    return Math.floor((1 - Math.log(Math.tan(p) + 1 / Math.cos(p)) / Math.PI) / 2 * n);
  };
  const tiles: [number, number][] = [];
  for (let y = ty(lat + dLat); y <= ty(lat - dLat); y++)
    for (let x = tx(lon - dLon); x <= tx(lon + dLon); x++) tiles.push([x, y]);
  return tiles;
}

/** Samples along the edge of the patch's data rectangle, one every `every` samples, with their heights: where
 *  the ring meets the patch (the offsets of the ring's heights are measured there). */
export function edgeSamples(patch: Pick<Patch, "meta" | "heights" | "cols">, every = 8):
    {x: number; y: number; h: number}[] {
  const r = dataRect(patch);
  if (!r) return [];
  const {left, top, res} = patch.meta;
  const j0 = Math.round((r.x0 - left) / res), j1 = Math.round((r.x1 - left) / res) - 1;
  const i0 = Math.round((top - r.y1) / res), i1 = Math.round((top - r.y0) / res) - 1;
  const out: {x: number; y: number; h: number}[] = [];
  const add = (i: number, j: number) => {
    const h = patch.heights[i * patch.cols + j];
    if (!Number.isNaN(h)) out.push({x: left + (j + 0.5) * res, y: top - (i + 0.5) * res, h});
  };
  for (let j = j0; j <= j1; j += every) { add(i0, j); add(i1, j); }
  for (let i = i0 + every; i < i1; i += every) { add(i, j0); add(i, j1); }
  return out;
}

/** The median and the 90th percentile of |values| (null when empty). */
export function offsetStats(values: number[]): {median: number; p90: number} | null {
  if (!values.length) return null;
  const a = values.map(Math.abs).sort((p, q) => p - q);
  const at = (q: number) => a[Math.min(a.length - 1, Math.floor(q * (a.length - 1) + 0.5))];
  return {median: at(0.5), p90: at(0.9)};
}
