// Where the terrain of a run's land came from (data.js `terrain_sources`, sources.filling.terrain_origins): the
// source's own data, a neighbour's, and the coarser fallbacks that filled where the source has none, with the
// regions they filled. The pure parts: the shares as text, whether the result warns, the km² of each fallback in a
// map's view (coarserLayer.ts draws them with Leaflet, tested in Node: tests/test_viewer.py).

import { overlaps, type LatLngBox } from "./shore";
import type { CoarserRegion, TerrainLayer, TerrainSources } from "./types";

/** The fallbacks' share of the land from which a result warns: search.FALLBACK_WARN_SHARE. */
export const FALLBACK_WARN_SHARE = 0.10;

/** The box of a region's outline (its first ring, lon, lat pairs). */
export function regionBox(r: CoarserRegion): LatLngBox {
  let south = Infinity, west = Infinity, north = -Infinity, east = -Infinity;
  for (const [lon, lat] of r.rings[0]) {
    if (lat < south) south = lat;
    if (lat > north) north = lat;
    if (lon < west) west = lon;
    if (lon > east) east = lon;
  }
  return {south, west, north, east};
}

/** The box of every region, or null without any. */
export function regionsBox(sources: TerrainSources): LatLngBox | null {
  if (!sources.regions.length) return null;
  const boxes = sources.regions.map(regionBox);
  return {south: Math.min(...boxes.map((b) => b.south)), west: Math.min(...boxes.map((b) => b.west)),
          north: Math.max(...boxes.map((b) => b.north)), east: Math.max(...boxes.map((b) => b.east))};
}

/** The km² of each layer (by its index in `layers`) among the regions whose box reaches `view` (a map's bounds):
 *  whole regions, so "about". */
export function km2InView(sources: TerrainSources, view: LatLngBox, boxes?: LatLngBox[]): number[] {
  const km2 = sources.layers.map(() => 0);
  sources.regions.forEach((r, k) => {
    if (overlaps(boxes?.[k] ?? regionBox(r), view)) km2[r.layer] += r.km2;
  });
  return km2;
}

/** A run worth the map's layer: at least one region. */
export function hasCoarser(sources: TerrainSources | null | undefined): sources is TerrainSources {
  return !!sources && sources.regions.length > 0;
}

/** The result warns (its head's note): the fallbacks gave FALLBACK_WARN_SHARE of the land or more. */
export function warns(sources: TerrainSources | null | undefined): sources is TerrainSources {
  return !!sources && sources.fallback_share >= FALLBACK_WARN_SHARE;
}

/** A share as a percentage with one decimal ("97.6"), as the search's info line prints it. */
export function percent(share: number): string {
  return (Math.round(share * 1000) / 10).toFixed(1).replace(/\.0$/, "");
}

/** A layer's name with its resolution ("USGS 3DEP (1/3 arc-second DEM), 10 m"). */
export function layerName(layer: TerrainLayer): string {
  return layer.resolution ? `${layer.name}, ${layer.resolution} m` : layer.name;
}

/** The fallbacks of a run, in their order. */
export function fallbacks(sources: TerrainSources): TerrainLayer[] {
  return sources.layers.filter((l) => l.role === "fallback");
}

/** The shares of every layer that gave some land ("97.6 % geoportal.gov.pl, 1 m · 2.4 % FABDEM …, 30 m"). */
export function sharesText(sources: TerrainSources): string {
  return sources.layers.filter((l) => l.share > 0).map((l) => `${percent(l.share)} % ${layerName(l)}`).join(" · ");
}

/** km² as the map's box writes it: two decimals, three under 0.1, "under 0.001" below. */
export function km2Text(km2: number): string {
  if (km2 < 0.001) return "under 0.001";
  return km2 < 0.1 ? km2.toFixed(3) : km2.toFixed(2);
}
