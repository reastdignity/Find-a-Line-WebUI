// The webbing and the walker as the scene draws them, pure (tested in Node: tests/test_viewer.py): curves of a
// fixed number of points (the Line2's buffers are written in place), the walker's pose on the loaded webbing,
// and the readout's values from /api/profile.

import type { Profile } from "../types";
import type { Anchor3d } from "./decode";
import { loadedAt, toScene, type Origin, type Point3d, type Webbing } from "./geometry";

export { webbing } from "./geometry";  // the webbing these draw, with them for line.ts and the tests

/** The points of each curve drawn. */
export const CURVE_POINTS = 61;
/** The walker's height, metres. */
export const WALKER_HEIGHT = 1.7;

/** `points` resampled to `n` points, evenly by their index (the ends kept). */
export function resample(points: Point3d[], n = CURVE_POINTS): Point3d[] {
  if (points.length === n) return points.map((p) => [p[0], p[1], p[2]]);
  const out: Point3d[] = [];
  for (let k = 0; k < n; k++) {
    const t = k / (n - 1) * (points.length - 1), i = Math.min(points.length - 2, Math.floor(t)), a = t - i;
    const p = points[i], q = points[i + 1];
    out.push([p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a, p[2] + (q[2] - p[2]) * a]);
  }
  return out;
}

/** Write grid points into a Line2's segment buffer (start xyz, end xyz per segment) in the scene's axes. */
export function writeSegments(points: Point3d[], origin: Origin, out: Float32Array) {
  for (let k = 0; k + 1 < points.length; k++) {
    const a = toScene(origin, ...points[k]), b = toScene(origin, ...points[k + 1]);
    out.set(a, 6 * k);
    out.set(b, 6 * k + 3);
  }
}

export interface WalkerPose {
  /** Where the feet stand: grid metres and height. */
  at: Point3d;
  /** The loaded webbing (CURVE_POINTS points) and its sag below the chord at the walker. */
  points: Point3d[];
  sag: number;
  /** The scene's rotation about Y that turns the walker's +Z (its front) along the line towards anchor 2. */
  yaw: number;
}

/** The walker at distance `s` along the span on the loaded webbing; null when the sag solver fails. */
export function walkerPose(w: Webbing, anchors: [Anchor3d, Anchor3d], s: number): WalkerPose | null {
  const loaded = loadedAt(w, anchors, s);
  if (!loaded) return null;
  const [a, b] = anchors;
  // Scene direction of the line: X = x, Z = −y; the yaw turns +Z onto it (rotation.y = atan2(dX, dZ))
  const yaw = Math.atan2(b.x - a.x, -(b.y - a.y));
  return {at: loaded.walker, points: resample(loaded.points), sag: loaded.sag, yaw};
}

/** Whether a line fits: over the terrain and the trees ("fits"), over the terrain only ("terrain_only": the
 *  surface model's clearance ≤ 0, as mapping.coordify's over_obstacles), or not at all ("no_fit": the clearance
 *  over the terrain below 0, the 2D profile's "does not fit"). */
export type Verdict = "fits" | "terrain_only" | "no_fit";

export function verdictOf(p: Pick<Profile, "min" | "min_nmpt">): Verdict {
  if (p.min[1] < 0) return "no_fit";
  return p.min_nmpt && p.min_nmpt[1] <= 0 ? "terrain_only" : "fits";
}

/** The webbing's colour token of a verdict. */
export const VERDICT_COLOUR: Record<Verdict, string> = {fits: "--clear", terrain_only: "--trees", no_fit: "--bad"};

export interface Readout {
  length: number;
  clearance: number;
  /** Over trees or buildings while fitting over the terrain (verdict "terrain_only"). */
  overTrees: boolean;
  verdict: Verdict;
}

/** The readout's values of a line's profile: its length, the clearance over the terrain and its verdict. */
export function readoutOf(p: Profile): Readout {
  const verdict = verdictOf(p);
  return {length: p.d[p.d.length - 1], clearance: p.min[1], overTrees: verdict === "terrain_only", verdict};
}

/** A number of metres for the readout: one decimal. */
export function metres(v: number): string {
  return v.toFixed(1);
}
