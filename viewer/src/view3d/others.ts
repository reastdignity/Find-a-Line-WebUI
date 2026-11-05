// The other lines of the 3D view, pure (tested in Node: tests/test_view3d_others.py; docs/3d-view-contract.md,
// "Round 2", point 7): where a line given by its key ("lat1,lon1,lat2,lon2", the 2D result's) stands in the patch
// (the inverse of the meta's affine, the heights from the patch), which of the candidate lines are drawn (inside the
// patch over terrain data, not the active one, at most OTHERS_MAX: the lines asked for first, then the user's
// favourites nearest the active line's middle) and the point of a line its label stands at. The scene's part is
// otherlines.ts.

import type { Anchor3d, PatchMeta } from "./decode";
import { unloadedAt } from "./webbing";
import { OTHERS_MAX, canonicalKey } from "./page";
import type { Webbing } from "./geometry";

export { OTHERS_MAX };

/** The part of the patch's meta that places a line: the affine, the grid's outer edges and its sample size. */
export type Frame = Pick<PatchMeta, "affine" | "left" | "top" | "res" | "width" | "height">;

/** A line's key as numbers [lat1, lon1, lat2, lon2]; null when it is not four finite numbers. */
export function keyCoords(key: string): [number, number, number, number] | null {
  const n = key.split(",");
  if (n.length !== 4 || n.some((v) => v.trim() === "")) return null;
  const v = n.map(Number);
  return v.every(isFinite) ? [v[0], v[1], v[2], v[3]] : null;
}

/** [lon, lat] to grid metres: the inverse of the meta's affine (geometry.ts `lonLat`, lon = a0 + a1·x + a2·y,
 *  lat = b0 + b1·x + b2·y); null when the affine is singular. */
export function gridOf(affine: PatchMeta["affine"], lon: number, lat: number): [number, number] | null {
  const [a0, a1, a2, b0, b1, b2] = affine, det = a1 * b2 - a2 * b1;
  if (!det || !isFinite(det)) return null;
  const u = lon - a0, v = lat - b0;
  return [(b2 * u - a2 * v) / det, (a1 * v - b1 * u) / det];
}

/** The point lies in the patch's grid (its outer edges). */
export function inPatch(frame: Pick<Frame, "left" | "top" | "res" | "width" | "height">, x: number, y: number): boolean {
  return x >= frame.left && x <= frame.left + frame.width * frame.res &&
         y <= frame.top && y >= frame.top - frame.height * frame.res;
}

/** Where a candidate comes from: `kept` a line that was the active one, `address` the lines of `&also=`, `favourite` the
 *  user's favourites of the run. */
export type Source = "kept" | "address" | "favourite";

export interface Candidate { key: string; source: Source }

/** A line to draw: its key (canonical), where it comes from and its anchors in grid metres with their heights. */
export interface Placed { key: string; source: Source; anchors: [Anchor3d, Anchor3d] }

/** The anchors of a line's key in the patch: grid metres by the inverse affine, the height from the patch at each;
 *  null when an end lies outside the patch or over no data, or the key is not a line. */
export function placeLine(frame: Frame, key: string, heightAt: (x: number, y: number) => number | null):
    [Anchor3d, Anchor3d] | null {
  const c = keyCoords(key);
  if (!c) return null;
  const out: Anchor3d[] = [];
  for (const [lat, lon] of [[c[0], c[1]], [c[2], c[3]]]) {
    const g = gridOf(frame.affine, lon, lat);
    if (!g || !inPatch(frame, g[0], g[1])) return null;
    const h = heightAt(g[0], g[1]);
    if (h === null || !isFinite(h)) return null;
    out.push({x: g[0], y: g[1], h});
  }
  return [out[0], out[1]];
}

export interface ChooseOptions {
  frame: Frame;
  heightAt(x: number, y: number): number | null;
  /** Keys that are not drawn: the active line's (canonical or not). */
  exclude: Iterable<string>;
  /** The active line's middle in grid metres: the favourites nearest to it come first. */
  middle: {x: number; y: number};
  max?: number;
}

/** The lines to draw among `candidates`: those placed in the patch over terrain data, not excluded, a key once (the
 *  first candidate's source counts); the lines of `kept` and `address` first in the order given, then the favourites
 *  nearest `middle` (ties in the order given); at most `max` (OTHERS_MAX). */
export function chooseOthers(candidates: readonly Candidate[], o: ChooseOptions): Placed[] {
  const skip = new Set([...o.exclude].map(canonicalKey)), seen = new Set<string>();
  const asked: Placed[] = [], favourites: {placed: Placed; d: number}[] = [];
  for (const c of candidates) {
    const key = canonicalKey(c.key);
    if (skip.has(key) || seen.has(key)) continue;
    const anchors = placeLine(o.frame, key, o.heightAt);
    if (!anchors) continue;
    seen.add(key);
    const placed = {key, source: c.source, anchors};
    if (c.source !== "favourite") { asked.push(placed); continue; }
    const mx = (anchors[0].x + anchors[1].x) / 2 - o.middle.x, my = (anchors[0].y + anchors[1].y) / 2 - o.middle.y;
    favourites.push({placed, d: mx * mx + my * my});
  }
  favourites.sort((a, b) => a.d - b.d);  // a stable sort: ties keep the order given
  return asked.concat(favourites.map((f) => f.placed)).slice(0, o.max ?? OTHERS_MAX);
}

/** The label's place on a line: its unloaded webbing at `fraction` (about 70 %) of the span, in grid metres and height;
 *  the chord when the webbing has no curve. */
export function labelPoint(w: Webbing, anchors: [Anchor3d, Anchor3d], fraction = 0.7): [number, number, number] {
  const at = unloadedAt(w, anchors, w.span * fraction);
  if (at) return at;
  const [a, b] = anchors;
  return [a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction, a.h + (b.h - a.h) * fraction];
}
