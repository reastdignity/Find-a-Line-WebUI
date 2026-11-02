// The scene core of the 3D view (docs/3d-view-contract.md, "Wave 2", V2a): every chunk of the patch's terrain
// (terrain.ts) as a mesh, shaded or textured through `Chunk.setTexture`, the view drawn on demand (view.ts), the
// camera across the found line, the credits box and the toolbar's row. Implements scene-api.ts' Scene3D for the
// imagery and the later waves; the webbing and the walker are line.ts'. The "Edges" look (`setEdges`, wave E):
// the chunks on paper (`--paper`, lit as the shaded terrain) with the mesh's feature edges in `--muted` (made the
// first time the look is chosen, hidden in the other kinds) and view.ts' edges' pass in `--ink`; the root gets
// data-edges="on" while it is on (for tests).

import {
  BufferAttribute, BufferGeometry, DoubleSide, Float32BufferAttribute, LineBasicMaterial, LineSegments, Mesh,
  MeshBasicMaterial, MeshLambertMaterial, Vector3, type Material, type Object3D, type Texture,
} from "three";
import type { Patch } from "./decode";
import { featureEdges, TERRAIN_LAYER } from "./edges";
import { lonLat, originOf, toScene, type Origin } from "./geometry";
import type { Level } from "./page";
import type { Chunk, Credits, GridBounds, Scene3D } from "./scene-api";
import { buildTerrain, type ChunkMesh, type Terrain } from "./terrain";
import { createView, type View } from "./view";
import { CHUNK } from "./decode";

/** Martini's error asked per level (metres; raised until the meshes fit the budget) and the vertex budget. */
export const MAX_ERROR = {full: 0.25, phone: 1.5};
export const VERTEX_BUDGET = {full: 300_000, phone: 130_000};

export interface SceneParts {
  stage: HTMLElement;
  toolbar: HTMLElement;
  credits: HTMLElement;
}

export interface SceneCore extends Scene3D {
  view: View;
  /** The stage holding the canvas: DOM overlays (handles, the pin) go here. */
  stage: HTMLElement;
  terrain: Terrain;
  /** The colour tokens of the page (e.g. "--clear"), read from the .ui root. */
  token(name: string): string;
  /** Called on the page's `pagehide`: everything freed. */
  dispose(): void;
  /** Run `fn` when disposing. */
  onDispose(fn: () => void): void;
}

/** The credits box: entries sorted by their order, hidden while empty. */
function creditsBox(box: HTMLElement): Credits {
  const entries = new Map<string, {html: string; order: number}>();
  const render = () => {
    const list = [...entries.values()].sort((a, b) => a.order - b.order);
    box.innerHTML = list.map((e) => `<span class="v3-credit">${e.html}</span>`).join(" ");  // trusted HTML only
    box.classList.toggle("v3-hidden", !list.length);
  };
  render();
  return {
    set(id, html, order = 0) { entries.set(id, {html, order}); render(); },
    remove(id) { entries.delete(id); render(); },
  };
}

/** A chunk's mesh; `base()`: its material without a texture (shaded, or the paper of the "Edges" look). */
function chunkOf(m: ChunkMesh, patch: Patch, base: () => Material, invalidate: () => void): Chunk {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(m.positions, 3));
  geometry.setAttribute("normal", new BufferAttribute(m.normals, 3));
  geometry.setIndex(new BufferAttribute(m.indices, 1));
  geometry.computeBoundingSphere();
  const mesh = new Mesh(geometry, base());
  mesh.layers.enable(TERRAIN_LAYER);  // the edges' pass draws the terrain alone
  mesh.name = `chunk-${m.ci}-${m.cj}`;
  const {left, top, res} = patch.meta, i0 = m.ci * CHUNK, j0 = m.cj * CHUNK;
  const bounds: GridBounds = {x0: left + j0 * res, x1: left + (j0 + CHUNK + 1) * res,
                              y0: top - (i0 + CHUNK + 1) * res, y1: top - i0 * res};
  let own: Material | null = null;
  return {
    ci: m.ci, cj: m.cj, mesh, bounds, hasLine: m.hasLine,
    setTexture(texture: Texture | null, uv?: (x: number, y: number) => [number, number]) {
      if (own) { own.dispose(); own = null; }
      if (!texture || !uv) {
        mesh.material = base();
        if (geometry.getAttribute("uv")) geometry.deleteAttribute("uv");
      } else {
        const n = m.grid.length / 2, uvs = new Float32Array(2 * n);
        for (let v = 0; v < n; v++) {
          const [u, w] = uv(m.grid[2 * v], m.grid[2 * v + 1]);
          uvs[2 * v] = u; uvs[2 * v + 1] = w;
        }
        geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
        mesh.material = own = new MeshBasicMaterial({map: texture, side: DoubleSide});
      }
      invalidate();
    },
  };
}

/** The patch's height at grid metres, bilinear between samples; null over no data or outside. */
export function heightAt(patch: Patch, x: number, y: number): number | null {
  const {left, top, res, width, height} = patch.meta;
  const u = (x - left) / res - 0.5, v = (top - y) / res - 0.5;
  if (!(u >= 0 && v >= 0 && u <= width - 1 && v <= height - 1)) return null;
  const j = Math.min(width - 2, Math.floor(u)), i = Math.min(height - 2, Math.floor(v)), a = u - j, b = v - i;
  const h = (r: number, c: number) => patch.heights[r * patch.cols + c];
  const value = (h(i, j) * (1 - a) + h(i, j + 1) * a) * (1 - b) + (h(i + 1, j) * (1 - a) + h(i + 1, j + 1) * a) * b;
  return Number.isNaN(value) ? null : value;
}

