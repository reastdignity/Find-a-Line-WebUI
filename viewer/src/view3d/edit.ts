// Moving the anchors (docs/3d-view-contract.md, "Wave 3", V3a), at level `full` only: a handle at each anchor,
// dragged over the terrain (a raycast on the scene's pickTargets with three-mesh-bvh), the anchor's height from
// the patch (over no data or off the patch it stays where it was); the webbing follows at once, neutral and
// "edited"; after a release the moved line's profile is asked for (interact.ts profileQueue: 300 ms, one request
// in flight, the newest wins). "Back to the found line" brings back the found anchors and their profile, kept
// from the start. Nothing is saved. The root's data-edit: "" (the found line), "moving", "waiting", "checked",
// "error".
// Round 2, point 3 ("Only valid lines", overlay.ts): the tool `valid` at level full; with it on, a dragged handle
// rests on the centre of the nearest valid sample near the pointer (and stays where it was when there is none),
// and the profile requests go through its lane (a reach request never runs beside one). `Edit.anchors` and
// `Edit.setAnchors` let other modules (the lines from a point, the several lines) read the line's anchors and set
// them as an edit; at the phone level they work too (a reset button appears at the first edit), the handles do not.

import { Vector3, type BufferGeometry, type Mesh } from "three";
import { acceleratedRaycast, computeBoundsTree, disposeBoundsTree } from "three-mesh-bvh";
import { t } from "../i18n";
import type { Profile } from "../types";
import { lineParam, profileQueue } from "./interact";
import type { Anchors, LineView } from "./line";
import { createValid, type Valid } from "./overlay";
import { currentPage, type PageRequest } from "./page";
import type { ReachGet } from "./reach";
import type { SceneCore } from "./scene";
import { draggable, overlayOf, place, pointerRay, toScreen } from "./screen";

export interface Edit {
  /** The found line's profile (or its error) once /api/profile answered: shown unless the anchors were moved. */
  found(profile: Profile | null, error?: string): void;
  /** The line's anchors now (copies). */
  anchors(): Anchors;
  /** Set the line's anchors from outside as an edit: the webbing neutral and "edited", the walk stopped, the
   *  profile of the new line asked for, the found anchors kept for "Back to the found line". False when the sag
   *  solver refuses them (nothing changed). `key`: the line's own key ("lat1,lon1,lat2,lon2") when it is a known
   *  line (a saved one, one handed over by the 2D result): the profile is asked for that key and `line.key`
   *  keeps it for saving and the links. */
  setAnchors(anchors: Anchors, key?: string | null): boolean;
}

export interface EditOptions {
  /** The page's own request (default: `currentPage()`); the reach asks for its run and line. */
  page?: PageRequest;
  /** The GET of /api/reach (tests; default: download.ts). */
  getReach?: ReachGet;
}

const copy = (a: Anchors): Anchors => [{...a[0]}, {...a[1]}];
const same = (a: {x: number; y: number}, b: {x: number; y: number}) => a.x === b.x && a.y === b.y;

/** The anchors' editing of `line`; `fetchProfile(line)` asks /api/profile for "lat1,lon1,lat2,lon2"; `onEdit`:
 *  an anchor is grabbed (the walk stops); `notes`: where the hint goes (before `before`, null: last). */
