// The outlines of the coverage map as the three views draw them: the features in drawing order
// (countries, then the regions over them), the dots of small covered areas and what a point hits.
// A feature's key is its id, or "<id>:rest" for the part of a country its source does not cover.
import { geoCentroid, geoContains } from "d3-geo";
import { areaOf, levelOf, type Shape, type Shapes } from "../data";
import type { Level } from "../types";

export const restKey = (id: string) => `${id}:rest`;
export const keyOf = (shape: Shape): string => (shape.properties.rest ? restKey(shape.properties.id) : shape.properties.id);
/** The area id of a key, and whether it is a country's rest. */
export const parseKey = (key: string): {id: string; rest: boolean} =>
  key.endsWith(":rest") ? {id: key.slice(0, -5), rest: true} : {id: key, rest: false};

/** The colour level of a key: a country's rest is at the world's 30 m. */
export const levelOfKey = (key: string): Level => {
  const {id, rest} = parseKey(key);
  return rest ? 3 : levelOf(id);
};
/** Whether a key is drawn hatched (its level reached in parts only). */
export const partialOfKey = (key: string): boolean => {
  const {id, rest} = parseKey(key);
  return !rest && !!areaOf(id)?.partial;
};

/** The zoom presets: [[west, south], [east, north]] in degrees. Tasmania and Queensland lie inside Oceania's box. */
export const BOXES = {
  world: [[-170, -58], [190, 80]],
  europe: [[-11, 35], [33, 71.5]],
  na: [[-168, 16], [-52, 71]],
  oceania: [[138, -48], [180, -10]],
} as const;
export type BoxName = keyof typeof BOXES;
export const BOX_NAMES = Object.keys(BOXES) as BoxName[];

export interface Dot { key: string; lonlat: [number, number] }

export interface Geo {
  features: Shape[];   // in drawing order
  dots: Dot[];         // small areas with detailed data: drawn as dots too
  hitAt(lonlat: [number, number]): string | null;
}

export function makeGeo(shapes: Shapes): Geo {
  const countries = shapes.features.filter(f => f.properties.kind === "country" && f.properties.continent !== "Antarctica");
  const regions = shapes.features.filter(f => f.properties.kind === "region");
  const dots = [...countries, ...regions]
    .filter(f => f.properties.small && !f.properties.rest && levelOf(f.properties.id) < 3)
    .map(f => ({key: keyOf(f), lonlat: geoCentroid(f) as [number, number]}));
  return {
    features: [...countries, ...regions],
    dots,
    hitAt(lonlat) {
      for (const f of regions) if (geoContains(f, lonlat)) return keyOf(f);
      for (const f of countries) if (geoContains(f, lonlat)) return keyOf(f);
      return null;
    },
  };
}