/** An oblique view across the line from its lower side, framing it. */
function lookAcross(view: View, patch: Patch, origin: Origin) {
  const [a, b] = patch.meta.anchors, span = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, mh = (a.h + b.h) / 2;
  const nx = -(b.y - a.y) / span, ny = (b.x - a.x) / span;  // across the line in grid metres
  // far enough that the line fits the view's width with a margin (a phone held upright is narrow): the camera
  // stands hypot(0.85, 0.45) · dist from the line's middle
  const across = 2 * Math.hypot(0.85, 0.45) * Math.tan(view.camera.fov * Math.PI / 360) * view.camera.aspect;
  const dist = Math.max(60, span * 1.25, span * 1.15 / across);
  const lower = (side: number) => heightAt(patch, mx + side * nx * dist * 0.5, my + side * ny * dist * 0.5) ?? Infinity;
  const side = lower(1) <= lower(-1) ? 1 : -1;
  const target = new Vector3(...toScene(origin, mx, my, mh - span * 0.05));
  const from = new Vector3(...toScene(origin, mx + side * nx * dist * 0.85, my + side * ny * dist * 0.85,
                                      mh + dist * 0.45));
  const {width, height, res} = patch.meta;
  view.look(from, target, Math.max(width, height) * res * 1.5);
}

/** The scene of a decoded patch in `parts.stage`; throws when the browser has no WebGL 2. */
export function createScene(patch: Patch, level: Level, parts: SceneParts, onLost: () => void): SceneCore {
  const root = parts.stage.closest(".ui") || document.documentElement;
  const style = getComputedStyle(root);
  const token = (name: string) => style.getPropertyValue(name).trim() || "#888888";
  const view = createView(parts.stage, level, token("--map-bg"), onLost);
  const origin = originOf(patch.meta);
  const terrain = buildTerrain(patch, origin, MAX_ERROR[level], VERTEX_BUDGET[level]);
  const shaded = new MeshLambertMaterial({color: token("--terrain"), side: DoubleSide});
  // The "Edges" look's parts, made the first time it is chosen: the paper (pushed back a little in depth, so the
  // feature edges on it are never hidden by their own faces) and the feature edges of each chunk's surface
  let paper: MeshLambertMaterial | null = null, featureMaterial: LineBasicMaterial | null = null, edges = false;
  const features: LineSegments[] = [];
  const base = () => (edges && paper) || shaded;
  const chunks = terrain.chunks.map((m) => chunkOf(m, patch, base, view.invalidate));
  for (const c of chunks) view.scene.add(c.mesh);
  lookAcross(view, patch, origin);
  const disposers: (() => void)[] = [];
  let disposed = false;
  const page = parts.stage.closest<HTMLElement>(".ui");
  const setEdges = (on: boolean) => {
    if (disposed || (on && !view.edgesSupported) || on === edges) return;
    edges = on;
    if (on && !paper) {
      paper = new MeshLambertMaterial({color: token("--paper"), side: DoubleSide, polygonOffset: true,
                                       polygonOffsetFactor: 1, polygonOffsetUnits: 1});
      featureMaterial = new LineBasicMaterial({color: token("--muted")});
      terrain.chunks.forEach((m, k) => {
        const geometry = new BufferGeometry();
        geometry.setAttribute("position", new BufferAttribute(featureEdges(m.positions, m.indices, m.surfaceIndices), 3));
        geometry.computeBoundingSphere();
        const lines = new LineSegments(geometry, featureMaterial!);
        lines.name = `edges-${m.ci}-${m.cj}`;
        chunks[k].mesh.add(lines);
        features.push(lines);
      });
    }
    for (const lines of features) lines.visible = on;
    for (const c of chunks) {  // a chunk without its texture takes the base material of the look
      if (c.mesh.material === shaded || c.mesh.material === paper) c.mesh.material = base();
    }
    view.setEdges(on ? token("--ink") : null);
    if (page) { if (on) page.dataset.edges = "on"; else delete page.dataset.edges; }
  };

  const scene: SceneCore = {
    level, patch, meta: patch.meta, origin, chunks, view, terrain, token, stage: parts.stage,
    pickTargets: chunks.map((c) => c.mesh),
    credits: creditsBox(parts.credits),
    toolbar: parts.toolbar,
    invalidate: view.invalidate,
    onFrame: view.onFrame,
    beforeDraw: view.beforeDraw,
    keepDrawing: view.keepDrawing,
    camera: view.camera,
    renderer: view.renderer,
    add(object: Object3D) { view.add(object); },
    remove(object: Object3D) { view.remove(object); },
    toScene(x, y, h) { return new Vector3(...toScene(origin, x, y, h)); },
    fromScene(v) { return {x: v.x + origin.cx, y: origin.cy - v.z, h: v.y + origin.h0}; },
    heightAt(x, y) { return heightAt(patch, x, y); },
    lonLat(x, y) { return lonLat(patch.meta.affine, x, y); },
    edgesSupported: view.edgesSupported,
    setEdges,
    edgesOn() { return edges; },
    terrainLayer: TERRAIN_LAYER,
    paper: token("--paper"),
    onDispose(fn) { disposers.push(fn); },
    dispose() {
      if (disposed) return;
      disposed = true;
      for (const fn of disposers.splice(0).reverse()) {
        try { fn(); } catch (e) { console.error(e); }
      }
      for (const c of chunks) {
        c.setTexture(null);
        c.mesh.geometry.dispose();
      }
      for (const lines of features) lines.geometry.dispose();
      featureMaterial?.dispose();
      paper?.dispose();
      shaded.dispose();
      if (page) delete page.dataset.edges;
      view.dispose();
    },
  };
  view.invalidate();
  return scene;
}
