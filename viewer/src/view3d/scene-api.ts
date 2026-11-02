// The scene's API between the modules of the 3D view (docs/3d-view-contract.md, "Wave 2" and "Wave 3"): the
// scene core (scene.ts) implements it; the imagery (imagery.ts), the editing and the walk (wave 3a) and the ring
// (wave 3b) use it. Types only.

import type { Mesh, Object3D, PerspectiveCamera, Texture, Vector3, WebGLRenderer } from "three";
import type { Patch, PatchMeta } from "./decode";
import type { Origin } from "./geometry";
import type { Level } from "./page";

/** Grid metres in the run's CRS: x east, y north. */
export interface GridBounds { x0: number; y0: number; x1: number; y1: number }

/** One chunk of the terrain as drawn. */
export interface Chunk {
  /** Its row and column among the chunks. */
  ci: number;
  cj: number;
  /** In the scene; its material takes the texture of `setTexture`. */
  mesh: Mesh;
  /** Its extent: the outer edges of its samples (x0 west, x1 east, y0 south, y1 north). */
  bounds: GridBounds;
  /** The found line crosses it: imagery takes a finer zoom here. */
  hasLine: boolean;
  /** An image on the chunk (null: shaded); `uv` maps grid metres to the texture's (u, v) in [0, 1]. */
  setTexture(texture: Texture | null, uv?: (x: number, y: number) => [number, number]): void;
}

/** The credits box of the page: entries in `order`, low first. Trusted HTML only (built from our strings). */
export interface Credits {
  set(id: string, html: string, order?: number): void;
  remove(id: string): void;
}

export interface Scene3D {
  level: Level;
  patch: Patch;
  meta: PatchMeta;
  origin: Origin;
  chunks: Chunk[];
  /** Meshes for picking on the terrain (raycasts of wave 3a). */
  pickTargets: Object3D[];
  credits: Credits;
  /** A row of the page's toolbar for a module's controls (the imagery's, the walker's). */
  toolbar: HTMLElement;
  /** Draw one frame soon (the scene draws on demand only). */
  invalidate(): void;
  /** Called before every frame drawn while an owner keeps drawing (`keepDrawing`) with the seconds since the
   *  frame before (0 on the first); returns the unsubscribe. */
  onFrame(fn: (seconds: number) => void): () => void;
  /** Called before every frame drawn, on demand or not (after the `onFrame` callbacks): e.g. a level of detail
   *  following the camera; returns the unsubscribe. */
  beforeDraw(fn: () => void): () => void;
  keepDrawing(owner: string, on: boolean): void;
  /** The camera and renderer, read-only for the modules: they never move the camera or resize the renderer. */
  camera: PerspectiveCamera;
  renderer: WebGLRenderer;
  add(object: Object3D): void;
  remove(object: Object3D): void;
  toScene(x: number, y: number, h: number): Vector3;
  fromScene(v: Vector3): { x: number; y: number; h: number };
  /** The patch's height at grid metres (bilinear between samples), null over no data or outside the patch. */
  heightAt(x: number, y: number): number | null;
  /** Grid metres to lon/lat through the meta's affine. */
  lonLat(x: number, y: number): [number, number];
}
