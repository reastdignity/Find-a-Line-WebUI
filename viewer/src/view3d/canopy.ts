// The trees and buildings of the 3D view (docs/3d-view-contract.md, "Round 2", decision 8 and "V, the canopy"):
// the tool "Trees and buildings", a switch offered only when the patch's meta says the run has a surface model
// (`meta.surface`). Switched on it asks the block of the run's obstacle surface less the terrain once
// (GET /api/patch?part=canopy, the patch's request with the same header; the activity "trees" meanwhile), checks
// and keeps it for the page's life, and draws it as a half-transparent lit mesh in `--tree-fill` (canopymesh.ts:
// a lattice of cells of about 2 m, 4 m at the phone level, made coarser until it fits the vertex budget).
// Switched off the mesh is only hidden, so switching it on again asks nothing. A failure shows
// `ui.view3d.trees_failed` under the toolbar and the switch goes off.
//
// Drawing: two passes of one geometry, both after every other transparent object (renderOrder): a depth-only
// pass (no colour, pushed back a little) and the colour pass above it without writing depth. So only the
// nearest face of the canopy shows (no double veil where a wood's far side lies behind its near side, whatever
// the order of the triangles), the opaque webbing and the walker are drawn before the canopy and show tinted
// through it, and nothing is hidden by it. Layer 0 only: the edges' pass (the terrain layer) ignores it, and it
// is never among `pickTargets`.
// The root gets data-trees ("off" | "loading" | "on" | "failed"), data-trees-triangles, -vertices and -cell
// (the lattice's side, metres) for tests.

import {
  BufferAttribute, BufferGeometry, FrontSide, Group, Mesh, MeshBasicMaterial, MeshLambertMaterial,
} from "three";
import { download } from "../download";
import { detailMessage, t } from "../i18n";
import {
  buildMesh, CANOPY_BUDGET, CELL_METRES, chooseLattice, decodeCanopy, minValue, samplesPerCell, sameGrid,
  type CanopyData, type CanopyMesh,
} from "./canopymesh";
import type { PatchMeta } from "./decode";
import { currentPage, patchUrl, type PageRequest } from "./page";
import { MAX_ERROR, type SceneCore } from "./scene";

/** What the contract adds to the patch's meta (the coordinator adds it to `PatchMeta`): the run has a surface model. */
export type SurfaceMeta = PatchMeta & {surface?: boolean};

/** The tool's icon: a crown over a trunk, in a 16 × 16 box. */
export const TREE_ICON = "M8 1.5 12.5 8.5h-9z M8 8.5v6 M5.5 14.5h5";
/** The colour pass's opacity. */
export const OPACITY = 0.7;
/** Draw orders: after the lines (0 to 2) and the other transparent objects. */
export const DEPTH_ORDER = 3, COLOUR_ORDER = 4;

export interface CanopyOptions {
  /** The page's request (default: `currentPage()`). */
  page?: PageRequest;
  /** The address of the block (default: `patchUrl(page)` with `&part=canopy`). */
  url?: string;
}

export interface Canopy {
  /** Switch the canopy on or off (the tool's button does the same). */
  set(on: boolean): void;
  dispose(): void;
}

/** The block's address: the patch's with `part=canopy`. */
export function canopyUrl(page: PageRequest): string {
  return patchUrl(page) + "&part=canopy";
}

class Failure extends Error {}

/** Ask the block and decode it; throws Failure with the text to show. */
async function fetchCanopy(url: string): Promise<CanopyData> {
  let answer;
  try {
    answer = await download(url, "arraybuffer", {headers: {"X-Findaline-Patch": "1"}});
  } catch (e) {
    throw new Failure((e as Error).message);
  }
  if (answer.status !== 200) {
    let data: {detail?: unknown} = {};
    try { data = JSON.parse(new TextDecoder().decode(answer.body)); } catch { /* not JSON */ }
    throw new Failure(detailMessage(data.detail, String(answer.status)));
  }
  try {
    return await decodeCanopy(answer.body);
  } catch (e) {
    throw new Failure((e as Error).message);
  }
}

/** The tool "Trees and buildings" in `scene`'s strip, or null when the run has no surface model (no tool, nothing
 *  else). Call it once the terrain is drawn, from `main.ts`. */
