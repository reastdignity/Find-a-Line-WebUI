// The trees and buildings of the 3D view, the pure part (docs/3d-view-contract.md, "Round 2": "The block of trees
// and buildings" and "V, the canopy"; tested in Node: tests/test_view3d_canopy.py). The answer of
// GET /api/patch?part=canopy is framed as the patch's (`uint32 LE N`, N bytes of JSON meta, the deflated values):
// one uint8 a sample on the patch's grid, row-major from the top, the height of the obstacle surface above the
// terrain in units of `quantum` (0: none, below `min_height`, no data). From it a lattice of cells of k × k samples
// (the largest value of a cell decides whether it is drawn and how tall) becomes one indexed mesh: the cells'
// tops on shared corners, so a wood reads as one surface, at the terrain's height plus the cells' value, and side
// faces from the edge of a drawn region down to a little under the terrain, so it reads as a volume. The lattice
// is made coarser (k grows) until the mesh fits the vertex budget. No triangles over no data.

import { inflate, splitAnswer } from "./decode";
import { toScene, type Origin } from "./geometry";

/** The meta of the answer for `part=canopy`. */
export interface CanopyMeta {
  part: "canopy";
  width: number;
  height: number;
  step: number;
  res: number;
  left: number;
  top: number;
  /** Metres per unit of a value (0.5). */
  quantum: number;
  /** The smallest height drawn, metres (1). */
  min_height: number;
  rule: unknown;
  /** Samples above 0. */
  cells: number;
  sha256: string;
}

/** A failure to decode: the answer is not what the contract says. */
export class CanopyError extends Error {}

export interface CanopyData { meta: CanopyMeta; values: Uint8Array }

