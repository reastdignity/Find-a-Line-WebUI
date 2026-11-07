// The no-fall zone at the line ends and the A-frames (helpers.end_zone_rule), as the viewer needs them: the zone's
// metres and steps (helpers.zone_steps, the same integer arithmetic), the safety limit of the rule at a point, and
// what a line needs rigged (the values the search saved, or for a line without them, its profile's). Pure: the
// profile chart (Profile.tsx, both bundles), the filters and the line's details use it; tests/test_viewer.py runs it
// in Node against Python.

import type { Line, Profile } from "./types";

/** The share of a line's length the zone may take at each end (helpers.ZONE_CAP). */
export const ZONE_CAP = 0.25;

/** The zone's metres at each end of a line of `length` metres: min(end_zone, ZONE_CAP · length), 0 when off. */
export function zoneMetres(length: number, endZone: number, cap = ZONE_CAP): number {
  const d = Math.min(endZone, cap * length);
  return d > 0 ? d : 0;
}

/** helpers.zone_steps: kz of a line of `steps` DDA steps and `length` metres, the number of steps k >= 0 whose
 *  distance k · length / steps from the nearer anchor is below the zone's metres; step k lies in the zone iff
 *  min(k, steps - k) < kz. The same operations as Python's (a float64 product and quotient, then ceil). */
export function zoneSteps(steps: number, length: number, endZone: number, cap = ZONE_CAP): number {
  const d = Math.min(endZone, cap * length);
  if (!(d > 0)) return 0;
  return Math.ceil(d * steps / length);
}

/** Whether step k of `steps` lies in the zone of `kz` steps (zoneSteps). */
export const stepInZone = (k: number, steps: number, kz: number) => Math.min(k, steps - k) < kz;

/** Whether a point `d` metres from anchor 1 lies in a zone of `zone` metres (zoneMetres) of a line of `length`
 *  metres. For a DDA step's exact distance k · length / steps this is stepInZone's answer: an integer m is below
 *  ceil(x) exactly when it is below x, so min(k, steps - k) < kz iff min(k, steps - k) · length / steps < zone. */
export function inZone(d: number, length: number, zone: number): boolean {
  return zone > 0 && Math.min(d, length - d) < zone;
}

/** The rule of a run (or a chart): the model's limit and what the zone gives up below the webbing. */
export interface LimitRule {
  model: "formula" | "sag";
  slope: number;      // formula: metres of drop per metre from the nearer anchor
  leashFall: number;  // formula: the leash fall
  fall: number;       // sag: the fall zone below the loaded webbing
  zone: number;       // metres of the zone at each end (zoneMetres; 0: none)
}

/** What the zone gives up below the webbing: the fall allowance (helpers.end_delta with no end clearance). */
export const zoneDelta = (rule: LimitRule) => rule.model === "sag" ? rule.fall : rule.leashFall;

/** The safety limits of a line whose anchors (already raised by their A-frames) stand at e1 and e2:
 *  `strict(d)` helpers.max_safe_elevation's (the formula, or the loaded webbing `envelopeAt` less the fall zone),
 *  `limitAt(d)` the rule's (strict, raised by the zone's delta inside it): one function for the chart's line, the
 *  smallest clearance and the readout. NaN for the sag model without an envelope. */
export function limits(len: number, e1: number, e2: number, rule: LimitRule,
                       envelopeAt: ((d: number) => number) | null) {
  const delta = zoneDelta(rule);
  const strict = (d: number) => rule.model !== "sag"
    ? Math.min(e1, e2) - rule.slope * Math.min(d, len - d) - rule.leashFall
    : envelopeAt ? envelopeAt(d) - rule.fall : NaN;
  const zoned = (d: number) => inZone(d, len, rule.zone);
  return {strict, inZone: zoned, limitAt: (d: number) => strict(d) + (zoned(d) ? delta : 0)};
}

/** What a line needs rigged: the A-frame height with the run's zone and without any zone (metres, 0: none; null:
 *  not known). */
export interface RiggingNeed { needed: number; noZone: number | null }

/** The rigging a line needs: the search's values (`lift_needed`, `lift_no_zone`); for a line without them (the 3D
 *  view's, a line computed again) from its profile when that was made with the rule (`zone`/`lift` keys): every
 *  limit moves with the A-frames, so the need with the zone is the lift less the rule's smallest clearance, and
 *  without the zone the smallest strict margin over the profile's points (a thinned profile may miss its
 *  lowest point by a little; the sag model's is not known there); null for a run without the options. */
export function riggingNeed(l: Line, p: Profile | null | undefined, rule: LimitRule | null): RiggingNeed | null {
  if (typeof l.lift_needed === "number") {
    return {needed: l.lift_needed, noZone: typeof l.lift_no_zone === "number" ? l.lift_no_zone : l.lift_needed};
  }
  if (!p || p.lift === undefined || !rule) return null;
  const lift = p.lift || 0;
  const needed = Math.max(0, lift - p.min[1]);
  const n = p.d.length - 1, len = p.d[n];
  if (!rule.zone) return {needed, noZone: needed};
  if (p.z[0] === null || p.z[n] === null || rule.model === "sag") return {needed, noZone: null};
  // the strict margins at lift 0 (the formula needs no envelope; the sag model's limit is the chart's to draw)
  const at0 = limits(len, p.z[0]!, p.z[n]!, {...rule, zone: 0}, null);
  let smallest = Infinity;
  for (let i = 1; i < n; i++) {
    const z = p.z[i];
    if (z !== null) smallest = Math.min(smallest, at0.strict(p.d[i]) - z);
  }
  return {needed, noZone: isFinite(smallest) ? Math.max(needed, -smallest, 0) : needed};
}

/** The choices of the filter "A-frame needed at most": 0 to the run's A-frame height in steps of 0.5 m, the
 *  height itself last when it is not a multiple. */
export function liftChoices(lift: number): number[] {
  const out: number[] = [];
  for (let v = 0; v < lift - 1e-9; v += 0.5) out.push(Math.round(v * 10) / 10);
  out.push(lift);
  return out;
}

/** A height in metres as the texts write it: one decimal at most ("2", "1.5", "0.3"). */
export function shortMetres(v: number): string {
  return String(Math.round(v * 10) / 10);
}
