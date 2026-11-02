// The terrain's mesh of one chunk of 513 × 513 samples (docs/3d-view-contract.md, "Chunks"): one shared
// Martini(513), no triangles over no data, positions in the scene's axes (geometry.ts). Pure (no three.js),
// so the page and Node tests share it. Skirts and the forced anchor samples come with the scene (wave 2).

import Martini from "./martini";
import { CHUNK, type Patch } from "./decode";
import { sampleXY, toScene, type Origin } from "./geometry";

let shared: Martini | null = null;

/** The one Martini of the page (its triangle table takes a moment and 2 MB). */
export function martini(): Martini {
  return shared || (shared = new Martini(CHUNK + 1));
}

export interface ChunkMesh {
  /** X, Y, Z of each vertex. */
  positions: Float32Array;
  indices: Uint32Array;
}

/** The number of chunks across and down. */
export function chunkCount(patch: Pick<Patch, "cols" | "rows">): [number, number] {
  return [(patch.cols - 1) / CHUNK, (patch.rows - 1) / CHUNK];
}

/** The mesh of chunk (row ci, column cj) within `maxError` metres. */
export function chunkMesh(patch: Patch, origin: Origin, ci: number, cj: number, maxError: number): ChunkMesh {
  const size = CHUNK + 1, i0 = ci * CHUNK, j0 = cj * CHUNK, {heights, cols} = patch;
  const terrain = new Float32Array(size * size);
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const h = heights[(i0 + r) * cols + j0 + c];
      terrain[r * size + c] = Number.isNaN(h) ? origin.h0 : h;  // a stand-in: its triangles are left out
    }
  }
  const {vertices, triangles} = martini().createTile(terrain).getMesh(maxError);
  const n = vertices.length / 2, positions = new Float32Array(n * 3), missing = new Uint8Array(n);
  for (let v = 0; v < n; v++) {
    const c = vertices[2 * v], r = vertices[2 * v + 1], h = heights[(i0 + r) * cols + j0 + c];
    const [x, y] = sampleXY(patch.meta, i0 + r, j0 + c);
    positions.set(toScene(origin, x, y, Number.isNaN(h) ? origin.h0 : h), 3 * v);
    missing[v] = Number.isNaN(h) ? 1 : 0;
  }
  let kept = 0;
  const indices = new Uint32Array(triangles.length);
  for (let t = 0; t < triangles.length; t += 3) {
    const a = triangles[t], b = triangles[t + 1], c = triangles[t + 2];
    if (missing[a] || missing[b] || missing[c]) continue;
    indices[kept++] = a; indices[kept++] = b; indices[kept++] = c;
  }
  return {positions, indices: indices.slice(0, kept)};
}