export async function sha256Hex(body: Uint8Array): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;  // not a secure context: left unchecked, as main.ts does
  const digest = await crypto.subtle.digest("SHA-256", body as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** The meta and the values of an answer: the sha256 of the deflated values checked (where it can be), inflated,
 *  the length checked against the meta. Throws CanopyError. */
export async function decodeCanopy(answer: ArrayBuffer, sha: (b: Uint8Array) => Promise<string | null> = sha256Hex):
    Promise<CanopyData> {
  let meta: CanopyMeta, body: Uint8Array;
  try {
    ({meta, body} = splitAnswer(answer) as unknown as {meta: CanopyMeta; body: Uint8Array});
  } catch (e) {
    throw new CanopyError((e as Error).message);
  }
  if (meta.part !== "canopy" || !(meta.width > 0 && meta.height > 0)) throw new CanopyError("not the canopy block");
  const digest = await sha(body);
  if (digest !== null && digest !== meta.sha256) throw new CanopyError("the block's checksum differs");
  let values: Uint8Array;
  try {
    values = await inflate(body);
  } catch (e) {
    throw new CanopyError((e as Error).message);
  }
  if (values.byteLength !== meta.width * meta.height) {
    throw new CanopyError(`expected ${meta.width * meta.height} values, got ${values.byteLength}`);
  }
  return {meta, values};
}

/** The grid of the samples: the patch's (docs/3d-view-contract.md, "/api/patch": the centre of sample (i, j) is
 *  at left + (j + .5)·res, top − (i + .5)·res). */
export interface Grid { width: number; height: number; res: number; left: number; top: number }

/** The patch's heights in metres (NaN for no data) with their row stride (decode.ts `Patch`: padded to 512·k + 1). */
export interface Ground extends Grid { heights: Float32Array; cols: number }

/** The canopy's grid is the patch's (same request, same step): else the answer is not for this patch. */
export function sameGrid(a: Grid, b: Grid): boolean {
  const near = (x: number, y: number) => Math.abs(x - y) <= 1e-6 * Math.max(1, Math.abs(x));
  return a.width === b.width && a.height === b.height && near(a.res, b.res) && near(a.left, b.left) && near(a.top, b.top);
}

/** The smallest value drawn: `min_height` in units of `quantum`, at least 1. */
export function minValue(meta: Pick<CanopyMeta, "min_height" | "quantum">): number {
  return Math.max(1, Math.ceil(meta.min_height / meta.quantum - 1e-9));
}

/** The vertex budgets of the canopy: a third of the terrain's (scene.ts VERTEX_BUDGET: 300 000 and 130 000). */
export const CANOPY_BUDGET = {full: 100_000, phone: 43_000};
/** The cell's side asked, metres (the lattice grows coarser from it until the mesh fits). */
export const CELL_METRES = {full: 2, phone: 4};

/** A lattice of cells of k × k samples over the grid. */
export interface Lattice {
  /** Samples per cell side. */
  k: number;
  /** Columns and rows of cells. */
  nx: number;
  ny: number;
  /** The largest value of each cell, row-major, 0 where it is not drawn (below `minValue`). */
  cells: Uint8Array;
  /** Cells drawn, their distinct corners and their sides next to no cell drawn (or the patch's edge). */
  drawn: number;
  corners: number;
  edges: number;
  /** What the mesh will hold at most (corners + 4 per side face; some cells may drop out over no data). */
  vertices: number;
  triangles: number;
}

/** The lattice of `k` samples a cell: each cell the largest value of its samples, drawn from `min` up. */
export function lattice(values: Uint8Array, width: number, height: number, k: number, min: number): Lattice {
  const nx = Math.ceil(width / k), ny = Math.ceil(height / k), cells = new Uint8Array(nx * ny);
  const column = new Int32Array(width);
  for (let j = 0; j < width; j++) column[j] = Math.floor(j / k);
  for (let i = 0; i < height; i++) {
    const row = Math.floor(i / k) * nx, at = i * width;
    for (let j = 0; j < width; j++) {
      const v = values[at + j];
      if (v > cells[row + column[j]]) cells[row + column[j]] = v;
    }
  }
  return counted(cells, nx, ny, k, min);
}

/** `cells` (largest values) cut at `min` and the lattice's counts. */
function counted(cells: Uint8Array, nx: number, ny: number, k: number, min: number): Lattice {
  const seen = new Uint8Array((nx + 1) * (ny + 1));
  let drawn = 0, corners = 0, edges = 0;
  const on = (r: number, c: number) => r >= 0 && r < ny && c >= 0 && c < nx && cells[r * nx + c] > 0;
  for (let c = 0; c < cells.length; c++) if (cells[c] < min) cells[c] = 0;
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      if (!cells[r * nx + c]) continue;
      drawn++;
      for (const at of [r * (nx + 1) + c, r * (nx + 1) + c + 1, (r + 1) * (nx + 1) + c, (r + 1) * (nx + 1) + c + 1]) {
        if (!seen[at]) { seen[at] = 1; corners++; }
      }
      edges += +!on(r - 1, c) + +!on(r + 1, c) + +!on(r, c - 1) + +!on(r, c + 1);
    }
  }
  return {k, nx, ny, cells, drawn, corners, edges, vertices: corners + 4 * edges, triangles: 2 * drawn + 2 * edges};
}

/** The finest lattice from `k0` samples a cell whose mesh fits `budget` vertices: k grows by at least one, and by
 *  the square root of the excess, which cannot pass the answer (the vertices never fall faster than with k²). */
export function chooseLattice(values: Uint8Array, width: number, height: number, k0: number, min: number,
                              budget: number): Lattice {
  let k = Math.max(1, Math.floor(k0));
  for (;;) {
    const found = lattice(values, width, height, k, min);
    if (found.vertices <= budget || k >= Math.max(width, height)) return found;
    k = Math.max(k + 1, Math.floor(k * Math.sqrt(found.vertices / budget)));
  }
}

/** The samples a cell is asked at: `cell` metres over `res` metres a sample, at least one. */
export function samplesPerCell(cell: number, res: number): number {
  return Math.max(1, Math.round(cell / res));
}

/** The terrain's height at grid metres, bilinear between the sample centres with the edge clamped, over the
 *  samples that have data only (their weights renormalised); NaN where the four around it have none. */
