// The terrain's meshes (docs/3d-view-contract.md, "Chunks"): the padded grid in chunks of 513 × 513 samples,
// one shared Martini(513), no triangles over no data, skirts along the edges between chunks, and the samples
// of the anchors and of the line's footprint forced into the mesh. Pure (no three.js), so the page and Node
// tests share it; positions in the scene's axes (geometry.ts), normals from the grid's slopes.

import Martini, { type Tile } from "./martini";
import { CHUNK, type Anchor3d, type Patch, type PatchMeta } from "./decode";
import type { Origin } from "./geometry";

let shared: Martini | null = null;

/** The one Martini of the page (its triangle table takes a moment and 2 MB). */
export function martini(): Martini {
  return shared || (shared = new Martini(CHUNK + 1));
}

export interface ChunkMesh {
  ci: number;
  cj: number;
  /** X, Y, Z of each vertex: the surface's first, then the skirts' lower edges. */
  positions: Float32Array;
  /** The surface's normal at each vertex (a skirt's lower vertex takes its upper one's). */
  normals: Float32Array;
  /** x, y grid metres of each vertex (for texture UVs). */
  grid: Float64Array;
  /** The padded grid's index (row · cols + column) of each vertex's sample. */
  samples: Int32Array;
  indices: Uint32Array;
  /** The surface's vertices and index entries (the skirts follow them). */
  surfaceVertices: number;
  surfaceIndices: number;
  /** The found line's footprint crosses the chunk. */
  hasLine: boolean;
}

/** The number of chunks down and across: [rows, columns]. */
export function chunkCount(patch: Pick<Patch, "cols" | "rows">): [number, number] {
  return [(patch.rows - 1) / CHUNK, (patch.cols - 1) / CHUNK];
}

/** The samples (row, column) whose cells (res × res around their centres) the straight segment between two
 *  points in grid metres crosses, in order from the first (a grid traversal; a corner crossed touches both
 *  cells beside it). */
export function footprint(meta: Pick<PatchMeta, "left" | "top" | "res">, a: {x: number; y: number},
                          b: {x: number; y: number}): [number, number][] {
  const u1 = (a.x - meta.left) / meta.res, v1 = (meta.top - a.y) / meta.res;
  const u2 = (b.x - meta.left) / meta.res, v2 = (meta.top - b.y) / meta.res;
  let j = Math.floor(u1), i = Math.floor(v1);
  const jEnd = Math.floor(u2), iEnd = Math.floor(v2), du = u2 - u1, dv = v2 - v1;
  const stepJ = Math.sign(du), stepI = Math.sign(dv);
  const deltaJ = du ? Math.abs(1 / du) : Infinity, deltaI = dv ? Math.abs(1 / dv) : Infinity;
  let tJ = du > 0 ? (j + 1 - u1) / du : du < 0 ? (u1 - j) / -du : Infinity;
  let tI = dv > 0 ? (i + 1 - v1) / dv : dv < 0 ? (v1 - i) / -dv : Infinity;
  const out: [number, number][] = [[i, j]];
  const limit = Math.abs(jEnd - j) + Math.abs(iEnd - i) + 2;
  for (let n = 0; (i !== iEnd || j !== jEnd) && n < limit; n++) {
    const t = Math.min(tJ, tI);
    if (t > 1) break;
    if (Math.abs(tJ - tI) < 1e-12) {  // through a corner: the two cells beside it are touched too
      out.push([i, j + stepJ], [i + stepI, j]);
      i += stepI; j += stepJ; tJ += deltaJ; tI += deltaI;
    } else if (tJ < tI) {
      j += stepJ; tJ += deltaJ;
    } else {
      i += stepI; tI += deltaI;
    }
    out.push([i, j]);
  }
  return out;
}

/** The samples forced into the mesh, as a mask over the padded grid: the anchors' and the line's footprint
 *  (`line`), and the samples on both sides of every edge between data and no data (`all`), so that no kept
 *  triangle reaches over no data however coarse the mesh (Martini's triangles hold no vertex but their corners:
 *  a triangle with samples of both kinds would hold a forced pair, both its corners, one of them no data). */
export function forcedSamples(patch: Patch, anchors: [Anchor3d, Anchor3d] = patch.meta.anchors):
    {all: Uint8Array; line: [number, number][]} {
  const {heights, cols, rows} = patch, all = new Uint8Array(cols * rows);
  const line = footprint(patch.meta, anchors[0], anchors[1]).filter(([i, j]) => i >= 0 && j >= 0 && i < rows && j < cols);
  for (const [i, j] of line) all[i * cols + j] = 1;
  for (let i = 0; i < rows; i++) {
    for (let j = 0; j < cols; j++) {
      const k = i * cols + j;
      if (Number.isNaN(heights[k])) continue;
      for (let di = -1; di <= 1; di++) {
        const r = i + di;
        if (r < 0 || r >= rows) continue;
        for (let dj = -1; dj <= 1; dj++) {
          const c = j + dj;
          if (c < 0 || c >= cols || !Number.isNaN(heights[r * cols + c])) continue;
          all[k] = 1;
          all[r * cols + c] = 1;
        }
      }
    }
  }
  return {all, line};
}

