// The reach of an anchor (docs/3d-view-contract.md, "Round 2", point 3 and `GET /api/reach`): where the other
// anchor may stand so that the line between them fits. Pure but for `fetchReach`'s default request (download.ts),
// so Node tests (tests/test_view3d_reach.py) share it with the page: the request's address, an answer split,
// checked and decoded, a sample's class and clearance at grid metres, the nearest valid sample of a point (the
// snap of a dragged anchor), the mask as the RGBA picture of the overlay, and the lane that sends the reach
// requests one at a time and never beside a profile request (the public site allows one waiting quick task a user).

import { download } from "../download";
import { detailMessage, t } from "../i18n";
import { inflate, splitAnswer } from "./decode";
import type { PageRequest } from "./page";

/** The header /api/reach asks for (web.py `/api/reach`). */
export const REACH_HEADER = "X-Findaline-Reach";

/** Which anchor stays: 1 or 2, the query's `as`. */
export type End = 1 | 2;

/** The meta of an answer (the contract's `/api/reach`): value (i, j) belongs to the patch's sample (i·lattice,
 *  j·lattice), whose centre is at left + (j·lattice + 0.5)·res, top − (i·lattice + 0.5)·res. */
export interface ReachMeta {
  width: number;
  height: number;
  lattice: number;
  res: number;
  left: number;
  top: number;
  anchor: {x: number; y: number; h: number};
  as: End;
  min_length: number;
  max_length: number;
  valid: number;
  trees: number;
  /** Metres one step of a value's low 7 bits stands for. */
  quantum: number;
  sha256: string;
}

export interface Reach {
  meta: ReachMeta;
  /** One byte a lattice sample, row-major from the top: 0 not valid; else the low 7 bits are
   *  min(127, ceil(clearance / quantum)) (at least 1) and the high bit is set when the line passes over trees
   *  or buildings. */
  mask: Uint8Array;
}

/** An answer that does not hold together (a damaged or unexpected body). */
export class ReachError extends Error {}

/** /api/reach's address: the page's run and line as /api/patch took them (`step` as the patch's), the fixed
 *  point `lonLat` ([lon, lat], 7 decimals) and which end of the line it is. */
export function reachUrl(page: Pick<PageRequest, "run" | "line" | "level">, lonLat: [number, number], end: End,
                         step: 1 | 2 = page.level === "phone" ? 2 : 1): string {
  return `/api/reach?run=${encodeURIComponent(page.run)}&line=${encodeURIComponent(page.line || "")}` +
         `&step=${step}&anchor=${lonLat[1].toFixed(7)},${lonLat[0].toFixed(7)}&as=${end}`;
}

