// The outlines and areas as the drawings need them: features by kind and id, the small areas drawn as dots at
// their centroids, the areas grouped by the parts of the world the cameras visit, and the areas worth naming.
import { geoCentroid } from "d3-geo";
import { COVERAGE, type Shape, type Shapes } from "../data";

/** The parts of the world with a camera of their own (map.ts BOXES), in the order the tours visit them. */
export const GROUPS = ["europe", "na", "oceania"] as const;
export type Group = (typeof GROUPS)[number];
export type View = "world" | Group;

const CONTINENT_GROUP: Record<string, Group> = {"Europe": "europe", "North America": "na", "Oceania": "oceania"};

export interface World {
  countries: Shape[];             // without Antarctica (never shown) and with the rests of covered countries
  regions: Shape[];
  byId: Map<string, Shape>;       // the covered part of a split country
  small: string[];                // areas with data drawn as dots too
  centroids: Map<string, [number, number]>;
  groups: Record<Group, string[]>;  // the areas of coverage.json in its order; areas elsewhere in none
  listed: string[];               // the areas a list or a caption names (see `listed`)
}

/** The areas a text names: an area with the same provider and resolutions as one before it (Puerto Rico and
 *  the Virgin Islands with the USA, Liechtenstein with Switzerland, Åland with Finland, the Canary Islands
 *  with Spain) is told by that one. */
function listed(): string[] {
  const seen = new Set<string>(), out: string[] = [];
  for (const [id, area] of Object.entries(COVERAGE.areas)) {
    const key = `${area.provider}|${area.res.join(",")}`;
    if (!seen.has(key)) out.push(id);
    seen.add(key);
  }
  return out;
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
  const groups: Record<Group, string[]> = {europe: [], na: [], oceania: []};
  for (const id of Object.keys(COVERAGE.areas)) {
    // a region lies on its country's continent
    const country = byId.get(id.split("-")[0]), group = CONTINENT_GROUP[country?.properties.continent || ""];
    if (group) groups[group].push(id);
  }
  return {countries, regions, byId, small, centroids, groups, listed: listed()};
}
