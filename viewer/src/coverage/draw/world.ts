// The outlines and areas as the drawings need them: features by kind and id, the small areas drawn as dots at
// their centroids, the areas grouped by the parts of the world the cameras visit, and the areas worth naming.
import { geoCentroid } from "d3-geo";
import { COVERAGE, type Shape, type Shapes } from "../data";
import { camFor, projFor } from "./map";

/** The parts of the world with a camera of their own (map.ts BOXES), in the order the slides show them (the
 *  tour's own order: scenes.ts `tourPlan`). */
export const GROUPS = ["europe", "na", "caribbean", "sa", "asia", "oceania", "africa"] as const;
export type Group = (typeof GROUPS)[number];
export type View = "world" | Group;

/** The frame an area's view is judged in: the README's map (1600 x 800 less its caption band). */
const FRAME = {x: 0, y: 0, w: 1600, h: 664};

/** The view an area belongs to: of the views whose frame shows its centre, the one where it lies nearest the middle
 *  (Puerto Rico the Caribbean's, not North America's; Iceland Europe's); none when no view shows it. */
function homeOf(at: [number, number]): Group | null {
  let best: Group | null = null, bestD = Infinity;
  for (const g of GROUPS) {
    const xy = projFor(camFor(g, FRAME), FRAME)(at);
    if (!xy) continue;
    const dx = (xy[0] - FRAME.w / 2) / (FRAME.w / 2), dy = (xy[1] - FRAME.h / 2) / (FRAME.h / 2);
    const d = Math.hypot(dx, dy);
    if (Math.abs(dx) <= .96 && Math.abs(dy) <= .96 && d < bestD) { best = g; bestD = d; }
  }
  return best;
}

export interface World {
  countries: Shape[];             // without Antarctica (never shown) and with the rests of covered countries
  regions: Shape[];
  byId: Map<string, Shape>;       // the covered part of a split country
  small: string[];                // areas with data drawn as dots too
  centroids: Map<string, [number, number]>;
  groups: Record<Group, string[]>;  // each area in its view (homeOf), in coverage.json's order; areas no view shows in none
  listed: string[];               // the areas a list or a caption names (see `listed`)
}

/** The areas a text names: of the areas of one source (Puerto Rico and the Virgin Islands with the USA,
 *  Liechtenstein with Switzerland, Åland with Finland, Berlin with Brandenburg, Jan Mayen with Svalbard)
 *  only one, the first that is not `small` (else the first): coverage.json's order puts Puerto Rico before
 *  the USA. Not by provider: Greenland, Svalbard, Nunavut and Iceland share ArcticDEM's. */
function listed(small: Set<string>): string[] {
  const chosen = new Map<string, string>();
  for (const [id, area] of Object.entries(COVERAGE.areas)) {
    const key = area.source, before = chosen.get(key);
    if (before === undefined || small.has(before) && !small.has(id)) chosen.set(key, id);
  }
  const names = new Set(chosen.values());
  return Object.keys(COVERAGE.areas).filter(id => names.has(id));
}

export function prepareWorld(shapes: Shapes): World {
  const countries: Shape[] = [], regions: Shape[] = [], byId = new Map<string, Shape>();
  for (const f of shapes.features) {
    const p = f.properties;
    if (p.kind === "region") regions.push(f);
    else if (p.continent !== "Antarctica") countries.push(f);
    if (!p.rest) byId.set(p.id, f);
  }
  const small = Object.keys(COVERAGE.areas).filter(id => byId.get(id)?.properties.small);
  const centroids = new Map(small.map(id => [id, geoCentroid(byId.get(id)!) as [number, number]]));
  const groups = Object.fromEntries(GROUPS.map(g => [g, [] as string[]])) as Record<Group, string[]>;
  for (const id of Object.keys(COVERAGE.areas)) {
    // by where the area lies, not by its country: Guadeloupe and Réunion are no part of Europe's view
    const shape = byId.get(id);
    if (!shape) continue;
    const home = homeOf(centroids.get(id) || geoCentroid(shape) as [number, number]);
    if (home) groups[home].push(id);
  }
  return {countries, regions, byId, small, centroids, groups, listed: listed(new Set(small))};
}