/** Martini's tile of chunk (ci, cj) with the forced samples' errors infinite (propagated to the triangles above
 *  them by a second pass); null when the chunk holds no data. */
export function chunkTile(patch: Patch, ci: number, cj: number, forced: Uint8Array, h0: number): Tile | null {
  const size = CHUNK + 1, i0 = ci * CHUNK, j0 = cj * CHUNK, {heights, cols} = patch;
  const terrain = new Float32Array(size * size);
  let any = false, anyForced = false;
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const h = heights[(i0 + r) * cols + j0 + c];
      if (Number.isNaN(h)) terrain[r * size + c] = h0;  // a stand-in: its triangles are left out
      else { terrain[r * size + c] = h; any = true; }
    }
  }
  if (!any) return null;
  const tile = martini().createTile(terrain);
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (forced[(i0 + r) * cols + j0 + c]) { tile.errors[r * size + c] = Infinity; anyForced = true; }
    }
  }
  if (anyForced) tile.update();  // keeps the infinite errors (a maximum) and carries them up the tree
  return tile;
}

/** The surface's unit normal at a sample of the padded grid from its neighbours' heights. */
function normalAt(patch: Patch, i: number, j: number, out: Float32Array, at: number) {
  const {heights, cols, rows} = patch, res = patch.meta.res, h = heights[i * cols + j];
  const get = (r: number, c: number) => r < 0 || c < 0 || r >= rows || c >= cols ? NaN : heights[r * cols + c];
  const slope = (minus: number, plus: number) => {
    if (!Number.isNaN(minus) && !Number.isNaN(plus)) return (plus - minus) / (2 * res);
    if (!Number.isNaN(plus) && !Number.isNaN(h)) return (plus - h) / res;
    if (!Number.isNaN(minus) && !Number.isNaN(h)) return (h - minus) / res;
    return 0;
  };
  const gx = slope(get(i, j - 1), get(i, j + 1));      // up towards the east
  const gy = slope(get(i + 1, j), get(i - 1, j));      // up towards the north (rows run south)
  const n = Math.hypot(gx, 1, gy);
  out[at] = -gx / n; out[at + 1] = 1 / n; out[at + 2] = gy / n;  // Y = h, Z = −y
}

/** How far the skirts reach below the edges, for a mesh within `maxError` metres. */
export function skirtDepth(maxError: number): number {
  return 2 + 4 * maxError;
}

/** The mesh of chunk (ci, cj) from its tile within `maxError` metres: triangles over no data left out, its
 *  vertices those of the kept triangles, skirts along the edges it shares with other chunks. */