export function groundAt(g: Ground, x: number, y: number): number {
  const u = Math.min(g.width - 1, Math.max(0, (x - g.left) / g.res - 0.5));
  const v = Math.min(g.height - 1, Math.max(0, (g.top - y) / g.res - 0.5));
  const j = Math.min(g.width - 2, Math.floor(u)), i = Math.min(g.height - 2, Math.floor(v));
  const j0 = Math.max(0, j), i0 = Math.max(0, i), a = u - j0, b = v - i0;
  let sum = 0, weight = 0;
  for (let di = 0; di < 2; di++) {
    for (let dj = 0; dj < 2; dj++) {
      const r = Math.min(g.height - 1, i0 + di), c = Math.min(g.width - 1, j0 + dj), h = g.heights[r * g.cols + c];
      if (Number.isNaN(h)) continue;
      const w = (dj ? a : 1 - a) * (di ? b : 1 - b);
      sum += h * w;
      weight += w;
    }
  }
  return weight > 1e-9 ? sum / weight : NaN;
}

export interface CanopyMesh {
  /** Scene coordinates (x, y, z per vertex), the normals, the triangles' vertex indices. */
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
  vertices: number;
  triangles: number;
  /** Cells drawn, sides faced, and the samples per cell side (the lattice's k). */
  cells: number;
  edges: number;
  k: number;
}

/** The mesh of a lattice over `ground`: the cells' tops on shared corners at the terrain's height plus the
 *  corner's value (the largest of the drawn cells around it) times `quantum`; a cell with a corner over no data
 *  is dropped; a side face from each side next to no cell down to `sink` metres under the terrain (so the
 *  terrain's own mesh, which may differ from the samples by its error, hides the foot); the scene's axes as
 *  geometry.ts `toScene` gives them. Top faces point up; side faces carry their outward flat normal. */
