// The answer of /api/patch (docs/3d-view-contract.md, "/api/patch" and "Body"): `uint32 LE N`, N bytes of
// JSON meta, the deflated heights. The heights are int16 decimetres above `base_dm` (-32768: no data),
// row-major from the top, each row as horizontal deltas with int16 wrapping, in zlib's format.
// The steps are separate so tests can feed inflated bytes (tests/data/make_patch_fixture.py is the reference).

import type { Rigging } from "../types";

export const NO_DATA = -32768;
/** Martini's tile: chunks of CHUNK + 1 samples share their edge rows and columns. */
export const CHUNK = 512;

export interface Anchor3d { x: number; y: number; h: number }

export interface PatchMeta {
  width: number;
  height: number;
  step: 1 | 2;
  /** Metres between samples. */
  res: number;
  crs: string;
  /** Outer edges of the grid: sample (i, j) has its centre at (left + (j + .5)·res, top − (i + .5)·res). */
  left: number;
  top: number;
  base_dm: number;
  anchors: [Anchor3d, Anchor3d];
  /** lon = a0 + a1·x + a2·y, lat = b0 + b1·x + b2·y (grid metres). */
  affine: [number, number, number, number, number, number];
  rigging: Rigging;
  model: string;
  /** The run's formula-model constants as data.js has them (search.patch_of_line): the profile chart's limit. */
  slope: number;
  leash_fall: number;
  /** The run's no-fall zone at the ends and its A-frame height, metres (search.patch_of_line, only when set): the
   *  webbing starts `lift` above the anchors' heights (line.ts), the profile card's chart draws both. */
  end_zone?: number;
  lift?: number;
  /** The run has a surface model: the block of trees and buildings can be asked (canopy.ts). */
  surface?: boolean;
  /** The run's grouping distance in metres (options.ts: the lines from a point as the result's spots). */
  group_distance?: number;
  ortho: unknown;
  attribution: unknown;
  sha256: string;
  /** The deflated kinds of the uncertain shore after the heights (search.encode_shore), when the run fills the
   *  water: their length and sha256. */
  shore_bytes?: number;
  shore_sha256?: string;
}

export interface Patch {
  meta: PatchMeta;
  /** The decoded values, meta.width × meta.height (decimetres above base_dm, NO_DATA for no data). */
  values: Int16Array;
  /** The kinds of the uncertain shore, meta.width × meta.height (0 none, 1 the face from the surface model, 2 the
   *  sea fill standing in for a cliff's foot: view3d/shore.ts); absent without any. */
  shore?: Uint8Array;
  /** Heights in metres padded with NaN to cols × rows (each 512·k + 1), row-major from the top. */
  heights: Float32Array;
  cols: number;
  rows: number;
}

/** The meta and the deflated body of an answer. */
export function splitAnswer(answer: ArrayBuffer): {meta: PatchMeta; body: Uint8Array} {
  if (answer.byteLength < 4) throw new Error("The answer is too short.");
  const n = new DataView(answer).getUint32(0, true);
  if (4 + n > answer.byteLength) throw new Error("The answer's meta is cut short.");
  const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(answer, 4, n))) as PatchMeta;
  return {meta, body: new Uint8Array(answer, 4 + n)};
}

/** Inflate a zlib (RFC 1950) body with the browser's DecompressionStream("deflate"). */
export async function inflate(body: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([body as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** The int16 values of inflated bytes: the deltas of each row summed with int16 wrapping. */
export function decodeValues(raw: Uint8Array, width: number, height: number): Int16Array {
  if (raw.byteLength !== width * height * 2) {
    throw new Error(`Expected ${width * height * 2} bytes of heights, got ${raw.byteLength}.`);
  }
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength), values = new Int16Array(width * height);
  for (let i = 0, k = 0; i < height; i++) {
    let acc = 0;
    for (let j = 0; j < width; j++, k++) {
      acc = ((acc + view.getInt16(2 * k, true)) << 16) >> 16;
      values[k] = acc;
    }
  }
  return values;
}

/** The smallest 512·k + 1 (k ≥ 1) holding n samples. */
export function paddedSize(n: number): number {
  return CHUNK * Math.max(1, Math.ceil((n - 1) / CHUNK)) + 1;
}

/** Heights in metres (NaN for no data), padded on the right and at the bottom to 512·k + 1 each way. */
export function toHeights(values: Int16Array, width: number, height: number, baseDm: number):
    {heights: Float32Array; cols: number; rows: number} {
  const cols = paddedSize(width), rows = paddedSize(height), heights = new Float32Array(cols * rows).fill(NaN);
  for (let i = 0; i < height; i++) {
    for (let j = 0; j < width; j++) {
      const v = values[i * width + j];
      if (v !== NO_DATA) heights[i * cols + j] = (v + baseDm) / 10;
    }
  }
  return {heights, cols, rows};
}

/** Decode a whole answer of /api/patch: the heights, then the shore's kinds when the meta names their bytes. */
export async function decodePatch(answer: ArrayBuffer): Promise<Patch> {
  const {meta, body} = splitAnswer(answer);
  const n = meta.shore_bytes ?? 0;
  if (n < 0 || n > body.byteLength) throw new Error("The answer's shore block is cut short.");
  const values = decodeValues(await inflate(n ? body.subarray(0, body.byteLength - n) : body), meta.width, meta.height);
  const patch: Patch = {meta, values, ...toHeights(values, meta.width, meta.height, meta.base_dm)};
  if (n) {
    const kinds = await inflate(body.subarray(body.byteLength - n));
    if (kinds.byteLength !== meta.width * meta.height) {
      throw new Error(`Expected ${meta.width * meta.height} bytes of the shore, got ${kinds.byteLength}.`);
    }
    if (kinds.some((k) => k !== 0)) patch.shore = kinds;
  }
  return patch;
}
