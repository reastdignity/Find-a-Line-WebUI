// The line in the scene: the webbing as two Line2 of CURVE_POINTS points written in place (the loaded curve with
// the walker at s, also drawn faintly through the terrain; the unloaded one faint), the walker standing on it, its slider in the toolbar and the readout
// (length, sag, clearance, over trees) once /api/profile answered; until then a neutral colour. The anchors can
// change (edit.ts): the webbing is solved again, neutral and "edited" until the new profile is in. A run with
// A-frames (the patch meta's `lift`): the webbing, the walker and the pin start on the A-frames' tops (geometry.ts
// raised), an A-frame drawn at each anchor; `anchors` stay the ground's.

import type { InterleavedBufferAttribute } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { t } from "../i18n";
import type { Profile } from "../types";
import type { Anchor3d } from "./decode";
import { aFrame, raised, type Point3d, type Webbing } from "./geometry";
import type { SceneCore } from "./scene";
import { createWalker, type Walker } from "./walker";
import {
  metres, readoutOf, resample, unloadedAt, VERDICT_COLOUR, walkerPose, webbing, writeSegments, type Readout,
} from "./webbing";

export type Anchors = [Anchor3d, Anchor3d];

export interface LineView {
  /** The profile's answer colours the webbing and fills the readout (null: it failed, neutral stays; `error`:
   *  its message in the readout). */
  setProfile(p: Profile | null, error?: string): void;
  /** New anchors: the webbing solved again, neutral and marked edited (`edited`) until `setProfile`; false when
   *  the sag solver fails for them (nothing changed). */
  setAnchors(anchors: Anchors, edited: boolean, key?: string | null): boolean;
  /** The key ("lat1,lon1,lat2,lon2") of a line taken from outside whose key is known (a saved line's, one handed
   *  over by the 2D result: round 2, points 7 and 9), so saving and the links name that line and not the rounded
   *  place of its anchors; null for the found line and for dragged anchors. */
  key: string | null;
  /** The walker at distance `s` along the span. */
  setWalker(s: number): void;
  /** Called after the walker moved (by anyone), with its distance along the span. */
  onWalker(fn: (s: number) => void): void;
  /** Called after `setAnchors` changed the line, with its anchors and whether they are moved ones (`edited`). */
  onAnchors(fn: (anchors: Anchors, edited: boolean) => void): void;
  /** Called after `setProfile` showed a profile's answer (null: it failed). */
  onProfile(fn: (p: Profile | null) => void): void;
  /** The anchors are moved ones, not the found line's. */
  edited: boolean;
  /** The profile shown (null: not in yet, or it failed). */
  profile: Profile | null;
  /** The slider's label: the walk's controls go in it (walk.ts). */
  field: HTMLElement;
  slider: HTMLInputElement;
  walker: Walker;
  readout: Readout | null;
  anchors: Anchors;
  /** The walker's distance along the span, the span, the walker's sag there. */
  s: number;
  span: number;
  /** The unloaded webbing's point above the walker's place at distance `s` along the span (grid metres and height);
   *  the pin's tip stands over it (pin.ts). */
  unloadedAt(s: number): Point3d | null;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** A readout's value: its sentence `text` and the short form narrow screens show instead (view3d.css: .v3-long,
 *  .v3-short under 600 px; the hidden one is out of the accessibility tree too). */