async function sha256Hex(body: Uint8Array): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;  // not a secure context: left unchecked, as the patch's
  const digest = await crypto.subtle.digest("SHA-256", body as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function finite(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** The meta of an answer, checked: the numbers the page relies on are there. */
export function checkedMeta(meta: Partial<ReachMeta>): ReachMeta {
  const sizes = [meta.width, meta.height, meta.lattice];
  if (!sizes.every((v) => finite(v) && Number.isInteger(v) && v >= 1)) throw new ReachError(t("error.patch_damaged"));
  if (![meta.res, meta.left, meta.top, meta.quantum].every(finite) || !(meta.res! > 0) || !(meta.quantum! > 0)) {
    throw new ReachError(t("error.patch_damaged"));
  }
  if (meta.as !== 1 && meta.as !== 2) throw new ReachError(t("error.patch_damaged"));
  return meta as ReachMeta;
}

/** Decode a whole answer of /api/reach (`uint32 LE N`, N bytes of JSON meta, the deflated values): the sha256
 *  of the deflated values is checked (where the browser has crypto), the values must fill the lattice. */
export async function decodeReach(answer: ArrayBuffer): Promise<Reach> {
  let split;
  try { split = splitAnswer(answer); } catch (e) { throw new ReachError((e as Error).message); }
  const meta = checkedMeta(split.meta as unknown as Partial<ReachMeta>);
  const sha = await sha256Hex(split.body);
  if (sha !== null && sha !== meta.sha256) throw new ReachError(t("error.patch_damaged"));
  const mask = await inflate(split.body);
  if (mask.byteLength !== meta.width * meta.height) throw new ReachError(t("error.patch_damaged"));
  return {meta, mask};
}

/** One GET of the reach (default: download.ts' XMLHttpRequest, like the patch's). */
export type ReachGet = (url: string, headers: Record<string, string>) =>
    Promise<{status: number; body: ArrayBuffer}>;

const xhrGet: ReachGet = (url, headers) => download(url, "arraybuffer", {headers});

/** Ask /api/reach for `url`: the decoded answer; a refusal or a failure rejects with the server's message. */
export async function fetchReach(url: string, get: ReachGet = xhrGet): Promise<Reach> {
  const answer = await get(url, {[REACH_HEADER]: "1"});
  if (answer.status !== 200) {
    let data: {detail?: unknown} = {};
    try { data = JSON.parse(new TextDecoder().decode(answer.body)); } catch { /* not JSON */ }
    throw new ReachError(detailMessage(data.detail, String(answer.status)));
  }
  return decodeReach(answer.body);
}

/** A sample's class: not valid, the line fits over the terrain, or fits over trees or buildings only. */
export type Kind = 0 | 1 | 2;

/** The class of a mask byte. */
export function kindOf(value: number): Kind {
  return value === 0 ? 0 : value & 0x80 ? 2 : 1;
}

/** The size in metres of a lattice cell. */
export function cellOf(meta: Pick<ReachMeta, "lattice" | "res">): number {
  return meta.lattice * meta.res;
}

/** The lattice indices (row i, column j) whose cell holds the grid point (x, y), null outside the lattice. A cell
 *  is centred on its sample and is `lattice` samples wide. */
export function cellAt(meta: ReachMeta, x: number, y: number): [number, number] | null {
  const cell = cellOf(meta);
  const j = Math.floor((x - (meta.left + (0.5 - meta.lattice / 2) * meta.res)) / cell);
  const i = Math.floor(((meta.top - (0.5 - meta.lattice / 2) * meta.res) - y) / cell);
  return i >= 0 && j >= 0 && i < meta.height && j < meta.width ? [i, j] : null;
}

/** The mask byte at grid metres (0 outside the lattice). */
export function byteAt(reach: Reach, x: number, y: number): number {
  const at = cellAt(reach.meta, x, y);
  return at ? reach.mask[at[0] * reach.meta.width + at[1]] : 0;
}

/** The class of the point's sample. */
export function kindAt(reach: Reach, x: number, y: number): Kind {
  return kindOf(byteAt(reach, x, y));
}

/** The clearance in metres of a valid sample, an upper bound within one quantum (127 steps cap it); null where
 *  the line is not valid. */
export function clearanceAt(reach: Reach, x: number, y: number): number | null {
  const b = byteAt(reach, x, y);
  return b === 0 ? null : (b & 0x7f) * reach.meta.quantum;
}

export interface ValidSample {
  /** The sample's centre in grid metres. */
  x: number;
  y: number;
  i: number;
  j: number;
  kind: 1 | 2;
  clearance: number;
  /** From the asked point to the centre, metres. */
  distance: number;
}

/** The nearest valid sample whose centre lies within `radius` metres of (x, y); null when there is none. Ties go
 *  to the smaller row, then column. */
export function nearestValid(reach: Reach, x: number, y: number, radius: number): ValidSample | null {
  const {meta, mask} = reach, cell = cellOf(meta);
  const u = (x - (meta.left + 0.5 * meta.res)) / cell, v = ((meta.top - 0.5 * meta.res) - y) / cell, r = radius / cell;
  const j0 = Math.max(0, Math.ceil(u - r)), j1 = Math.min(meta.width - 1, Math.floor(u + r));
  const i0 = Math.max(0, Math.ceil(v - r)), i1 = Math.min(meta.height - 1, Math.floor(v + r));
  let best: ValidSample | null = null, bestD = radius * radius;
  for (let i = i0; i <= i1; i++) {
    const cy = meta.top - (i * meta.lattice + 0.5) * meta.res, dy = cy - y;
    for (let j = j0; j <= j1; j++) {
      const b = mask[i * meta.width + j];
      if (b === 0) continue;
      const cx = meta.left + (j * meta.lattice + 0.5) * meta.res, dx = cx - x, d = dx * dx + dy * dy;
      if (d > radius * radius || (best && d >= bestD)) continue;
      bestD = d;
      best = {x: cx, y: cy, i, j, kind: kindOf(b) as 1 | 2, clearance: (b & 0x7f) * meta.quantum, distance: Math.sqrt(d)};
    }
  }
  return best;
}

/** The farthest a dragged anchor looks for a valid sample around the pointer's hit (metres). */
export const SNAP_MAX_M = 80;
/** How far, in screen pixels, a dragged anchor looks around the pointer. */
export const SNAP_PX = 28;

/** The radius of the snap around the pointer's hit: SNAP_PX pixels at the hit's `distance` from the camera (vertical
 *  field of view `fov` degrees, `viewportPx` pixels high), at least one and a half lattice cells (a drag always
 *  finds the cell it is in) and at most SNAP_MAX_M. */
export function snapRadius(distance: number, fov: number, viewportPx: number, cell: number): number {
  const perPixel = 2 * distance * Math.tan(fov * Math.PI / 360) / Math.max(1, viewportPx);
  return Math.min(SNAP_MAX_M, Math.max(1.5 * cell, SNAP_PX * perPixel));
}

export type Rgb = [number, number, number];

/** The mask as the overlay's picture. */
export interface Picture {
  /** RGBA, row-major from the top (WebGL's texture rows with flipY off). */
  rgba: Uint8Array;
  width: number;
  height: number;
  /** The picture's west edge and north edge in grid metres, and the metres one pixel spans. */
  left: number;
  top: number;
  cell: number;
}

/** Alpha of the overlay's colours (about 45 %). */
export const OVERLAY_ALPHA = 115;

/** The picture of a reach: a pixel a lattice sample, `fits` where the line fits over the terrain and `trees` where
 *  it passes over trees or buildings, at `OVERLAY_ALPHA`; transparent (with the fitting colour, so that mipmaps do
 *  not darken the edges) where it is not valid. Cropped to the valid samples with a transparent pixel around;
 *  null without a valid sample. */
export function reachPicture(reach: Reach, fits: Rgb, trees: Rgb, alpha = OVERLAY_ALPHA): Picture | null {
  const {meta, mask} = reach, {width, height} = meta;
  let i0 = height, i1 = -1, j0 = width, j1 = -1;
  for (let i = 0; i < height; i++) {
    for (let j = 0; j < width; j++) {
      if (mask[i * width + j] === 0) continue;
      if (i < i0) i0 = i;
      if (i > i1) i1 = i;
      if (j < j0) j0 = j;
      if (j > j1) j1 = j;
    }
  }
  if (i1 < 0) return null;
  const w = j1 - j0 + 3, h = i1 - i0 + 3, rgba = new Uint8Array(w * h * 4), cell = cellOf(meta);
  for (let p = 0; p < w * h; p++) rgba.set([fits[0], fits[1], fits[2], 0], 4 * p);
  for (let i = i0; i <= i1; i++) {
    for (let j = j0; j <= j1; j++) {
      const b = mask[i * width + j];
      if (b === 0) continue;
      const colour = kindOf(b) === 2 ? trees : fits, at = 4 * ((i - i0 + 1) * w + (j - j0 + 1));
      rgba[at] = colour[0]; rgba[at + 1] = colour[1]; rgba[at + 2] = colour[2]; rgba[at + 3] = alpha;
    }
  }
  const edge = (0.5 - meta.lattice / 2) * meta.res;  // a cell's west (north) edge from its sample's centre line
  return {rgba, width: w, height: h, cell,
          left: meta.left + (j0 - 1) * cell + edge, top: meta.top - (i0 - 1) * cell - edge};
}

/** Grid metres to the picture's (u, v): u from the west edge, v down from the north edge (the texture's rows as
 *  `rgba` has them, flipY off). */
export function pictureUv(p: Picture): (x: number, y: number) => [number, number] {
  return (x, y) => [(x - p.left) / (p.width * p.cell), (p.top - y) / (p.height * p.cell)];
}

export type Slot = 0 | 1;
/** The lane serves the reaches of the two anchors (`Slot`) and, as a third, the reach of a point picked by the
 *  tool "Lines from a point" (point.ts). */
export const POINT_SLOT = 2;
export type LaneSlot = Slot | typeof POINT_SLOT;

/** What the lane reports. */
export interface LaneHandlers {
  /** The reach of anchor `slot` (the answer of a request still wanted). */
  got(slot: LaneSlot, reach: Reach): void;
  /** The request for `slot` failed. */
  failed(slot: LaneSlot, error: unknown): void;
  /** A request is in flight (true) or the lane is idle (false). */
  busy(on: boolean): void;
}

/** The reach requests: one at a time, never while a profile request is in flight or waiting (the lane's profile
 *  side: `hold` and `guard`), only while `on`. `want(slot)` asks for the reach of anchor `slot` anew (an answer
 *  to an earlier ask of that slot is ignored); `drop(slot)` forgets the ask and any answer on its way. The slot
 *  `first` names goes first when several are wanted (then the others in the order of their numbers). */
export interface Lane {
  on: boolean;
  want(slot: LaneSlot): void;
  drop(slot: LaneSlot): void;
  /** Drop everything wanted and ignore the answer in flight (the switch went off). */
  stop(): void;
  /** A profile request is waiting to be sent (its debounce) or not: while it is, no reach request starts. */
  hold(on: boolean): void;
  /** Run a profile request through the lane: it waits for a reach request in flight to end, and while it runs no
   *  reach request starts. */
  guard<T>(fetch: () => Promise<T>): Promise<T>;
  /** A request is in flight. */
  readonly running: boolean;
  /** Requests sent so far, in order, as the `want`s that were served (for tests). */
  readonly log: readonly LaneSlot[];
}

const SLOTS: readonly LaneSlot[] = [0, 1, POINT_SLOT];

export function reachLane(send: (slot: LaneSlot) => Promise<Reach>, handlers: LaneHandlers,
                          first: () => LaneSlot = () => 0): Lane {
  const wanted = [false, false, false], epoch = [0, 0, 0];
  let held = false, profiles = 0, on = false, current: {slot: LaneSlot; epoch: number} | null = null;
  const log: LaneSlot[] = [], idle: (() => void)[] = [];
  const kick = () => {
    if (!on || current || held || profiles > 0) return;
    const a = first(), slot = [a, ...SLOTS.filter((s) => s !== a)].find((s) => wanted[s]);
    if (slot === undefined) return;
    wanted[slot] = false;
    const mine = current = {slot, epoch: epoch[slot]};
    log.push(slot);
    handlers.busy(true);
    const finish = (then: () => void) => {
      current = null;
      if (on && mine.epoch === epoch[slot]) then();
      handlers.busy(false);
      for (const fn of idle.splice(0)) fn();
      kick();
    };
    send(slot).then((reach) => finish(() => handlers.got(slot, reach)),
                    (error) => finish(() => handlers.failed(slot, error)));
  };
  return {
    get on() { return on; },
    set on(value: boolean) { on = value; if (on) kick(); },
    want(slot) { epoch[slot]++; wanted[slot] = true; kick(); },
    drop(slot) { epoch[slot]++; wanted[slot] = false; },
    stop() { on = false; for (const s of SLOTS) { epoch[s]++; wanted[s] = false; } },
    hold(value) { held = value; if (!value) kick(); },
    guard<T>(fetch: () => Promise<T>): Promise<T> {
      profiles++;
      const run = async () => {
        while (current) await new Promise<void>((resolve) => idle.push(resolve));
        return fetch();
      };
      return run().finally(() => { profiles--; kick(); });
    },
    get running() { return current !== null; },
    get log() { return log; },
  };
}
