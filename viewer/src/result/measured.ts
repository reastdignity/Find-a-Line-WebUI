// A line measured between two points from its profile (the result's "measure" and the 3D view's chart): no
// Preact, no model, so the 3D page's bundle takes it alone.

import { percentileRank, type Line, type Profile, type Terrain } from "../types";

/** A line measured between two points from its profile; its ends' percentiles from the run's terrain when known. */
export function measuredLine(a: [number, number], b: [number, number], p: Profile, terrain?: Terrain | null): Line {
  const n = p.d.length - 1;
  if (p.z[0] === null || p.z[n] === null) throw new Error("no terrain data at a point");
  return {lat1: a[0], lon1: a[1], lat2: b[0], lon2: b[1], x1: 0, y1: 0, x2: 0, y2: 0,
          len: p.d[n], clr: p.min[1], clrN: p.min_nmpt ? p.min_nmpt[1] : null,
          e1: p.z[0]!, e2: p.z[n]!, over: false, water: p.water_m, filled: p.filled_m,
          hmax: p.max_height ? p.max_height[1] : NaN, hmean: NaN, highPct: NaN,
          angle1: NaN, angle2: NaN, prom1: null, prom2: null, drop1: null, drop2: null,
          pct1: terrain ? percentileRank(p.z[0]!, terrain.quantiles) : null,
          pct2: terrain ? percentileRank(p.z[n]!, terrain.quantiles) : null, prof: p};
}
