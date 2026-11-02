// The coverage data in the bundle (coverage.json, from the source catalogue) and the outlines, loaded
// when a map needs them (coverage-shapes.json next to the bundle: about 0.8 MB).
import type { Feature, FeatureCollection, Geometry } from "geojson";
import data from "./coverage.json";
import type { Area, Coverage, Level, ShapeProperties } from "./types";

export const COVERAGE = data as unknown as Coverage;

export const areaOf = (id: string): Area | null => COVERAGE.areas[id] || null;

/** The level of an area's colour; an area without detailed data has the world's. */
export const levelOf = (id: string): Level => COVERAGE.areas[id]?.level ?? 3;

/** The areas of a country with detailed data in some regions only, else []. */
export const regionsOf = (country: string): string[] => COVERAGE.partly[country] || [];

/** The timeline: the start (no areas), then the areas by the date their source went live. */
export function timeline(): { date: string; ids: string[] }[] {
  const days = new Map<string, string[]>();
  for (const [id, area] of Object.entries(COVERAGE.areas)) {
    if (!days.has(area.added)) days.set(area.added, []);
    days.get(area.added)!.push(id);
  }
  const steps = [...days.keys()].sort().map(date => ({date, ids: days.get(date)!}));
  return [{date: COVERAGE.start, ids: []}, ...steps];
}

export type Shape = Feature<Geometry, ShapeProperties>;
export type Shapes = FeatureCollection<Geometry, ShapeProperties>;

export const SHAPES_FILE = "coverage-shapes.json";

let loading: Promise<Shapes> | null = null;

/** The outlines from `url` (the bundle's folder + SHAPES_FILE by default), fetched once. */
export function loadShapes(url = SHAPES_FILE): Promise<Shapes> {
  if (!loading) {
    loading = fetch(url).then(answer => {
      if (!answer.ok) throw new Error(`${url}: HTTP ${answer.status}`);
      return answer.json() as Promise<Shapes>;
    });
    loading.catch(() => { loading = null; });
  }
  return loading;
}
