// The coarse ring of terrain around the patch (docs/3d-view-contract.md, "Wave 3", V3b): 3DTilesRendererJS over
// the terrain tiles of the page's meta findaline-3d-ring (Mapterhorn's on the public site, behind
// FINDALINE_3D_RING), cut out under the patch, its imagery following the imagery control. A stub with the
// final signature until wave 3b fills it: the page calls it as it will call the real one.

import type { Imagery } from "./imagery";
import type { Scene3D } from "./scene-api";

export interface Ring {
  dispose(): void;
}

/** The ring's tile URL template ({z}/{x}/{y}) of the page's meta, or null without a ring ("off", no meta). */
export function ringUrl(): string | null {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="findaline-3d-ring"]');
  const url = meta ? meta.content.trim() : "";
  return url && url !== "off" ? url : null;
}

/** The ring around `scene`'s patch from the tiles of `url`; its imagery follows `imagery`, its credit goes to
 *  `scene.credits`. */
export function createRing(scene: Scene3D, imagery: Imagery, url: string): Ring {
  void scene; void imagery; void url;
  return { dispose() {} };
}