function say(span: HTMLElement, text: string, short: string) {
  span.replaceChildren(el("span", "v3-long", text), el("span", "v3-short", short));
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
  // The run's A-frames (the patch meta's lift): the anchors stay the ground's, the webbing starts on their tops
  const lift = scene.meta.lift;
  let top = raised(anchors, lift);
  let w: Webbing | null = webbing(top, scene.meta.rigging);
  if (!w) return null;
  const neutral = scene.token("--muted");
  const width = scene.level === "phone" ? 3 : 4;
  const loadedMaterial = new LineMaterial({color: neutral, linewidth: width});
  const faintMaterial = new LineMaterial({color: neutral, linewidth: 2, transparent: true, opacity: 0.25});
  // The loaded webbing once more through the terrain, faint: where a slope hides it (near an anchor seen from
  // the side) it still reaches the anchor's handle; where it is seen, the same colour drawn over it changes nothing
  const xrayMaterial = new LineMaterial({color: neutral, linewidth: width, transparent: true, opacity: 0.35,
                                         depthTest: false, depthWrite: false});
  const materials = [loadedMaterial, faintMaterial, xrayMaterial];
  scene.view.onResize((size) => { for (const m of materials) m.resolution.copy(size); });
  const first = walkerPose(w, top, w.start.s);
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
  // An A-frame at each anchor: two legs from the ground to the webbing's start (the profile chart's shape)
  const frameMaterial = lift ? new LineMaterial({color: scene.token("--ink-2") || neutral, linewidth: width - 1}) : null;
  const frames = frameMaterial ? ([0, 1] as const).map((k) => {
    const c = curve(aFrame(anchors, k, lift)!, scene, frameMaterial);
    c.line.name = "a-frame";
    scene.add(c.line);
    return c;
  }) : [];
  // its own colour, not the verdict's (colour() recolours `materials` only)
  if (frameMaterial) scene.view.onResize((size) => frameMaterial.resolution.copy(size));

  // The readout: length and clearance from the profile, the sag with the walker from sag.ts
  const length = el("span", "v3-read"), sag = el("span", "v3-read"), clearance = el("span", "v3-read");
  const trees = el("span", "v3-read v3-trees v3-hidden"), edited = el("span", "v3-read v3-edited v3-hidden");
  say(trees, t("ui.view3d.over_trees"), t("ui.view3d.over_trees_short"));
  say(edited, t("ui.view3d.edited"), t("ui.view3d.edited_short"));
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
  const anchorFns: ((anchors: Anchors, edited: boolean) => void)[] = [];
  const profileFns: ((p: Profile | null) => void)[] = [];

  const colour = (name: string | null) => {
    const c = name ? scene.token(name) : neutral;
    for (const m of materials) m.color.set(c);
    readoutBox.dataset.colour = loadedMaterial.color.getHexString();  // for tests
  };

  const self: LineView = {
    readout: null, s: w.start.s, span: w.span, anchors, field, slider, walker, edited: false, profile: null, key: null,
    unloadedAt(s: number) { return unloadedAt(w!, top, s); },
    onAnchors(fn) { anchorFns.push(fn); },
    onProfile(fn) { profileFns.push(fn); },
    setWalker(s: number) {
      const pose = walkerPose(w!, top, s);
      if (!pose) return;
      self.s = Math.min(w!.span, Math.max(0, s));
      loaded.write(pose.points);
      walker.group.position.copy(scene.toScene(...pose.at));
      walker.group.rotation.y = pose.yaw;
      const m = metres(pose.sag);
      say(sag, t("ui.view3d.sag", {m}), t("ui.view3d.sag_short", {m}));
      if (String(s) !== slider.value && document.activeElement !== slider) slider.value = String(s);
      for (const fn of walkerFns) fn(self.s);
      scene.invalidate();
    },
    onWalker(fn) { walkerFns.push(fn); },
    setAnchors(next: Anchors, isEdited: boolean, key: string | null = null) {
      const nextTop = raised(next, lift);
      const solved = webbing(nextTop, scene.meta.rigging);
      if (!solved) return false;
      const fraction = w!.span > 0 ? self.s / w!.span : 0;
      anchors = self.anchors = [{...next[0]}, {...next[1]}];
      top = nextTop;
      frames.forEach((f, k) => f.write(aFrame(anchors, k as 0 | 1, lift)!));
      w = solved;
      self.span = solved.span;
      self.readout = null;
      unloaded.write(resample(solved.unloaded));
      slider.max = String(solved.span);
      slider.step = String(Math.max(0.05, solved.span / 1000));
      colour(null);
      length.textContent = t("ui.view3d.length", {m: metres(solved.span)});
      clearance.replaceChildren();
      trees.classList.add("v3-hidden");
      failed.classList.add("v3-hidden");
      edited.classList.toggle("v3-hidden", !isEdited);
      readoutBox.dataset.filled = "";
      delete readoutBox.dataset.verdict;
      clearance.classList.remove("v3-nofit");
      self.setWalker(fraction * solved.span);
      self.edited = isEdited;
      self.key = isEdited ? key : null;
      self.profile = null;
      for (const fn of anchorFns) fn(self.anchors, isEdited);
      return true;
    },
    setProfile(p: Profile | null, error?: string) {
      waiting.remove();
      failed.textContent = error || "";
      failed.classList.toggle("v3-hidden", !error);
      self.profile = p;
      if (!p) { colour(null); scene.invalidate(); for (const fn of profileFns) fn(null); return; }
      const r = self.readout = readoutOf(p);
      colour(VERDICT_COLOUR[r.verdict]);
      length.textContent = t("ui.view3d.length", {m: metres(r.length)});
      const m = metres(r.clearance);
      if (r.verdict === "no_fit") say(clearance, t("ui.view3d.does_not_fit", {m}), t("ui.view3d.does_not_fit_short", {m}));
      else say(clearance, t("ui.view3d.clearance", {m}), t("ui.view3d.clearance_short", {m}));
      clearance.classList.toggle("v3-nofit", r.verdict === "no_fit");
      readoutBox.dataset.verdict = r.verdict;
      trees.classList.toggle("v3-hidden", !r.overTrees);
      readoutBox.dataset.filled = "1";
      scene.invalidate();
      for (const fn of profileFns) fn(p);
    },
  };
  slider.addEventListener("input", () => self.setWalker(Number(slider.value)));
  self.setWalker(w.start.s);
  scene.onDispose(() => {
    unloaded.dispose(); loaded.dispose(); walker.dispose();
    for (const f of frames) f.dispose();
    frameMaterial?.dispose();
    for (const m of materials) m.dispose();
  });
  return self;
}
