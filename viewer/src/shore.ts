// The uncertain shore of a run (data.js `shore`, sources.filling.shore_segments): where the terrain model had
// no data at the foot of a shore, so the surface model (kind "surface") or the sea fill (kind "sea") stands
// in; lines ending or passing there are less certain. The pure parts: which segments a map's view holds and
// their metres (shoreLayer.ts draws them with Leaflet, tested in Node: tests/test_viewer.py).

import type { Shore, ShoreKind, ShoreSegment } from "./types";

/** The colours of the two kinds, on the map and in the 3D view's hatching. */
export const SHORE_COLOURS: Record<ShoreKind, string> = {surface: "#e3912f", sea: "#c43d2f"};

export interface LatLngBox { south: number; west: number; north: number; east: number }

/** The box of a segment's ring (lon, lat pairs). */
export function segmentBox(s: ShoreSegment): LatLngBox {
  let south = Infinity, west = Infinity, north = -Infinity, east = -Infinity;
  for (const [lon, lat] of s.ring) {
    if (lat < south) south = lat;
    if (lat > north) north = lat;
    if (lon < west) west = lon;
    if (lon > east) east = lon;
  }
  return {south, west, north, east};
}

/** Two boxes meet (touching at an edge or a corner counts). */
export function overlaps(a: LatLngBox, b: LatLngBox): boolean {
  return a.south <= b.north && a.north >= b.south && a.west <= b.east && a.east >= b.west;
}

/** The metres of each kind among the segments whose box reaches `view` (a map's bounds). */
export function metresInView(shore: Shore, view: LatLngBox, boxes?: LatLngBox[]): Record<ShoreKind, number> {
  const metres: Record<ShoreKind, number> = {surface: 0, sea: 0};
  shore.segments.forEach((s, k) => {
    if (overlaps(boxes?.[k] ?? segmentBox(s), view)) metres[s.kind] += s.m;
  });
  return metres;
}

/** A shore worth a layer: at least one segment. */
export function hasShore(shore: Shore | null | undefined): shore is Shore {
  return !!shore && shore.segments.length > 0;
}
