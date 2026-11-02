// The line in the scene: the webbing as two Line2 of CURVE_POINTS points written in place (the loaded curve with
// the walker at s, also drawn faintly through the terrain; the unloaded one faint), the walker standing on it, its slider in the toolbar and the readout
// (length, sag, clearance, over trees) once /api/profile answered; until then a neutral colour. The anchors can
// change (edit.ts): the webbing is solved again, neutral and "edited" until the new profile is in.

import type { InterleavedBufferAttribute } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { t } from "../i18n";
import type { Profile } from "../types";
import type { Anchor3d } from "./decode";
import type { Point3d, Webbing } from "./geometry";
import type { SceneCore } from "./scene";
import { createWalker, type Walker } from "./walker";
import {
  metres, readoutOf, resample, VERDICT_COLOUR, walkerPose, webbing, writeSegments, type Readout,
} from "./webbing";

export type Anchors = [Anchor3d, Anchor3d];

export interface LineView {
  /** The profile's answer colours the webbing and fills the readout (null: it failed, neutral stays; `error`:
   *  its message in the readout). */
  setProfile(p: Profile | null, error?: string): void;
  /** New anchors: the webbing solved again, neutral and marked edited (`edited`) until `setProfile`; false when
   *  the sag solver fails for them (nothing changed). */
  setAnchors(anchors: Anchors, edited: boolean): boolean;
  /** The walker at distance `s` along the span. */
  setWalker(s: number): void;
  /** Called after the walker moved (by anyone), with its distance along the span. */
  onWalker(fn: (s: number) => void): void;
  /** The slider's label: the walk's controls go in it (walk.ts). */
  field: HTMLElement;
  slider: HTMLInputElement;
  walker: Walker;
  readout: Readout | null;
  anchors: Anchors;
  /** The walker's distance along the span, the span, the walker's sag there. */
  s: number;
  span: number;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** A Line2 of `points` whose segment buffer is later written in place. */
function curve(points: Point3d[], scene: SceneCore, material: LineMaterial) {
  const geometry = new LineGeometry();
  const flat: number[] = [];
  for (const p of points) flat.push(...scene.toScene(...p).toArray());
  geometry.setPositions(flat);
  const line = new Line2(geometry, material);
  line.computeLineDistances();
  const buffer = (geometry.getAttribute("instanceStart") as InterleavedBufferAttribute).data;
  return {
    line,
    write(next: Point3d[]) {
      writeSegments(next, scene.origin, buffer.array as Float32Array);
      buffer.needsUpdate = true;
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
    },
    dispose() { geometry.dispose(); },
  };
}

/** The line of the patch's anchors in `scene`, its readout in `readoutBox`; null when the sag solver fails. */
export function createLine(scene: SceneCore, readoutBox: HTMLElement): LineView | null {
  let anchors: Anchors = [{...scene.meta.anchors[0]}, {...scene.meta.anchors[1]}];
  let w: Webbing | null = webbing(anchors, scene.meta.rigging);
  if (!w) return null;
  const neutral = scene.token("--muted");
  const width = scene.level === "phone" ? 3 : 4;
  const loadedMaterial = new LineMaterial({color: neutral, linewidth: width});
  const faintMaterial = new LineMaterial({color: neutral, linewidth: 2, transparent: true, opacity: 0.4});
  // The loaded webbing once more through the terrain, faint: where a slope hides it (near an anchor seen from
  // the side) it still reaches the anchor's handle; where it is seen, the same colour drawn over it changes nothing
  const xrayMaterial = new LineMaterial({color: neutral, linewidth: width, transparent: true, opacity: 0.35,
                                         depthTest: false, depthWrite: false});
  const materials = [loadedMaterial, faintMaterial, xrayMaterial];
  scene.view.onResize((size) => { for (const m of materials) m.resolution.copy(size); });
  const first = walkerPose(w, anchors, w.start.s);
  const unloaded = curve(resample(w.unloaded), scene, faintMaterial);
  const loaded = curve(first ? first.points : resample(w.unloaded), scene, loadedMaterial);
  loaded.line.renderOrder = 1;
  const xray = new Line2(loaded.line.geometry, xrayMaterial);  // the same buffer: loaded.write moves both
  xray.renderOrder = 2;
  const walker = createWalker(scene.token("--ink"));
  scene.add(unloaded.line);
  scene.add(loaded.line);
  scene.add(xray);
  scene.add(walker.group);

  // The readout: length and clearance from the profile, the sag with the walker from sag.ts
  const length = el("span", "v3-read"), sag = el("span", "v3-read"), clearance = el("span", "v3-read");
  const trees = el("span", "v3-read v3-trees v3-hidden", t("ui.view3d.over_trees"));
  const edited = el("span", "v3-read v3-edited v3-hidden", t("ui.view3d.edited"));
  const waiting = el("span", "v3-read v3-wait", t("ui.view3d.loading_profile"));
  const failed = el("span", "v3-read v3-failed v3-hidden");
  readoutBox.replaceChildren(edited, length, sag, clearance, trees, waiting, failed);
  length.textContent = t("ui.view3d.length", {m: metres(w.span)});

  // The slider in the toolbar
  const field = el("label", "v3-field");
  const slider = el("input", "v3-slider");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(w.span);
  slider.step = String(Math.max(0.05, w.span / 1000));
  slider.value = String(w.start.s);
  slider.setAttribute("aria-label", t("ui.view3d.walker_position"));
  field.append(el("span", "v3-field-label", t("ui.view3d.walker")), slider);
  scene.toolbar.append(field);
  const walkerFns: ((s: number) => void)[] = [];

  const colour = (name: string | null) => {
    const c = name ? scene.token(name) : neutral;
    for (const m of materials) m.color.set(c);
    readoutBox.dataset.colour = loadedMaterial.color.getHexString();  // for tests
  };

  const self: LineView = {
    readout: null, s: w.start.s, span: w.span, anchors, field, slider, walker,
    setWalker(s: number) {
      const pose = walkerPose(w!, anchors, s);
      if (!pose) return;
      self.s = Math.min(w!.span, Math.max(0, s));
      loaded.write(pose.points);
      walker.group.position.copy(scene.toScene(...pose.at));
      walker.group.rotation.y = pose.yaw;
      sag.textContent = t("ui.view3d.sag", {m: metres(pose.sag)});
      if (String(s) !== slider.value && document.activeElement !== slider) slider.value = String(s);
      for (const fn of walkerFns) fn(self.s);
      scene.invalidate();
    },
    onWalker(fn) { walkerFns.push(fn); },
    setAnchors(next: Anchors, isEdited: boolean) {
      const solved = webbing(next, scene.meta.rigging);
      if (!solved) return false;
      const fraction = w!.span > 0 ? self.s / w!.span : 0;
      anchors = self.anchors = [{...next[0]}, {...next[1]}];
      w = solved;
      self.span = solved.span;
      self.readout = null;
      unloaded.write(resample(solved.unloaded));
      slider.max = String(solved.span);
      slider.step = String(Math.max(0.05, solved.span / 1000));
      colour(null);
      length.textContent = t("ui.view3d.length", {m: metres(solved.span)});
      clearance.textContent = "";
      trees.classList.add("v3-hidden");
      failed.classList.add("v3-hidden");
      edited.classList.toggle("v3-hidden", !isEdited);
      readoutBox.dataset.filled = "";
      delete readoutBox.dataset.verdict;
      clearance.classList.remove("v3-nofit");
      self.setWalker(fraction * solved.span);
      return true;
    },
    setProfile(p: Profile | null, error?: string) {
      waiting.remove();
      failed.textContent = error || "";
      failed.classList.toggle("v3-hidden", !error);
      if (!p) { colour(null); scene.invalidate(); return; }
      const r = self.readout = readoutOf(p);
      colour(VERDICT_COLOUR[r.verdict]);
      length.textContent = t("ui.view3d.length", {m: metres(r.length)});
      clearance.textContent = t(r.verdict === "no_fit" ? "ui.view3d.does_not_fit" : "ui.view3d.clearance",
                                {m: metres(r.clearance)});
      clearance.classList.toggle("v3-nofit", r.verdict === "no_fit");
      readoutBox.dataset.verdict = r.verdict;
      trees.classList.toggle("v3-hidden", !r.overTrees);
      readoutBox.dataset.filled = "1";
      scene.invalidate();
    },
  };
  slider.addEventListener("input", () => self.setWalker(Number(slider.value)));
  self.setWalker(w.start.s);
  scene.onDispose(() => {
    unloaded.dispose(); loaded.dispose(); walker.dispose();
    for (const m of materials) m.dispose();
  });
  return self;
}
