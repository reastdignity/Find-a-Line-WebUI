// The lines from a point, pure (docs/3d-view-contract.md, "Round 2", point 9; tested in Node:
// tests/test_view3d_point.py): the candidates of a reach (the valid samples of its mask as lines from the picked
// point), the representatives (the first line of each of the groups `groupLines` makes of them, the grouping of
// the 2D result's spots, clear lines before lines over trees, at most FAN_MAX), the sorting of their list and the
// test of a click.

import { groupLines, type Groupable } from "../grouping";
import type { Reach } from "./reach";

/** The most lines the fan and its list show. */
export const FAN_MAX = 40;
/** The most candidates grouped: the valid samples of the largest clearance. */
export const CANDIDATES_MAX = 20_000;
/** How far (CSS pixels) a press and its release may lie apart to count as a click and not a drag. */
export const CLICK_SLOP_PX = 5;

/** The grouping distance when the patch's meta does not carry the run's (`group_distance`): params.py's default,
 *  `max(20, 2 × resolution)` (search.plan_search). `res` is the patch's, `step` 1 or 2 its subsampling. */
export const GROUP_DISTANCE_MIN = 20;

export function groupingDistance(meta: {group_distance?: number | null; res: number; step?: number}): number {
  const given = meta.group_distance;
  if (typeof given === "number" && Number.isFinite(given) && given > 0) return given;
  return Math.max(GROUP_DISTANCE_MIN, 2 * meta.res / (meta.step || 1));
}

/** A line from the picked point to a valid sample, in the shape `groupLines` takes: (x1, y1) the point, (x2, y2)
 *  the sample's centre, `len` its distance, `clr` the mask's clearance (an upper bound within the mask's quantum),
 *  `over` the line passes over trees or buildings. `hmax` is 0: the mask has no heights above the terrain, and the
 *  list is grouped by clearance. */
export interface Candidate extends Groupable {
  /** The sample's row and column in the mask. */
  i: number;
  j: number;
}

/** The valid samples of a reach as lines from its fixed point: all of them, or the `max` of the largest clearance
 *  (ties by the samples' order, row by row), in the mask's order. */
export function candidates(reach: Reach, max = CANDIDATES_MAX): Candidate[] {
  const {meta, mask} = reach, {width, height, lattice, res, left, top, quantum} = meta;
  const counts = new Uint32Array(128);
  let total = 0;
  for (let k = 0; k < mask.length; k++) if (mask[k] !== 0) { counts[mask[k] & 0x7f]++; total++; }
  // The cut: every clearance step above `cut` is kept, and `spare` samples of the step itself
  let cut = 0, spare = total;
  if (total > max) {
    let above = 0;
    for (cut = 127; cut >= 0; cut--) {
      if (above + counts[cut] >= max) break;
      above += counts[cut];
    }
    spare = max - above;
  }
  const {x: x1, y: y1} = meta.anchor, out: Candidate[] = [];
  for (let i = 0; i < height; i++) {
    const y2 = top - (i * lattice + 0.5) * res;
    for (let j = 0; j < width; j++) {
      const b = mask[i * width + j];
      if (b === 0) continue;
      const v = b & 0x7f;
      if (total > max) {
        if (v < cut) continue;
        if (v === cut && spare-- <= 0) continue;
      }
      const x2 = left + (j * lattice + 0.5) * res;
      out.push({x1, y1, x2, y2, len: Math.hypot(x2 - x1, y2 - y1), clr: v * quantum, over: (b & 0x80) !== 0, hmax: 0, i, j});
    }
  }
  return out;
}

/** One line of the fan and the list. */
export interface Option extends Candidate {
  /** Its place in the fan's order (clear lines first, the best clearance first), from 0. */
  rank: number;
  /** The lines of its group, itself included. */
  members: number;
  /** The target's height and its difference to the point's (target less point), null where the patch has no height. */
  h: number | null;
  dh: number | null;
}

export interface OptionsInput {
  /** The grouping distance in metres (`groupingDistance`). */
  distance: number;
  /** The run's `group_by` (default: clearance). */
  by?: string;
  max?: number;
  candidatesMax?: number;
  /** The patch's height at grid metres (null: none) and the point's. */
  heightAt?: (x: number, y: number) => number | null;
  h1?: number | null;
}

/** The representatives: `groupLines` over the candidates, the first line of each group in its order (lines clear
 *  of trees before lines over them), at most `max`. */
export function representatives(reach: Reach, input: OptionsInput): Option[] {
  const groups = groupLines(candidates(reach, input.candidatesMax ?? CANDIDATES_MAX), input.distance,
                            input.by ?? "clearance");
  return groups.slice(0, input.max ?? FAN_MAX).map((g, rank) => {
    const h = input.heightAt ? input.heightAt(g.rep.x2, g.rep.y2) : null;
    const h1 = input.h1 ?? null;
    return {...g.rep, rank, members: g.members.length, h, dh: h !== null && h1 !== null ? h - h1 : null};
  });
}

/** The list's columns. */
export type SortKey = "rank" | "length" | "clear" | "dh" | "trees";

/** The options sorted by a column (a copy; stable, so equal values keep the fan's order; a missing value last
 *  whichever way). "trees": clear lines before lines over trees. */
export function sortOptions(options: readonly Option[], key: SortKey, descending = false): Option[] {
  const value = (o: Option): number | null =>
    key === "length" ? o.len : key === "clear" ? o.clr : key === "dh" ? o.dh : key === "trees" ? (o.over ? 1 : 0) : o.rank;
  const sign = descending ? -1 : 1;
  return options.map((o, k) => ({o, k})).sort((a, b) => {
    const x = value(a.o), y = value(b.o);
    if (x === null || y === null) return x === y ? a.k - b.k : x === null ? 1 : -1;
    return (x - y) * sign || a.k - b.k;
  }).map((e) => e.o);
}

/** Whether a press at (x0, y0) and a release at (x1, y1) (CSS pixels) make a click and not a drag. */
export function isClick(x0: number, y0: number, x1: number, y1: number, slop = CLICK_SLOP_PX): boolean {
  return Math.hypot(x1 - x0, y1 - y0) <= slop;
}

/** A signed number of metres with one decimal ("+3.2", "−0.4"; a true minus sign). */
export function signedMetres(v: number): string {
  const s = Math.abs(v).toFixed(1);
  return Number(s) === 0 ? "0.0" : (v < 0 ? "−" : "+") + s;
}