export function buildMesh(ground: Ground, lat: Lattice, origin: Origin, quantum: number, sink: number): CanopyMesh {
  const {nx, ny, k} = lat, cw = nx + 1;
  // The corners' places: the outer edges of the cells' samples, kept inside the terrain mesh's extent (the
  // samples' centres of the first and last row and column)
  const x0 = ground.left + 0.5 * ground.res, x1 = ground.left + (ground.width - 0.5) * ground.res;
  const y0 = ground.top - (ground.height - 0.5) * ground.res, y1 = ground.top - 0.5 * ground.res;
  const cornerX = (c: number) => Math.min(x1, Math.max(x0, ground.left + Math.min(c * k, ground.width) * ground.res));
  const cornerY = (r: number) => Math.min(y1, Math.max(y0, ground.top - Math.min(r * k, ground.height) * ground.res));
  const base = new Float32Array(cw * (ny + 1)).fill(NaN), known = new Uint8Array(cw * (ny + 1));
  const baseAt = (r: number, c: number) => {
    const at = r * cw + c;
    if (!known[at]) { known[at] = 1; base[at] = groundAt(ground, cornerX(c), cornerY(r)); }
    return base[at];
  };
  // The cells drawn: those whose four corners have a terrain height
  const cells = new Uint8Array(nx * ny), top = new Uint8Array(cw * (ny + 1));
  let drawn = 0;
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      const v = lat.cells[r * nx + c];
      if (!v) continue;
      if (Number.isNaN(baseAt(r, c) + baseAt(r, c + 1) + baseAt(r + 1, c) + baseAt(r + 1, c + 1))) continue;
      cells[r * nx + c] = v;
      drawn++;
      for (const at of [r * cw + c, r * cw + c + 1, (r + 1) * cw + c, (r + 1) * cw + c + 1]) if (v > top[at]) top[at] = v;
    }
  }
  const on = (r: number, c: number) => r >= 0 && r < ny && c >= 0 && c < nx && cells[r * nx + c] > 0;
  const sides: [number, number, number][] = [];  // [cell row, cell column, side 0 north, 1 east, 2 south, 3 west]
  const index = new Int32Array(cw * (ny + 1)).fill(-1);
  let corners = 0;
  for (let at = 0; at < top.length; at++) if (top[at]) index[at] = corners++;
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      if (!cells[r * nx + c]) continue;
      if (!on(r - 1, c)) sides.push([r, c, 0]);
      if (!on(r, c + 1)) sides.push([r, c, 1]);
      if (!on(r + 1, c)) sides.push([r, c, 2]);
      if (!on(r, c - 1)) sides.push([r, c, 3]);
    }
  }
  const vertices = corners + 4 * sides.length, triangles = 2 * drawn + 2 * sides.length;
  const positions = new Float32Array(3 * vertices), normals = new Float32Array(3 * vertices);
  const indices = new Uint32Array(3 * triangles);
  const topOf = (r: number, c: number) => base[r * cw + c] + top[r * cw + c] * quantum;
  for (let r = 0; r <= ny; r++) {
    for (let c = 0; c <= nx; c++) {
      const at = index[r * cw + c];
      if (at < 0) continue;
      positions.set(toScene(origin, cornerX(c), cornerY(r), topOf(r, c)), 3 * at);
    }
  }
  // The tops: two triangles a cell, seen from above counter-clockwise (north-west, south-west, north-east, then
  // north-east, south-west, south-east); the corners' normals the sum of the faces around them
  let t = 0;
  const face = (a: number, b: number, c: number) => {
    indices[t++] = a; indices[t++] = b; indices[t++] = c;
    const ax = positions[3 * b] - positions[3 * a], ay = positions[3 * b + 1] - positions[3 * a + 1];
    const az = positions[3 * b + 2] - positions[3 * a + 2];
    const bx = positions[3 * c] - positions[3 * a], by = positions[3 * c + 1] - positions[3 * a + 1];
    const bz = positions[3 * c + 2] - positions[3 * a + 2];
    const nxv = ay * bz - az * by, nyv = az * bx - ax * bz, nzv = ax * by - ay * bx;  // the area-weighted normal
    for (const v of [a, b, c]) { normals[3 * v] += nxv; normals[3 * v + 1] += nyv; normals[3 * v + 2] += nzv; }
  };
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      if (!cells[r * nx + c]) continue;
      const nw = index[r * cw + c], ne = index[r * cw + c + 1], sw = index[(r + 1) * cw + c], se = index[(r + 1) * cw + c + 1];
      face(nw, sw, ne);
      face(ne, sw, se);
    }
  }
  for (let v = 0; v < corners; v++) {
    const l = Math.hypot(normals[3 * v], normals[3 * v + 1], normals[3 * v + 2]) || 1;
    normals[3 * v] /= l; normals[3 * v + 1] /= l; normals[3 * v + 2] /= l;
  }
  // The sides: clockwise seen from above, so a side's quad (P, Q, Q', P') faces outwards; P' and Q' under the terrain
  const OUT = [[0, 0, -1], [1, 0, 0], [0, 0, 1], [-1, 0, 0]];
  const FROM = [[0, 0], [0, 1], [1, 1], [1, 0]], TO = [[0, 1], [1, 1], [1, 0], [0, 0]];  // [row, column] offsets
  let v = corners;
  for (const [r, c, s] of sides) {
    const [pr, pc] = [r + FROM[s][0], c + FROM[s][1]], [qr, qc] = [r + TO[s][0], c + TO[s][1]];
    const first = v;
    for (const [rr, cc, down] of [[pr, pc, 0], [qr, qc, 0], [qr, qc, 1], [pr, pc, 1]]) {
      const h = down ? base[rr * cw + cc] - sink : topOf(rr, cc);
      positions.set(toScene(origin, cornerX(cc), cornerY(rr), h), 3 * v);
      normals.set(OUT[s], 3 * v);
      v++;
    }
    indices[t++] = first; indices[t++] = first + 1; indices[t++] = first + 3;
    indices[t++] = first + 1; indices[t++] = first + 2; indices[t++] = first + 3;
  }
  return {positions, normals, indices, vertices, triangles, cells: drawn, edges: sides.length, k};
}
