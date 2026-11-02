// The coverage map's data: coverage.json, written by tools/coverage_data.py from the source catalogue
// (sources/catalogue, Source.coverage), and the outlines of coverage-shapes.json (tools/coverage_shapes.py,
// Natural Earth). Change both sides together.

/** 1: 1 m or finer, 2: 2 to 5 m, 3: the global 30 m. */
export type Level = 1 | 2 | 3;

/** Whether the data knows trees and buildings (a surface model next to the terrain): "part" in some of
 *  the area only, "rough" at 30 m (the rest of the world). */
export type Trees = "yes" | "no" | "part" | "rough";

/** A remark on an area's data: locales/coverage "note.<code>", its params interpolated (numbers are
 *  metres, written with their unit by i18n.ts noteText). */
export interface Note { code: string; params?: Record<string, string | number | number[]> }

/** One area of the map: a country (ISO 3166-1 alpha-2) or a region (ISO 3166-2), lower case. */
export interface Area {
  source: string;     // the id of its source in the catalogue
  level: Level;       // the colour of the area
  partial: boolean;   // the level is reached in parts of the area only (drawn hatched over the 30 m base)
  res: number[];      // the resolutions of its data in metres, finest first (more than one: a mix, note "mixed")
  trees: Trees;
  survey: string;     // "2018", "2017–2023", a code (locales/coverage "survey.<code>") or "" (not shown)
  provider: string;   // the provider's short name ("GUGiK", "swisstopo")
  notes: Note[];      // in the order they are shown
  added: string;      // ISO date the source went live (the timeline)
}

export interface Coverage {
  areas: Record<string, Area>;
  /** A country whose detailed data covers some of its regions only: those regions ("de": ["de-by", ...]). */
  partly: Record<string, string[]>;
  /** Countries with detailed data; a territory counts with its state (pr, vi with us; ax with fi). */
  countries: number;
  /** The first version of Find-a-Line (the whole world at 30 m): the timeline's start. */
  start: string;
  /** The rest of the world. */
  world: { level: 3; res: number[]; trees: "rough"; provider: string };
}

/** coverage-shapes.json: a GeoJSON FeatureCollection; every area of coverage.json has a feature. */
export interface ShapeProperties {
  id: string;                    // as the keys of Coverage.areas; countries without data too
  kind: "country" | "region";    // a region is drawn over its country
  continent: string | null;      // Natural Earth's CONTINENT of a country, null for a region
  small: boolean;                // too small to see on a world map: drawn as a dot at its centroid
  rest?: true;                   // the part of a country its source does not cover (France's overseas
                                 // regions, Svalbard): a feature of its own with the country's id, at 30 m
}

/** The 30 m against 1 m comparison at famous places: docs/coverage/contrast/contrast.json, written by
 *  tools/coverage_contrast.py (the hillshades are JPEG files next to it). */
export interface ContrastSide {
  image: string;           // the hillshade's file name, a square of 2 x radius
  res: number;             // metres
  lines: number;
  spots: number;           // groups of lines (the map's spots)
  segments: [number, number, number, number, 0 | 1][];  // spots' lines in the square, 0..1 (x1, y1, x2, y2, over obstacles)
  relief: [number, number];  // lowest and highest height in the square
  source: string;
  source_name: string;
  credits: { data: string; attribution: string; licence: string; url: string; notice?: string }[];
}
export interface ContrastPlace {
  lat: number; lon: number; radius: number;
  fine: ContrastSide; coarse: ContrastSide;
  verify: { fine_spots: number; fine_found: number; coarse_spots: number; coarse_real: number };
}
export interface Contrast {
  threshold: number;       // the 30 m search's slope threshold (degrees)
  match_radius: number;    // a 30 m spot is real when a 1 m line has both anchors within this many metres
  places: Record<string, ContrastPlace>;
  verify: { places: number; fine_spots: number; fine_found: number; coarse_spots: number; coarse_real: number };
}
