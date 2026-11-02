// The imagery of the 3D view (docs/3d-view-contract.md, "Wave 2"): the run's national orthophoto (our cache
// first, then the service), Esri's satellite imagery (with a key), or the terrain shaded. A stub with the final
// signature until wave 2b fills it: the scene core calls it as it will call the real one.

import type { Scene3D } from "./scene-api";

export type ImageryKind = "ortho" | "esri" | "shaded";

export interface Imagery {
  /** The kinds this run can show, the default first. */
  available: ImageryKind[];
  current: ImageryKind;
  set(kind: ImageryKind): Promise<void>;
  dispose(): void;
}

/** The imagery of `scene`: its control in `scene.toolbar`, its credits in `scene.credits`. */
export function createImagery(scene: Scene3D, options: { runId: string; esriKey: string | null }): Imagery {
  void scene; void options;
  return { available: ["shaded"], current: "shaded", async set() {}, dispose() {} };
}
