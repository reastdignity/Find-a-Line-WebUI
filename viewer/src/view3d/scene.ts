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
import { t } from "../i18n";
import { createActivity, createTools } from "./chrome";
import { DATA_CREDITS } from "./credits";
import type { Patch } from "./decode";
import { featureEdges, TERRAIN_LAYER, WALL_OPACITY } from "./edges";
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
  /** The elements of the activity pill, the tool strip and the card's slot (chrome.ts; round 2). */
  activity: HTMLElement;
  tools: HTMLElement;
  card: HTMLElement;
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

/** Where the user's last choice of the data credits (open or folded) is kept in the browser, and the width from
 *  which they start open (ui.css folds them under it on the 2D result). */
export const CREDITS_KEY = "findaline.view3d.credits";
export const CREDITS_WIDE_PX = 768;

/** Whether the data credits start open: the stored choice ("open" or "folded") if there is one, else open on a
 *  wide screen and folded on a narrow one. */
export function creditsStartOpen(stored: string | null, wide: boolean): boolean {
  return stored === "open" ? true : stored === "folded" ? false : wide;
}

type Store = Pick<Storage, "getItem" | "setItem">;

/** The browser's local storage, null where it is not there (the page is right without it). */
function browserStore(): Store | null {
  try { return window.localStorage; } catch { return null; }
}

function wideScreen(): boolean {
  try { return matchMedia(`(min-width: ${CREDITS_WIDE_PX}px)`).matches; } catch { return false; }
}

/** The credits box: entries sorted by their order, hidden while empty. The run's data credits (DATA_CREDITS) fold
 *  behind a "Data credits" button at every width (the 2D map's button, layers.ts creditsHtml, ui.css .u-credits;
 *  view3d.css shows it above 768 px too), open at the start from 768 px up and folded under it, then as the user
 *  last left them (`store`, try/catch: the page is right without it; unfolded it stays so when the entries
 *  change); the imagery's and the ring's credits never fold. */
