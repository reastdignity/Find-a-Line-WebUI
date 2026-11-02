// The types 3d-tiles-renderer 0.5.3 leaves out of its declarations (the class is exported by
// "3d-tiles-renderer/three/plugins" at run time: src/three/plugins/images/terrain-rgb/TerrariumMeshPlugin.js): only
// what ring.ts uses, including the fields it reads or sets.

import "3d-tiles-renderer/three/plugins";

declare module "3d-tiles-renderer/three/plugins" {
  export class TerrariumMeshPlugin {
    constructor(options?: {
      url: string;
      tileDimension?: number;
      maxZoom?: number;
      heightScale?: number;
      unlit?: boolean;
      projection?: "ellipsoid" | "source" | string;
      endCaps?: boolean;
      useRecommendedSettings?: boolean;
    });
    name: string;
    /** The deepest zoom of the elevation tiles fetched (every second zoom up to it). */
    _maxSourceLevel: number;
    loadRootTileset(): Promise<unknown>;
    /** The loaded elevation at lat/lon (radians), null where none is loaded. */
    sampleCartographicElevation(lat: number, lon: number): number | null;
  }
}