export function createEdit(scene: SceneCore, line: LineView, root: HTMLElement,
                           fetchProfile: (line: string) => Promise<Profile>, onEdit: () => void,
                           notes: {parent: HTMLElement; before: Element | null}, options: EditOptions = {}): Edit {
  const foundAnchors: Anchors = copy(line.anchors);
  let found: {profile: Profile | null; error?: string} | null = null, edited = false;
  const full = scene.level === "full";
  const state = (s: string) => { root.dataset.edit = s; };
  state("");

  // "Only valid lines": the lane puts the profile requests and the reach requests in turn
  const page = options.page ?? currentPage();
  let valid: Valid | null = null;
  const queue = profileQueue((key: string) => valid ? valid.guard(() => fetchProfile(key)) : fetchProfile(key), (outcome) => {
    valid?.hold(false);
    if (!edited) return;
    if ("value" in outcome) { line.setProfile(outcome.value); state("checked"); }
    else { line.setProfile(null, (outcome.error as Error)?.message || String(outcome.error)); state("error"); }
  });
  const cancelProfile = () => { queue.cancel(); valid?.hold(false); };
  const askProfile = () => {
    const [a, b] = line.anchors;
    valid?.hold(true);
    queue.push(line.key ?? lineParam(scene.lonLat(a.x, a.y), scene.lonLat(b.x, b.y)));
    state("waiting");
  };
  scene.onDispose(cancelProfile);

  let reset: HTMLButtonElement | null = null;
  const ensureReset = () => {
    if (reset) return reset;
    const button = reset = document.createElement("button");
    button.type = "button";
    button.className = "u-btn v3-reset v3-hidden";
    button.textContent = t("ui.view3d.reset");
    scene.toolbar.append(button);
    button.addEventListener("click", () => {
      cancelProfile();
      edited = false;
      button.classList.add("v3-hidden");
      line.setAnchors(foundAnchors, false);
      if (found) line.setProfile(found.profile, found.error);
      valid?.reset();
      state("");
    });
    return button;
  };

  const edit: Edit = {
    found(profile, error) {
      found = {profile, error};
      if (!edited) line.setProfile(profile, error);
    },
    anchors() { return copy(line.anchors); },
    setAnchors(anchors, key = null) {
      const before = copy(line.anchors), next = copy(anchors);
      cancelProfile();
      onEdit();
      if (!line.setAnchors(next, true, key)) return false;
      edited = true;
      ensureReset().classList.remove("v3-hidden");
      askProfile();
      for (const k of [0, 1] as const) if (!same(before[k], next[k])) valid?.moved(k);
      return true;
    },
  };
  if (!full) return edit;

  const hint = document.createElement("p");
  hint.className = "v3-note v3-hint";
  hint.textContent = t("ui.view3d.edit_hint");
  notes.parent.insertBefore(hint, notes.before);
  ensureReset();
  valid = createValid(scene, root, {
    page,
    // the found anchors are asked for exactly as the page's line gives them (the affine is a plane over the
    // projection: a few centimetres off at the patch's edge), a moved anchor through the affine
    anchorLonLat(k) {
      const a = line.anchors[k], n = (page.line || "").split(",").map(Number);
      if (n.length === 4 && n.every(Number.isFinite) && same(a, foundAnchors[k])) return k === 0 ? [n[1], n[0]] : [n[3], n[2]];
      return scene.lonLat(a.x, a.y);
    },
    get: options.getReach,
  }, notes);

  // The terrain's bounds trees, made at the first drag (a few hundred ms for the largest meshes)
  let picking = false;
  const pickable = () => {
    if (picking) return;
    picking = true;
    for (const target of scene.pickTargets) {
      const mesh = target as Mesh;
      computeBoundsTree.call(mesh.geometry as BufferGeometry);
      mesh.raycast = acceleratedRaycast;
    }
  };
  scene.onDispose(() => {
    if (picking) for (const target of scene.pickTargets) disposeBoundsTree.call((target as Mesh).geometry);
  });

  const handles = [0, 1].map((n) => {
    const k = n as 0 | 1;
    const handle = document.createElement("div");
    handle.className = "v3-handle";
    handle.setAttribute("aria-hidden", "true");
    handle.dataset.anchor = String(k + 1);
    overlayOf(scene).append(handle);
    let moved = false;
    draggable(scene, handle, {
      start() { pickable(); cancelProfile(); onEdit(); state("moving"); moved = false; valid!.grab(k); },
      move(x, y) {
        const {raycaster} = pointerRay(scene, x, y);
        const hit = raycaster.intersectObjects(scene.pickTargets, false)[0];
        if (!hit) return;
        const g = scene.fromScene(hit.point);
        // With "Only valid lines" on, the centre of the nearest valid sample near the hit (none near: the anchor
        // stays), while the reach of the anchor that stays is not in yet it moves freely
        const snapped = valid!.snap(k, g, hit.distance);
        if (snapped === null) return;
        const at = snapped === "free" ? g : snapped, h = scene.heightAt(at.x, at.y);
        if (h === null) return;
        if (same(at, line.anchors[k])) return;
        const next: Anchors = copy(line.anchors);
        next[k] = {x: at.x, y: at.y, h};
        if (!line.setAnchors(next, true)) return;
        edited = moved = true;
        reset!.classList.remove("v3-hidden");
      },
      end() {
        // a grab without a move still asks again: the grab cancelled the request of the last release
        if (!edited) { state(""); return; }
        askProfile();
        if (moved) valid!.moved(k);  // its reach is stale; asked once the profile is in
      },
    });
    return handle;
  });

  const at = new Vector3();
  scene.view.onDrawn(() => {
    line.anchors.forEach((a, k) => place(handles[k], toScreen(scene, at.copy(scene.toScene(a.x, a.y, a.h)))));
  });

  return edit;
}