export function creditsBox(box: HTMLElement, store: Store | null = browserStore(), wide: () => boolean = wideScreen):
    Credits {
  const entries = new Map<string, {html: string; order: number}>();
  let stored: string | null = null;
  try { stored = store?.getItem(CREDITS_KEY) ?? null; } catch { /* storage refused: the default */ }
  let open = creditsStartOpen(stored, wide());
  const label = t("ui.credits.toggle").replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
  const render = () => {
    const list = [...entries.entries()].sort((a, b) => a[1].order - b[1].order);
    box.innerHTML = list.map(([id, e]) => id !== DATA_CREDITS ? `<span class="v3-credit">${e.html}</span>`
      : `<span class="v3-credit"><button type="button" class="u-credits-toggle" aria-expanded="${open}">${label}` +
        `</button><span class="u-credits${open ? " u-open" : ""}">${e.html}</span></span>`).join(" ");  // trusted HTML only
    box.classList.toggle("v3-hidden", !list.length);
  };
  box.addEventListener("click", (e) => {
    if (!(e.target as HTMLElement).closest?.(".u-credits-toggle")) return;
    open = !open;
    try { store?.setItem(CREDITS_KEY, open ? "open" : "folded"); } catch { /* not kept */ }
    render();
    box.querySelector<HTMLElement>(".u-credits-toggle")?.focus();  // the new button
  });
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
    setTexture(texture: Texture | null, uv?: (x: number, y: number) => [number, number], lit = false) {
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
        mesh.material = own = lit ? new MeshLambertMaterial({map: texture, side: DoubleSide})
                                  : new MeshBasicMaterial({map: texture, side: DoubleSide});
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

/** The feature edges of the Edges look, one pixel wide: each vertex pulled towards the camera by FEATURE_PULL of its
 *  distance (no depth fight with the faces it lies on), the lines fading out between FEATURE_FADE[0] and [1] metres,
 *  where their segments are shorter than a pixel and shimmer as the camera turns. */
export const FEATURE_PULL = 0.002;
export const FEATURE_FADE: [number, number] = [400, 1200];

function featureLines(colour: string, opacity = 1): LineBasicMaterial {
  const material = new LineBasicMaterial({color: colour, transparent: true, depthWrite: false, opacity});
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = "varying float vFalDistance;\n" + shader.vertexShader.replace("#include <project_vertex>",
      `#include <project_vertex>
      mvPosition.xyz *= ${(1 - FEATURE_PULL).toFixed(6)};
      gl_Position = projectionMatrix * mvPosition;
      vFalDistance = -mvPosition.z;`);
    shader.fragmentShader = "varying float vFalDistance;\n" + shader.fragmentShader.replace("#include <opaque_fragment>",
      `#include <opaque_fragment>
      gl_FragColor.a *= 1.0 - smoothstep(${FEATURE_FADE[0].toFixed(1)}, ${FEATURE_FADE[1].toFixed(1)}, vFalDistance);`);
  };
  return material;
}

/** The overlay's polygon offset (toward the camera, so that it wins the depth test against the surface it lies on). */
export const OVERLAY_OFFSET = -2;

/** The overlay of round 2 (`Scene3D.setOverlay`): one half-transparent picture over the whole terrain, drawn by a
 *  second mesh on each chunk that shares the chunk's positions and index (the surface's triangles only: the draw
 *  range stops before the skirts) and has a UV attribute of its own. The meshes are children of the chunks on the
 *  default layer alone: the edges' pass (terrain layer only) never draws them, and they are not in `pickTargets`.
 *  The meshes and their UVs are made at the first picture and kept (the chunks' buffers they share must not be
 *  released with a geometry of theirs); a picture taken away frees the texture and hides them. */
export function createOverlay(terrain: Terrain, chunks: Chunk[], invalidate: () => void) {
  let parts: {mesh: Mesh; uv: BufferAttribute; grid: Float64Array; count: number}[] | null = null;
  let material: MeshBasicMaterial | null = null, held: Texture | null = null;
  const release = () => { held?.dispose(); held = null; };
  return {
    set(texture: Texture | null, uv?: (x: number, y: number) => [number, number]) {
      release();
      if (!texture || !uv) {
        if (parts) for (const p of parts) p.mesh.visible = false;
        if (material) material.map = null;
        invalidate();
        return;
      }
      held = texture;
      if (!material) {
        material = new MeshBasicMaterial({map: texture, transparent: true, depthWrite: false, side: DoubleSide,
                                          polygonOffset: true, polygonOffsetFactor: OVERLAY_OFFSET,
                                          polygonOffsetUnits: OVERLAY_OFFSET});
      }
      material.map = texture;
      material.needsUpdate = true;
      if (!parts) {
        parts = terrain.chunks.map((m, k) => {
          const source = chunks[k].mesh.geometry, geometry = new BufferGeometry();
          const attribute = new Float32BufferAttribute(new Float32Array(2 * m.surfaceVertices), 2);
          geometry.setAttribute("position", source.getAttribute("position"));
          geometry.setAttribute("uv", attribute);
          geometry.setIndex(source.getIndex());
          geometry.setDrawRange(0, m.surfaceIndices);
          geometry.boundingSphere = source.boundingSphere?.clone() ?? null;
          const mesh = new Mesh(geometry, material!);
          mesh.name = `reach-${m.ci}-${m.cj}`;
          mesh.raycast = () => {};  // never a pick target
          chunks[k].mesh.add(mesh);
          return {mesh, uv: attribute, grid: m.grid, count: m.surfaceVertices};
        });
      }
      for (const p of parts) {
        const array = p.uv.array as Float32Array;
        for (let v = 0; v < p.count; v++) {
          const [u, w] = uv(p.grid[2 * v], p.grid[2 * v + 1]);
          array[2 * v] = u;
          array[2 * v + 1] = w;
        }
        p.uv.needsUpdate = true;
        p.mesh.visible = true;
      }
      invalidate();
    },
    dispose() {
      release();
      if (parts) for (const p of parts) { p.mesh.removeFromParent(); p.mesh.geometry.dispose(); }
      parts = null;
      material?.dispose();
      material = null;
    },
  };
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
  // feature edges on it are never hidden by their own faces) and the feature edges of each chunk's surface, those
  // between two faces of a wall lighter (WALL_OPACITY)
  let paper: MeshLambertMaterial | null = null, featureMaterial: LineBasicMaterial | null = null, edges = false;
  let wallMaterial: LineBasicMaterial | null = null;
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
      featureMaterial = featureLines(token("--muted"));
      wallMaterial = featureLines(token("--muted"), WALL_OPACITY);
      terrain.chunks.forEach((m, k) => {
        for (const [walls, material] of [["out", featureMaterial!], ["only", wallMaterial!]] as const) {
          const geometry = new BufferGeometry();
          geometry.setAttribute("position",
                                new BufferAttribute(featureEdges(m.positions, m.indices, m.surfaceIndices, undefined, walls), 3));
          geometry.computeBoundingSphere();
          const lines = new LineSegments(geometry, material);
          lines.name = `edges-${walls === "only" ? "walls" : "terrain"}-${m.ci}-${m.cj}`;
          chunks[k].mesh.add(lines);
          features.push(lines);
        }
      });
    }
    for (const lines of features) lines.visible = on;
    for (const c of chunks) {  // a chunk without its texture takes the base material of the look
      if (c.mesh.material === shaded || c.mesh.material === paper) c.mesh.material = base();
    }
    view.setEdges(on ? token("--ink") : null);
    if (page) { if (on) page.dataset.edges = "on"; else delete page.dataset.edges; }
  };

  const overlay = createOverlay(terrain, chunks, view.invalidate);
  const scene: SceneCore = {
    level, patch, meta: patch.meta, origin, chunks, view, terrain, token, stage: parts.stage,
    pickTargets: chunks.map((c) => c.mesh),
    credits: creditsBox(parts.credits),
    toolbar: parts.toolbar,
    activity: createActivity(parts.activity),
    tools: createTools(parts.tools),
    card: parts.card,
    setOverlay(texture, uv) { if (!disposed) overlay.set(texture, uv); },
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
      overlay.dispose();
      for (const c of chunks) {
        c.setTexture(null);
        c.mesh.geometry.dispose();
      }
      for (const lines of features) lines.geometry.dispose();
      featureMaterial?.dispose();
      wallMaterial?.dispose();
      paper?.dispose();
      shaded.dispose();
      if (page) delete page.dataset.edges;
      view.dispose();
    },
  };
  view.invalidate();
  return scene;
}
