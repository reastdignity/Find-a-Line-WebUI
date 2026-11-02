// The coarse ring of terrain around the patch (docs/3d-view-contract.md, "Wave 3", V3b): 3DTilesRendererJS's
// TilesRenderer with its TerrariumMeshPlugin over the terrain tiles of the page's meta findaline-3d-ring
// (Mapterhorn's on the public site, behind FINDALINE_3D_RING), placed into the scene's frame through the meta's
// affine (ringmath.ts ringFrame), cut out under the patch by clipping planes, its imagery (ImageOverlayPlugin's
// XYZ or WMS overlays) following the imagery control. Its level of detail does not follow the camera: a plugin
// of ours refines by the distance from the patch's centre only, so an open loads the same tiles wherever one
// looks (RING: the radius, the zoom of the elevation tiles, the mesh's spacing), and the tiles are updated only
// when the camera changed (UpdateOnChangePlugin), before a frame is drawn. With the "Edges" look (wave E) its
// tiles are terrain to the edges' pass (the scene's terrain layer), on the look's paper, without an overlay.

import { Matrix4, Plane, Vector3, type Material, type Mesh, type Object3D } from "three";
import { TilesRenderer } from "3d-tiles-renderer/three";
import {
  ImageOverlayPlugin, TerrariumMeshPlugin, UpdateOnChangePlugin, WMSTilesOverlay, XYZTilesOverlay,
  type ImageOverlay,
} from "3d-tiles-renderer/three/plugins";
import { esriKey } from "../layers";
import { RING_CREDIT, RING_CREDITS, RING_ORDER } from "./credits";
import type { Imagery, ImageryKind } from "./imagery";
import {
  centreEcef, cutPlanes, dataRect, edgeSamples, MESH_ZOOM, offsetStats, overlaySpecs, refines, RING, ringFrame,
  TERRAIN_PX, type OverlaySpec, type RingLevel,
} from "./ringmath";
import type { Scene3D } from "./scene-api";
import { orthoOf } from "./tiles";

export interface Ring {
  dispose(): void;
}

/** The ring's tile URL template ({z}/{x}/{y}) of the page's meta, or null without a ring ("off", no meta). */
export function ringUrl(): string | null {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="findaline-3d-ring"]');
  const url = meta ? meta.content.trim() : "";
  return url && url !== "off" ? url : null;
}

/** The terrain plugin with a tree down to MESH_ZOOM (meshes of 32 × 32 segments a tile) reading the elevation
 *  tiles of one zoom at most: the plugin fetches every second zoom up to the one its maxZoom gives
 *  (`_maxSourceLevel`, read on every tile), so it is clamped once the tree is made. */
class RingTerrain extends TerrariumMeshPlugin {
  constructor(url: string, private textureZoom: number) {
    super({url, tileDimension: TERRAIN_PX, maxZoom: MESH_ZOOM, useRecommendedSettings: false});
  }

  override async loadRootTileset() {
    const tileset = await super.loadRootTileset();
    this._maxSourceLevel = Math.min(this._maxSourceLevel, this.textureZoom);
    return tileset;
  }
}

interface ViewErrorTarget { inView: boolean; error: number; distance: number }
interface RingTile { geometricError: number; engineData: {boundingVolume: {distanceToPoint(p: Vector3): number}} }

/** Our level of detail: tiles within the radius are in view (also behind the camera), refined while their mesh
 *  is coarser than wanted at their distance from the patch's centre. With the renderer's errorTarget at the
 *  largest number, the camera's error refines only a tile holding the camera (its error is then infinite). */
function regionPlugin(level: RingLevel, centre: Vector3) {
  return {
    name: "FINDALINE_RING_REGION",
    calculateTileViewError(tile: RingTile, target: ViewErrorTarget) {
      const d = tile.engineData.boundingVolume.distanceToPoint(centre);
      target.inView = d <= level.radius;
      target.error = target.inView && refines(level, tile.geometricError, d) ? Infinity : 0;
      target.distance = d;
      return true;
    },
  };
}

function overlayOf(spec: OverlaySpec): ImageOverlay {
  return spec.type === "xyz" ? new XYZTilesOverlay({url: spec.url, levels: spec.levels})
    : new WMSTilesOverlay({url: spec.url, layer: spec.layer, crs: "EPSG:4326", version: "1.3.0", styles: "",
                           format: spec.format, transparent: spec.transparent});
}

/** The ring around `scene`'s patch from the tiles of `url`; its imagery follows `imagery`, its credit goes to
 *  `scene.credits`. */
