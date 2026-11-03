// The geometry of the 3D view, pure (tested in Node: tests/test_viewer.py): the scene's axes, the webbing
// between the anchors from sag.ts, the walker's start and the walk's stepping, grid metres to lon/lat and
// Web Mercator (docs/3d-view-contract.md, "Geometry in the page").

import { estimate, type Estimate } from "../sag";
import type { Rigging } from "../types";
import type { Anchor3d, PatchMeta } from "./decode";

/** The scene's origin: the patch centre (cx, cy) in grid metres and the height h0 = base_dm / 10. */
export interface Origin { cx: number; cy: number; h0: number }

export function originOf(meta: Pick<PatchMeta, "left" | "top" | "width" | "height" | "res" | "base_dm">): Origin {
  return {cx: meta.left + meta.width * meta.res / 2, cy: meta.top - meta.height * meta.res / 2, h0: meta.base_dm / 10};
}

/** Grid metres and a height to the scene: X east, Y up, Z south. */
export function toScene(o: Origin, x: number, y: number, h: number): [number, number, number] {
  return [x - o.cx, h - o.h0, -(y - o.cy)];
}

/** The centre of sample (row i, column j) in grid metres. */
export function sampleXY(meta: Pick<PatchMeta, "left" | "top" | "res">, i: number, j: number): [number, number] {
  return [meta.left + (j + 0.5) * meta.res, meta.top - (i + 0.5) * meta.res];
}

/** A point of the webbing in grid metres and its height. */
export type Point3d = [number, number, number];

export interface Webbing {
  span: number;
  /** h1 − h2: the drop from anchor 1 to anchor 2. */
  dh: number;
  estimate: Estimate;
  /** The webbing without the walker, from anchor 1 to anchor 2. */
  unloaded: Point3d[];
  /** The walker's start: the distance along the span of the envelope's largest sag, and that sag. */
  start: {s: number; sag: number};
}

/** A point at distance `s` along the span with the drop `d` below anchor 1. */
export function along(a: Anchor3d, b: Anchor3d, span: number, s: number, d: number): Point3d {
  const t = span > 0 ? s / span : 0;
  return [a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.h - d];
}

/** The webbing of a line from its anchors and the run's rigging; null when the sag solver fails. */
export function webbing(anchors: [Anchor3d, Anchor3d], rigging: Rigging): Webbing | null {
  const [a, b] = anchors, span = Math.hypot(b.x - a.x, b.y - a.y), dh = a.h - b.h;
  if (!(span > 0)) return null;
  const e = estimate(span, dh, rigging);
  if (!e) return null;
  let k = 0;
  for (let i = 1; i < e.sag.length; i++) if (e.sag[i] > e.sag[k]) k = i;
  return {span, dh, estimate: e, unloaded: e.unloaded.map(([s, d]) => along(a, b, span, s, d)),
          start: {s: e.f[k] * span, sag: e.sag[k]}};
}

/** The webbing with the walker at distance `s` along the span (sag.ts athlete); null when it fails. */
export function loadedAt(w: Webbing, anchors: [Anchor3d, Anchor3d], s: number):
    {points: Point3d[]; walker: Point3d; sag: number} | null {
  const [a, b] = anchors, x = Math.min(w.span, Math.max(0, s)), loaded = w.estimate.athlete(x);
  if (!loaded) return null;
  const chord = w.dh / w.span * x;  // the chord's drop below anchor 1 at x
  return {points: loaded.curve.map(([u, d]) => along(a, b, w.span, u, d)),
          walker: along(a, b, w.span, x, chord + loaded.sag), sag: loaded.sag};
}

/** The walk: 1 m/s times its speed. */
export const WALK_SPEED = 1;
export const SPEEDS = [1, 4] as const;

/** The walker's position after `dt` seconds of walking towards anchor 2 (`dir` 1) or anchor 1 (−1); it stops
 *  at the anchors (`done`). Under reduced motion it does not move (the page offers the slider only). */
export function walkStep(s: number, dt: number, span: number, speed: number, dir: 1 | -1, reduced: boolean):
    {s: number; done: boolean} {
  if (reduced) return {s, done: true};
  const next = s + dir * WALK_SPEED * speed * Math.max(0, dt);
  if (next >= span) return {s: span, done: true};
  if (next <= 0) return {s: 0, done: true};
  return {s: next, done: false};
}

/** Grid metres to [lon, lat] with the meta's affine. */
export function lonLat(affine: PatchMeta["affine"], x: number, y: number): [number, number] {
  const [a0, a1, a2, b0, b1, b2] = affine;
  return [a0 + a1 * x + a2 * y, b0 + b1 * x + b2 * y];
}

const R = 6378137;

/** [lon, lat] to Web Mercator metres (EPSG:3857), for texture UVs. */
export function mercator(lon: number, lat: number): [number, number] {
  const phi = Math.max(-85.0511287798, Math.min(85.0511287798, lat)) * Math.PI / 180;
  return [R * lon * Math.PI / 180, R * Math.log(Math.tan(Math.PI / 4 + phi / 2))];
}
