// Moving the anchors (docs/3d-view-contract.md, "Wave 3", V3a), at level `full` only: a handle at each anchor,
// dragged over the terrain (a raycast on the scene's pickTargets with three-mesh-bvh), the anchor's height from
// the patch (over no data or off the patch it stays where it was); the webbing follows at once, neutral and
// "edited"; after a release the moved line's profile is asked for (interact.ts profileQueue: 300 ms, one request
// in flight, the newest wins). "Back to the found line" brings back the found anchors and their profile, kept
// from the start. Nothing is saved. The root's data-edit: "" (the found line), "moving", "waiting", "checked",
// "error".

import { Vector3, type BufferGeometry, type Mesh } from "three";
import { acceleratedRaycast, computeBoundsTree, disposeBoundsTree } from "three-mesh-bvh";
import { t } from "../i18n";
import type { Profile } from "../types";
import { lineParam, profileQueue } from "./interact";
import type { Anchors, LineView } from "./line";
import type { SceneCore } from "./scene";
import { draggable, overlayOf, place, pointerRay, toScreen } from "./screen";

export interface Edit {
  /** The found line's profile (or its error) once /api/profile answered: shown unless the anchors were moved. */
  found(profile: Profile | null, error?: string): void;
}

/** The anchors' editing of `line`; `fetchProfile(line)` asks /api/profile for "lat1,lon1,lat2,lon2"; `onEdit`:
 *  an anchor is grabbed (the walk stops); `notes`: where the hint goes (before `before`, null: last). */
export function createEdit(scene: SceneCore, line: LineView, root: HTMLElement,
                           fetchProfile: (line: string) => Promise<Profile>, onEdit: () => void,
                           notes: {parent: HTMLElement; before: Element | null}): Edit {
  const foundAnchors: Anchors = [{...line.anchors[0]}, {...line.anchors[1]}];
  let found: {profile: Profile | null; error?: string} | null = null, edited = false;
  const state = (s: string) => { root.dataset.edit = s; };
  state("");
  if (scene.level !== "full") return {found(p, error) { found = {profile: p, error}; line.setProfile(p, error); }};

  const hint = document.createElement("p");
  hint.className = "v3-note v3-hint";
  hint.textContent = t("ui.view3d.edit_hint");
  notes.parent.insertBefore(hint, notes.before);
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "u-btn v3-reset v3-hidden";
  reset.textContent = t("ui.view3d.reset");
  scene.toolbar.append(reset);

  const queue = profileQueue(fetchProfile, (outcome) => {
    if (!edited) return;
    if ("value" in outcome) { line.setProfile(outcome.value); state("checked"); }
    else { line.setProfile(null, (outcome.error as Error)?.message || String(outcome.error)); state("error"); }
  });

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
    queue.cancel();
    if (picking) for (const target of scene.pickTargets) disposeBoundsTree.call((target as Mesh).geometry);
  });

  const handles = [0, 1].map((k) => {
    const handle = document.createElement("div");
    handle.className = "v3-handle";
    handle.setAttribute("aria-hidden", "true");
    handle.dataset.anchor = String(k + 1);
    overlayOf(scene).append(handle);
    draggable(scene, handle, {
      start() { pickable(); queue.cancel(); onEdit(); state("moving"); },
      move(x, y) {
        const {raycaster} = pointerRay(scene, x, y);
        const hit = raycaster.intersectObjects(scene.pickTargets, false)[0];
        if (!hit) return;
        const g = scene.fromScene(hit.point), h = scene.heightAt(g.x, g.y);
        if (h === null) return;
        const next: Anchors = [{...line.anchors[0]}, {...line.anchors[1]}];
        next[k] = {x: g.x, y: g.y, h};
        if (!line.setAnchors(next, true)) return;
        edited = true;
        reset.classList.remove("v3-hidden");
      },
      end() {
        // a grab without a move still asks again: the grab cancelled the request of the last release
        if (!edited) { state(""); return; }
        const [a, b] = line.anchors;
        queue.push(lineParam(scene.lonLat(a.x, a.y), scene.lonLat(b.x, b.y)));
        state("waiting");
      },
    });
    return handle;
  });

  const at = new Vector3();
  scene.view.onDrawn(() => {
    line.anchors.forEach((a, k) => place(handles[k], toScreen(scene, at.copy(scene.toScene(a.x, a.y, a.h)))));
  });

  reset.addEventListener("click", () => {
    queue.cancel();
    edited = false;
    reset.classList.add("v3-hidden");
    line.setAnchors(foundAnchors, false);
    if (found) line.setProfile(found.profile, found.error);
    state("");
  });

  return {
    found(profile, error) {
      found = {profile, error};
      if (!edited) line.setProfile(profile, error);
    },
  };
}
