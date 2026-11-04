// The uncertain shore in the 3D view (docs/3d-view-contract.md, "Body"): the patch's kinds (0 none, 1 the face
// from the surface model, 2 the sea fill standing in for a cliff's foot: search.encode_shore) hatched on the
// chunks' textures (imagery.ts), and a detector of the same thing from the heights alone (the walls a person
// sees as streaks straight down to the water: a sample of the sea fill next to one standing WALL_DROP higher),
// to compare with the data's kinds. Pure, tested in Node (tests/test_viewer.py).

import { SHORE_COLOURS } from "../shore";
import type { PatchMeta } from "./decode";
import { worldPixel, type TexturePlan } from "./tiles";

export const SHORE_SURFACE = 1, SHORE_SEA = 2;
/** A wall at least this high between a sample at the water's level and its neighbour counts as a cliff's foot
 *  the fill stands in for (the detector's threshold; the data's is sources.filling.SHORE_RIM_MIN). */
export const WALL_DROP = 10;
/** The sea fill's height. */
const SEA = 0;

/** The samples of the shore of a patch as texture rectangles of a chunk's plan: for each sample of a kind within
 *  the plan's canvas, its footprint in canvas pixels [x, y, w, h] and its kind. `step`: the patch's. */
export function shoreCells(kinds: Uint8Array, meta: Pick<PatchMeta, "width" | "height" | "left" | "top" | "res" | "affine">,
                           plan: TexturePlan, bounds: {x0: number; y0: number; x1: number; y1: number}):
    {x: number; y: number; w: number; h: number; kind: number}[] {
  const cells: {x: number; y: number; w: number; h: number; kind: number}[] = [];
  const {res} = meta;
  const j0 = Math.max(0, Math.floor((bounds.x0 - meta.left) / res)), j1 = Math.min(meta.width, Math.ceil((bounds.x1 - meta.left) / res));
  const i0 = Math.max(0, Math.floor((meta.top - bounds.y1) / res)), i1 = Math.min(meta.height, Math.ceil((meta.top - bounds.y0) / res));
  for (let i = i0; i < i1; i++) {
    for (let j = j0; j < j1; j++) {
      const kind = kinds[i * meta.width + j];
      if (!kind) continue;
      const x = meta.left + j * res, y = meta.top - i * res;  // the sample's footprint: its top left corner
      const [px0, py0] = worldPixel(meta.affine, x, y, plan.z), [px1, py1] = worldPixel(meta.affine, x + res, y - res, plan.z);
      const left = Math.min(px0, px1) - plan.px0, top = Math.min(py0, py1) - plan.py0;
      cells.push({x: left, y: top, w: Math.max(1, Math.abs(px1 - px0)), h: Math.max(1, Math.abs(py1 - py0)), kind});
    }
  }
  return cells;
}

/** The hatching: diagonal strokes of the kind's colour over a translucent fill, as a canvas pattern. */
export function hatchPattern(ctx: CanvasRenderingContext2D, kind: number): CanvasPattern | string {
  const colour = kind === SHORE_SEA ? SHORE_COLOURS.sea : SHORE_COLOURS.surface;
  const tile = document.createElement("canvas");
  tile.width = tile.height = 8;
  const c = tile.getContext("2d");
  if (!c) return colour;
  c.fillStyle = colour;
  c.globalAlpha = 0.25;
  c.fillRect(0, 0, 8, 8);
  c.globalAlpha = 0.9;
  c.strokeStyle = colour;
  c.lineWidth = 1.5;
  c.beginPath();
  c.moveTo(-2, 10); c.lineTo(10, -2);
  c.moveTo(-2, 2); c.lineTo(2, -2);
  c.moveTo(6, 10); c.lineTo(10, 6);
  c.stroke();
  return ctx.createPattern(tile, "repeat") ?? colour;
}

/** Draw the shore's cells of a chunk on its canvas (after the imagery). Returns how many were drawn. */
export function drawShore(ctx: CanvasRenderingContext2D, kinds: Uint8Array,
                          meta: Pick<PatchMeta, "width" | "height" | "left" | "top" | "res" | "affine">,
                          plan: TexturePlan, bounds: {x0: number; y0: number; x1: number; y1: number}): number {
  const cells = shoreCells(kinds, meta, plan, bounds);
  if (!cells.length) return 0;
  const patterns = new Map<number, CanvasPattern | string>();
  for (const cell of cells) {
    if (!patterns.has(cell.kind)) patterns.set(cell.kind, hatchPattern(ctx, cell.kind));
    ctx.fillStyle = patterns.get(cell.kind)!;
    ctx.fillRect(cell.x, cell.y, cell.w, cell.h);
  }
  return cells.length;
}

/** Whether any sample of the shore lies within bounds (grid metres). */
export function shoreWithin(kinds: Uint8Array, meta: Pick<PatchMeta, "width" | "height" | "left" | "top" | "res">,
                            bounds: {x0: number; y0: number; x1: number; y1: number}): boolean {
  const {res} = meta;
  const j0 = Math.max(0, Math.floor((bounds.x0 - meta.left) / res)), j1 = Math.min(meta.width, Math.ceil((bounds.x1 - meta.left) / res));
  const i0 = Math.max(0, Math.floor((meta.top - bounds.y1) / res)), i1 = Math.min(meta.height, Math.ceil((meta.top - bounds.y0) / res));
  for (let i = i0; i < i1; i++) for (let j = j0; j < j1; j++) if (kinds[i * meta.width + j]) return true;
  return false;
}

/** The detector from the heights alone: a sample at the sea's level (the fill) with a neighbour (8) at least
 *  `drop` higher is marked SHORE_SEA. `heights`: width × height row-major (NaN: no data). Used to compare with
 *  the data's kinds, which know the faces from the surface model too. */
export function detectWalls(heights: ArrayLike<number>, width: number, height: number, drop = WALL_DROP): Uint8Array {
  const out = new Uint8Array(width * height);
  for (let i = 0; i < height; i++) {
    for (let j = 0; j < width; j++) {
      const h = heights[i * width + j];
      if (h !== SEA) continue;
      let highest = -Infinity;
      for (let di = -1; di <= 1; di++) {
        for (let dj = -1; dj <= 1; dj++) {
          if (!di && !dj) continue;
          const ii = i + di, jj = j + dj;
          if (ii < 0 || jj < 0 || ii >= height || jj >= width) continue;
          const n = heights[ii * width + jj];
          if (n === n && n > highest) highest = n;
        }
      }
      if (highest - h >= drop) out[i * width + j] = SHORE_SEA;
    }
  }
  return out;
}

/** How the detector's marks and the data's kinds agree: the samples of each, and of both. */
export function agreement(detected: Uint8Array, kinds: Uint8Array): {detected: number; data: number; both: number} {
  let d = 0, k = 0, both = 0;
  for (let n = 0; n < kinds.length; n++) {
    const a = detected[n] > 0, b = kinds[n] > 0;
    if (a) d++;
    if (b) k++;
    if (a && b) both++;
  }
  return {detected: d, data: k, both};
}