export function chunkMesh(patch: Patch, origin: Origin, ci: number, cj: number, tile: Tile, maxError: number,
                          lineSamples: [number, number][] = []): ChunkMesh {
  const i0 = ci * CHUNK, j0 = cj * CHUNK, {heights, cols} = patch, {left, top, res} = patch.meta;
  const [chunkRows, chunkCols] = chunkCount(patch);
  const {vertices, triangles} = tile.getMesh(maxError);
  const n = vertices.length / 2, use = new Int32Array(n).fill(-1);
  const missing = (v: number) => Number.isNaN(heights[(i0 + vertices[2 * v + 1]) * cols + j0 + vertices[2 * v]]);
  const kept: number[] = [];
  let used = 0;
  for (let t = 0; t < triangles.length; t += 3) {
    const a = triangles[t], b = triangles[t + 1], c = triangles[t + 2];
    if (missing(a) || missing(b) || missing(c)) continue;
    for (const v of [a, b, c]) {
      if (use[v] < 0) use[v] = used++;
      kept.push(use[v]);
    }
  }
  // The skirts: the edges shared with another chunk, between neighbouring vertices with data all along
  const local = new Int32Array(used * 2);
  for (let v = 0; v < n; v++) {
    if (use[v] >= 0) { local[2 * use[v]] = vertices[2 * v]; local[2 * use[v] + 1] = vertices[2 * v + 1]; }
  }
  const edges: {along: number[]; at: (k: number) => number}[] = [];
  const onEdge = (test: (c: number, r: number) => boolean, key: (c: number, r: number) => number) => {
    const list: number[] = [];
    for (let v = 0; v < used; v++) if (test(local[2 * v], local[2 * v + 1])) list.push(v);
    list.sort((a, b) => key(local[2 * a], local[2 * a + 1]) - key(local[2 * b], local[2 * b + 1]));
    return list;
  };
  if (ci > 0) edges.push({along: onEdge((_c, r) => r === 0, (c) => c), at: (c) => i0 * cols + j0 + c});
  if (ci < chunkRows - 1) edges.push({along: onEdge((_c, r) => r === CHUNK, (c) => c), at: (c) => (i0 + CHUNK) * cols + j0 + c});
  if (cj > 0) edges.push({along: onEdge((c) => c === 0, (_c, r) => r), at: (r) => (i0 + r) * cols + j0});
  if (cj < chunkCols - 1) edges.push({along: onEdge((c) => c === CHUNK, (_c, r) => r), at: (r) => (i0 + r) * cols + j0 + CHUNK});
  const skirtPairs: [number, number][] = [];
  for (const {along, at} of edges) {
    for (let k = 1; k < along.length; k++) {
      const a = along[k - 1], b = along[k];
      const ka = local[2 * a] === local[2 * b] ? local[2 * a + 1] : local[2 * a];
      const kb = local[2 * a] === local[2 * b] ? local[2 * b + 1] : local[2 * b];
      let whole = true;
      for (let s = ka; s <= kb && whole; s++) whole = !Number.isNaN(heights[at(s)]);
      if (whole) skirtPairs.push([a, b]);
    }
  }
  // Skirt vertices: one below each upper vertex that has a pair
  const below = new Int32Array(used).fill(-1);
  let total = used;
  for (const [a, b] of skirtPairs) {
    if (below[a] < 0) below[a] = total++;
    if (below[b] < 0) below[b] = total++;
  }
  const positions = new Float32Array(total * 3), normals = new Float32Array(total * 3);
  const grid = new Float64Array(total * 2), samples = new Int32Array(total), depth = skirtDepth(maxError);
  for (let v = 0; v < used; v++) {
    const r = i0 + local[2 * v + 1], c = j0 + local[2 * v], k = r * cols + c;
    const x = left + (c + 0.5) * res, y = top - (r + 0.5) * res;
    positions[3 * v] = x - origin.cx; positions[3 * v + 1] = heights[k] - origin.h0; positions[3 * v + 2] = -(y - origin.cy);
    grid[2 * v] = x; grid[2 * v + 1] = y; samples[v] = k;
    normalAt(patch, r, c, normals, 3 * v);
  }
  for (let v = 0; v < used; v++) {
    const w = below[v];
    if (w < 0) continue;
    positions[3 * w] = positions[3 * v]; positions[3 * w + 1] = positions[3 * v + 1] - depth;
    positions[3 * w + 2] = positions[3 * v + 2];
    normals.copyWithin(3 * w, 3 * v, 3 * v + 3);
    grid[2 * w] = grid[2 * v]; grid[2 * w + 1] = grid[2 * v + 1]; samples[w] = samples[v];
  }
  const indices = new Uint32Array(kept.length + skirtPairs.length * 6);
  indices.set(kept);
  let at = kept.length;
  for (const [a, b] of skirtPairs) {
    indices[at++] = a; indices[at++] = b; indices[at++] = below[b];
    indices[at++] = a; indices[at++] = below[b]; indices[at++] = below[a];
  }
  const hasLine = lineSamples.some(([i, j]) => i >= i0 && i <= i0 + CHUNK && j >= j0 && j <= j0 + CHUNK);
  return {ci, cj, positions, normals, grid, samples, indices, surfaceVertices: used, surfaceIndices: kept.length, hasLine};
}

export interface Terrain {
  chunks: ChunkMesh[];
  /** Martini's error the meshes were made with (raised from the asked one until they fit the budget). */
  maxError: number;
  vertices: number;
}

/** Every chunk's mesh within `maxError` metres, the error raised by half until all vertices fit `budget`. */
export function buildTerrain(patch: Patch, origin: Origin, maxError: number, budget: number): Terrain {
  const {all, line} = forcedSamples(patch), [rowsOf, colsOf] = chunkCount(patch);
  const tiles: {ci: number; cj: number; tile: Tile}[] = [];
  for (let ci = 0; ci < rowsOf; ci++) {
    for (let cj = 0; cj < colsOf; cj++) {
      const tile = chunkTile(patch, ci, cj, all, origin.h0);
      if (tile) tiles.push({ci, cj, tile});
    }
  }
  let error = maxError;
  for (let attempt = 0; ; attempt++) {
    const chunks = tiles.map(({ci, cj, tile}) => chunkMesh(patch, origin, ci, cj, tile, error, line))
                        .filter((c) => c.surfaceIndices > 0);
    const vertices = chunks.reduce((sum, c) => sum + c.positions.length / 3, 0);
    if (vertices <= budget || attempt >= 12) return {chunks, maxError: error, vertices};
    error *= 1.5;
  }
}
