// The scene's API between the modules of the 3D view (docs/3d-view-contract.md, "Wave 2", "Wave 3" and "Wave E"):
// the scene core (scene.ts) implements it; the imagery (imagery.ts), the editing and the walk (wave 3a) and the
// ring (wave 3b) use it. Types only.

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
  /** `lit`: the texture multiplies the shaded terrain (MeshLambertMaterial: the hatching of the uncertain
   *  shore on the Shaded look) instead of replacing it as imagery does (MeshBasicMaterial). */
  setTexture(texture: Texture | null, uv?: (x: number, y: number) => [number, number], lit?: boolean): void;
}

/** The credits box of the page: entries in `order`, low first. Trusted HTML only (built from our strings). */
export interface Credits {
  set(id: string, html: string, order?: number): void;
  remove(id: string): void;
}

/** The activity pill over the stage (round 2): what the page is loading or computing right now, with a spinner.
 *  The entry added last shows (setting an entry again changes it in place: the imagery's count never hides a
 *  wait that began after it); `fraction` (0 to 1) adds a small bar, null none. Hidden without an entry. */
export interface Activity {
  set(id: string, text: string, fraction?: number | null): void;
  clear(id: string): void;
}

/** A button of the tool strip over the stage (round 2). */
export interface ToolSpec {
  /** The button's `data-tool` (for tests). */
  id: string;
  label: string;
  /** The `d` of a path in a 16 × 16 box, drawn as a line in the text's colour. */
  icon: string;
  /** Its place in the strip, low first (docs/3d-view-contract.md, "Round 2": the tools' order). */
  order: number;
  /** A switch (`aria-pressed`, `setPressed`) and not an action. */
  toggle?: boolean;
  onClick(): void;
}

export interface ToolButton {
  element: HTMLButtonElement;
  setPressed(on: boolean): void;
  setLabel(text: string): void;
  setIcon(d: string): void;
  remove(): void;
}

/** The tool strip over the stage: the controls of round 2 (the bar below keeps the walker, the imagery, the views). */
export interface Tools {
  add(spec: ToolSpec): ToolButton;
}

export interface Scene3D {
  level: Level;
  activity: Activity;
  tools: Tools;
  /** The slot of the card over the stage's bottom (the profile's): it lies on the canvas, which keeps its size. */
  card: HTMLElement;
  /** A half-transparent picture over the whole terrain (round 2: the reach of an anchor); `uv` maps grid metres
   *  to its (u, v) in [0, 1]; null takes it away. Never drawn in the edges' pass, never a pick target. */
  setOverlay(texture: Texture | null, uv?: (x: number, y: number) => [number, number]): void;
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
  /** The "Edges" look (wave E): the browser can draw it (the imagery offers it only then). */
  edgesSupported: boolean;
  /** The look on (the chunks on paper with the mesh's feature edges, the edges' pass) or off (back to the
   *  chunks' textures or shading, the feature edges hidden, the pass freed). The imagery calls it. */
  setEdges(on: boolean): void;
  /** The look is on. */
  edgesOn(): boolean;
  /** The layer of the terrain's meshes: the edges' pass draws it alone, so a mesh of terrain (the ring's tiles)
   *  enables it; nothing else may. */
  terrainLayer: number;
  /** The paper's colour of the look (the page's `--paper`): the ring's tiles take it while the look is on. */
  paper: string;
}