export function createCanopy(scene: SceneCore, options: CanopyOptions = {}): Canopy | null {
  const meta = scene.meta as SurfaceMeta;
  if (!meta.surface) return null;
  const page = options.page ?? currentPage(), url = options.url ?? canopyUrl(page);
  const root = scene.stage.closest<HTMLElement>(".ui") ?? document.documentElement;
  const note = document.createElement("p");
  note.className = "v3-note v3-hidden";
  note.setAttribute("role", "alert");
  scene.toolbar.insertAdjacentElement("afterend", note);

  let data: CanopyData | null = null, group: Group | null = null, wanted = false, asking = false, disposed = false;
  const geometries: BufferGeometry[] = [], materials: (MeshBasicMaterial | MeshLambertMaterial)[] = [];
  const state = (name: "off" | "loading" | "on" | "failed") => { root.dataset.trees = name; };
  state("off");

  const button = scene.tools.add({
    id: "trees", label: t("ui.view3d.trees"), icon: TREE_ICON, order: 3, toggle: true,
    onClick: () => set(!wanted),
  });

  /** The meshes of the answer (made once, the first time they are shown). */
  function build(canopy: CanopyData): Group {
    const patch = scene.patch;
    if (!sameGrid(canopy.meta, meta)) throw new Failure(t("error.patch_damaged"));
    const min = minValue(canopy.meta);
    const lat = chooseLattice(canopy.values, meta.width, meta.height, samplesPerCell(CELL_METRES[scene.level], meta.res),
                              min, CANOPY_BUDGET[scene.level]);
    const mesh: CanopyMesh = buildMesh({...meta, heights: patch.heights, cols: patch.cols}, lat, scene.origin,
                                       canopy.meta.quantum, MAX_ERROR[scene.level] + 0.1);
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(mesh.positions, 3));
    geometry.setAttribute("normal", new BufferAttribute(mesh.normals, 3));
    geometry.setIndex(new BufferAttribute(mesh.indices, 1));
    geometry.computeBoundingSphere();
    geometries.push(geometry);
    // The depth pass (no colour; pushed back so the colour pass, which draws the same triangles, passes its test)
    // and the colour pass (lit, half transparent, no depth written)
    const depth = new MeshBasicMaterial({colorWrite: false, transparent: true, depthWrite: true,
                                         polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1});
    const colour = new MeshLambertMaterial({color: scene.token("--tree-fill"), transparent: true, opacity: OPACITY,
                                            depthWrite: false, side: FrontSide});
    materials.push(depth, colour);
    const behind = new Mesh(geometry, depth), over = new Mesh(geometry, colour);
    behind.renderOrder = DEPTH_ORDER;
    over.renderOrder = COLOUR_ORDER;
    behind.name = "canopy-depth";
    over.name = "canopy";
    const built = new Group();
    built.name = "canopy";
    built.add(behind, over);
    root.dataset.treesTriangles = String(mesh.triangles);
    root.dataset.treesVertices = String(mesh.vertices);
    root.dataset.treesCell = String(lat.k * meta.res);
    return built;
  }

  function show(on: boolean) {
    if (disposed) return;
    if (on && data && !group) {
      try {
        group = build(data);
        scene.add(group);
      } catch (e) {
        fail(e instanceof Failure ? e.message : (e as Error).message);
        return;
      }
    }
    if (group) { group.visible = on; scene.invalidate(); }
    state(on ? "on" : "off");
  }

  function fail(message: string) {
    wanted = false;
    button.setPressed(false);
    note.textContent = t("ui.view3d.trees_failed", {message});
    note.classList.remove("v3-hidden");
    show(false);
    state("failed");
  }

  async function load() {
    asking = true;
    state("loading");
    scene.activity.set("trees", t("ui.view3d.activity_trees"));
    try {
      data = await fetchCanopy(url);
    } catch (e) {
      asking = false;
      scene.activity.clear("trees");
      if (!disposed) fail((e as Error).message);
      return;
    }
    asking = false;
    scene.activity.clear("trees");
    if (!disposed && wanted) show(true);  // switched off while it loaded: kept, not drawn
    else if (!disposed) state("off");
  }

  function set(on: boolean) {
    if (disposed || on === wanted) return;
    wanted = on;
    button.setPressed(on);
    if (on) note.classList.add("v3-hidden");
    if (on && !data) { if (!asking) void load(); return; }
    if (!asking) show(on);
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    if (group) scene.remove(group);
    group = null;
    for (const g of geometries.splice(0)) g.dispose();
    for (const m of materials.splice(0)) m.dispose();
    data = null;
    scene.activity.clear("trees");
    button.remove();
    note.remove();
    delete root.dataset.trees;
  }
  scene.onDispose(dispose);
  return {set, dispose};
}