export function createRing(scene: Scene3D, imagery: Imagery, url: string): Ring {
  const level = RING[scene.level];
  const root = scene.toolbar.closest<HTMLElement>(".ui");
  const state = (value: string | null) => {
    if (!root) return;
    if (value === null) delete root.dataset.ring; else root.dataset.ring = value;
  };
  const tiles = new TilesRenderer();
  tiles.errorTarget = Number.MAX_VALUE;
  tiles.loadSiblings = false;
  tiles.loadAncestors = false;
  const terrain = new RingTerrain(url, level.zoom);
  const overlays = new ImageOverlayPlugin({overlays: [], renderer: scene.renderer, resolution: level.imagery,
                                           enableTileSplitting: false});
  const centre = new Vector3(...centreEcef(scene.meta, scene.origin));
  tiles.registerPlugin(terrain);
  tiles.registerPlugin(overlays);
  tiles.registerPlugin(new UpdateOnChangePlugin());
  tiles.registerPlugin(regionPlugin(level, centre));

  // Into the scene's frame
  const group = tiles.group;
  group.matrixAutoUpdate = false;
  group.matrix.copy(new Matrix4().set(...(ringFrame(scene.meta, scene.origin) as Parameters<Matrix4["set"]>)));
  group.matrixWorldNeedsUpdate = true;
  group.name = "ring";

  // Cut out under the patch's data
  const rect = dataRect(scene.patch);
  const planes = rect ? cutPlanes(rect, scene.origin).map((p) => new Plane(new Vector3(...p.normal), p.constant)) : [];
  if (planes.length) scene.renderer.localClippingEnabled = true;
  const shadedColour = getComputedStyle(scene.toolbar).getPropertyValue("--terrain").trim() || "#bba680";
  const colourOf = (kind: ImageryKind) => kind === "edges" ? scene.paper : shadedColour;
  const paint = (model: Object3D, kind: ImageryKind, first: boolean) => {
    model.traverse((o) => {
      const mesh = o as Mesh;
      if (!mesh.isMesh) return;
      if (first) mesh.layers.enable(scene.terrainLayer);
      for (const m of ([] as Material[]).concat(mesh.material)) {
        if (first) { m.clippingPlanes = planes; m.clipIntersection = true; }
        const coloured = m as Material & {color?: {set(c: string): void}};
        coloured.color?.set(colourOf(kind));
      }
    });
  };
  const onModel = ({scene: model}: {scene: Object3D}) => {
    paint(model, imagery.current, true);
    scene.invalidate();
  };
  const onRender = () => scene.invalidate();
  let loaded = false;
  const onStart = () => { state(loaded ? "updating" : "loading"); scene.keepDrawing("ring", true); };
  const onEnd = () => {
    scene.keepDrawing("ring", false);
    loaded = true;
    measure();
    if (root) root.dataset.ringTiles = String(tiles.visibleTiles.size);
    state("loaded");
    scene.invalidate();
  };
  const onError = () => { if (root) root.dataset.ringErrors = String(Number(root.dataset.ringErrors || 0) + 1); };
  tiles.addEventListener("load-model", onModel as never);
  tiles.addEventListener("needs-render", onRender);
  tiles.addEventListener("needs-update", onRender);
  tiles.addEventListener("tiles-load-start", onStart);
  tiles.addEventListener("tiles-load-end", onEnd);
  tiles.addEventListener("load-error", onError as never);

  // The ring's heights against the patch's along the edge of its data (data-ring-offset: metres, the median and
  // the 90th percentile of the differences' size, and their median with its sign)
  const measure = () => {
    if (!root) return;
    const diffs: number[] = [];
    for (const s of edgeSamples(scene.patch)) {
      const [lon, lat] = scene.lonLat(s.x, s.y);
      const h = terrain.sampleCartographicElevation(lat * Math.PI / 180, lon * Math.PI / 180);
      if (h !== null && Number.isFinite(h)) diffs.push(h - s.h);
    }
    const stats = offsetStats(diffs);
    if (!stats) return;
    const signed = [...diffs].sort((a, b) => a - b)[Math.floor(diffs.length / 2)];
    root.dataset.ringOffset = JSON.stringify({...stats, signed, samples: diffs.length});
  };

  // The imagery: the overlays of the kind shown
  let shown: ImageOverlay[] = [];
  const ortho = orthoOf(scene.meta.ortho), key = esriKey();
  const show = (kind: ImageryKind) => {
    for (const o of shown) overlays.deleteOverlay(o);
    shown = overlaySpecs(kind, ortho, key).map(overlayOf);
    shown.forEach((o, k) => overlays.addOverlay(o, k));
    paint(group, kind, false);  // the loaded tiles: paper with the "Edges" look, else the shaded terrain's colour
    scene.invalidate();
  };
  show(imagery.current);
  const offChange = imagery.onChange(show);

  scene.add(group);
  tiles.setCamera(scene.camera);
  const offDraw = scene.beforeDraw(() => {
    tiles.setResolutionFromRenderer(scene.camera, scene.renderer);
    scene.camera.updateMatrixWorld();
    tiles.update();
  });
  scene.credits.set(RING_CREDITS, RING_CREDIT, RING_ORDER);
  state("loading");
  scene.invalidate();

  let disposed = false;
  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      offDraw();
      offChange();
      tiles.removeEventListener("load-model", onModel as never);
      tiles.removeEventListener("needs-render", onRender);
      tiles.removeEventListener("needs-update", onRender);
      tiles.removeEventListener("tiles-load-start", onStart);
      tiles.removeEventListener("tiles-load-end", onEnd);
      tiles.removeEventListener("load-error", onError as never);
      scene.keepDrawing("ring", false);
      scene.remove(group);
      tiles.dispose();
      scene.credits.remove(RING_CREDITS);
      state(null);
    },
  };
}
