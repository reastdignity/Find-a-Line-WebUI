// The found line in the scene: the webbing as two Line2 of CURVE_POINTS points written in place (the loaded
// curve with the walker at s, the unloaded one faint), the walker standing on it, its slider in the toolbar and
// the readout (length, sag, clearance, over trees) once /api/profile answered; until then a neutral colour.

import type { InterleavedBufferAttribute } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { t } from "../i18n";
import type { Profile } from "../types";
import type { Point3d } from "./geometry";
import type { SceneCore } from "./scene";
import { createWalker } from "./walker";
import { metres, readoutOf, resample, walkerPose, webbing, writeSegments, type Readout } from "./webbing";

export interface LineView {
  /** The profile's answer colours the webbing and fills the readout (null: it failed, neutral stays). */
  setProfile(p: Profile | null): void;
  /** The walker at distance `s` along the span. */
  setWalker(s: number): void;
  readout: Readout | null;
  /** The walker's distance along the span. */
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
  const anchors = scene.meta.anchors, w = webbing(anchors, scene.meta.rigging);
  if (!w) return null;
  const neutral = scene.token("--muted");
  const loadedMaterial = new LineMaterial({color: neutral, linewidth: scene.level === "phone" ? 3 : 4});
  const faintMaterial = new LineMaterial({color: neutral, linewidth: 2, transparent: true, opacity: 0.4});
  scene.view.onResize((size) => { loadedMaterial.resolution.copy(size); faintMaterial.resolution.copy(size); });
  const first = walkerPose(w, anchors, w.start.s);
  const unloaded = curve(resample(w.unloaded), scene, faintMaterial);
  const loaded = curve(first ? first.points : resample(w.unloaded), scene, loadedMaterial);
  loaded.line.renderOrder = 1;
  const walker = createWalker(scene.token("--ink"));
  scene.add(unloaded.line);
  scene.add(loaded.line);
  scene.add(walker.group);

  // The readout: length and clearance from the profile, the sag with the walker from sag.ts
  const length = el("span", "v3-read"), sag = el("span", "v3-read"), clearance = el("span", "v3-read");
  const trees = el("span", "v3-read v3-trees v3-hidden", t("ui.view3d.over_trees"));
  const waiting = el("span", "v3-read v3-wait", t("ui.view3d.loading_profile"));
  readoutBox.replaceChildren(length, sag, clearance, trees, waiting);
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

  const self: LineView = {
    readout: null, s: w.start.s, span: w.span,
    setWalker(s: number) {
      const pose = walkerPose(w, anchors, s);
      if (!pose) return;
      self.s = s;
      loaded.write(pose.points);
      walker.group.position.copy(scene.toScene(...pose.at));
      walker.group.rotation.y = pose.yaw;
      sag.textContent = t("ui.view3d.sag", {m: metres(pose.sag)});
      if (String(s) !== slider.value && document.activeElement !== slider) slider.value = String(s);
      scene.invalidate();
    },
    setProfile(p: Profile | null) {
      waiting.remove();
      if (!p) return;
      const r = self.readout = readoutOf(p);
      const color = scene.token(r.overTrees ? "--trees" : "--clear");
      loadedMaterial.color.set(color);
      faintMaterial.color.set(color);
      length.textContent = t("ui.view3d.length", {m: metres(r.length)});
      clearance.textContent = t("ui.view3d.clearance", {m: metres(r.clearance)});
      trees.classList.toggle("v3-hidden", !r.overTrees);
      readoutBox.dataset.filled = "1";
      scene.invalidate();
    },
  };
  slider.addEventListener("input", () => self.setWalker(Number(slider.value)));
  self.setWalker(w.start.s);
  scene.onDispose(() => {
    unloaded.dispose(); loaded.dispose(); loadedMaterial.dispose(); faintMaterial.dispose(); walker.dispose();
  });
  return self;
}
