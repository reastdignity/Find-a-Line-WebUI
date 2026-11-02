// The walker's views (docs/3d-view-contract.md, "Wave F"): a switch in the toolbar between the orbit view (the
// default, the only one where anchors are dragged), the walker's eyes (the mannequin, its pin and grip hidden, a
// wider field of view) and behind the walker. Both walker views follow the walker (the slider, the walk, its
// sag): the camera is placed from its pose before every frame (look.ts cameraPose), so they draw on demand as the
// rest. Dragging on the canvas looks around (look.ts dragGaze), the orbit controls off meanwhile; leaving them
// gives back the orbit camera as it was (view.ts setOrbit). The phone's motion (where DeviceOrientationEvent
// exists and the pointer is coarse) turns the gaze on top of the drags, relative to how the phone was held when
// switched on or the view entered; iOS asks for its permission in the button's click. The sensors' readings stay
// in the page. The root's data-view ("orbit", "eyes", "behind"), data-motion ("on", "denied", none) and
// data-camera (the last frame's camera: its position in the scene's metres, its unit direction and its field
// of view) are for tests.

import { Vector3 } from "three";
import { t } from "../i18n";
import type { LineView } from "./line";
import {
  BEHIND_CLEARANCE, cameraPose, clampGaze, deviceLook, dragGaze, gazeMoved, motionOffset, screenAngle, VIEW_SPECS,
  VIEWS, type Gaze, type ViewName,
} from "./look";
import type { SceneCore } from "./scene";

export interface Views {
  /** The view shown. */
  readonly current: ViewName;
  set(view: ViewName): void;
}

const LABELS: Record<ViewName, string> = {
  orbit: "ui.view3d.view_orbit", eyes: "ui.view3d.view_eyes", behind: "ui.view3d.view_behind",
};

const SVG = "http://www.w3.org/2000/svg";
/** The icons' shapes (24 × 24, stroked in currentColor by ui.css .u-ic). */
const ICONS: Record<ViewName | "motion", [string, Record<string, string>][]> = {
  orbit: [["path", {d: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.8 3.4v3.6h-3.6"}], ["circle", {cx: "12", cy: "12", r: "2"}]],
  eyes: [["path", {d: "M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"}],
         ["circle", {cx: "12", cy: "12", r: "3"}]],
  behind: [["circle", {cx: "12", cy: "5", r: "2.4"}], ["path", {d: "M12 8.5v6.5M8 21l4-6 4 6M5 11.5h14"}]],
  motion: [["rect", {x: "8", y: "3", width: "8", height: "18", rx: "2"}], ["path", {d: "M11 18h2M4.5 8.5a7 7 0 0 0 0 7M19.5 8.5a7 7 0 0 1 0 7"}]],
};

function icon(name: keyof typeof ICONS): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "u-ic");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const [tag, attrs] of ICONS[name]) {
    const shape = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) shape.setAttribute(k, v);
    svg.append(shape);
  }
  return svg;
}

function labelled(button: HTMLButtonElement, name: keyof typeof ICONS, text: string) {
  const label = document.createElement("span");
  label.className = "v3-long";
  label.textContent = text;
  button.append(icon(name), label);
  button.setAttribute("aria-label", text);
  button.title = text;
}

type Orientation = {alpha: number | null; beta: number | null; gamma: number | null};
type WithPermission = {requestPermission?: () => Promise<string>};

/** The views of `line`'s walker; `hints`: where the look hint goes (before `before`, null: last) at level full. */
export function createViews(scene: SceneCore, line: LineView, root: HTMLElement,
                            hints: {parent: HTMLElement; before: Element | null}): Views {
  let view: ViewName = "orbit", gaze: Gaze = {yaw: 0, pitch: 0}, offset: Gaze = {yaw: 0, pitch: 0};

  // The switch: a segmented control of icons (with their names from 600 px on), first in the toolbar (under
  // 600 px on a row of its own with the phone's motion, after the walk's and the imagery's controls)
  const seg = document.createElement("div");
  seg.className = "u-seg v3-views";
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", t("ui.view3d.view"));
  const buttons = new Map<ViewName, HTMLButtonElement>();
  for (const name of VIEWS) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.view = name;
    labelled(b, name, t(LABELS[name]));
    b.onclick = () => self.set(name);
    buttons.set(name, b);
    seg.append(b);
  }
  const box = document.createElement("span");
  box.className = "v3-viewbox";
  box.append(seg);

  // The phone's motion: a toggle where the sensors may exist, a note when they are denied or silent
  const Orientation = (globalThis as {DeviceOrientationEvent?: WithPermission}).DeviceOrientationEvent;
  const coarse = typeof matchMedia === "function" && matchMedia("(any-pointer: coarse)").matches;
  const motionButton = document.createElement("button");
  motionButton.type = "button";
  motionButton.className = "u-btn v3-motion v3-hidden";
  labelled(motionButton, "motion", t("ui.view3d.motion"));
  const motionNote = document.createElement("span");
  motionNote.className = "u-small v3-motion-note v3-hidden";
  motionNote.textContent = t("ui.view3d.motion_denied");
  if (Orientation && coarse) box.append(motionButton);
  box.append(motionNote);
  scene.toolbar.prepend(box);

  let lookHint: HTMLElement | null = null;
  if (scene.level === "full") {
    lookHint = document.createElement("p");
    lookHint.className = "v3-note v3-look-hint v3-hidden";
    lookHint.textContent = t("ui.view3d.look_hint");
    hints.parent.insertBefore(lookHint, hints.before);
  }

  // The camera before every frame of a walker view
  const from = new Vector3(), to = new Vector3();
  const total = (): Gaze => ({yaw: gaze.yaw + offset.yaw, pitch: gaze.pitch + offset.pitch});
  scene.beforeDraw(() => {
    if (view === "orbit") return;
    const group = line.walker.group, p = group.position;
    const pose = cameraPose(view, {feet: [p.x, p.y, p.z], yaw: group.rotation.y}, total());
    from.set(...pose.position);
    to.set(...pose.target);
    if (view === "behind") {  // never under the terrain behind the walker
      const g = scene.fromScene(from), ground = scene.heightAt(g.x, g.y);
      if (ground !== null && g.h < ground + BEHIND_CLEARANCE) from.y += ground + BEHIND_CLEARANCE - g.h;
    }
    scene.view.place(from, to, VIEW_SPECS[view].fov);
  });
  const camera = scene.camera, looking = new Vector3();
  scene.view.onDrawn(() => {
    camera.getWorldDirection(looking);
    root.dataset.camera = [...camera.position.toArray().map((v) => v.toFixed(2)),
                           ...looking.toArray().map((v) => v.toFixed(3)), camera.fov.toFixed(0)].join(",");
  });

  // Looking around by dragging on the canvas
  const canvas = scene.renderer.domElement;
  canvas.addEventListener("pointerdown", (e) => {
    if (view === "orbit" || e.button !== 0 || !e.isPrimary) return;
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch { /* a synthetic pointer */ }
    const v = view;
    let x = e.clientX, y = e.clientY;
    const move = (m: PointerEvent) => {
      if (m.pointerId !== e.pointerId || view !== v) return;
      gaze = dragGaze(v, gaze, m.clientX - x, m.clientY - y, canvas.clientHeight);
      x = m.clientX;
      y = m.clientY;
      scene.invalidate();
    };
    const up = (u: PointerEvent) => {
      if (u.pointerId !== e.pointerId) return;
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      removeEventListener("pointercancel", up);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    addEventListener("pointercancel", up);
  });

  // The phone's motion
  let motion = false, base: {heading: number; pitch: number} | null = null, heard: ReturnType<typeof setTimeout> | null = null;
  const onOrientation = (e: Event) => {
    const o = e as unknown as Orientation;
    const reading = deviceLook(o.alpha, o.beta, o.gamma, screenAngle());
    if (!reading) return;
    if (heard !== null) { clearTimeout(heard); heard = null; }
    if (!base) { base = reading; return; }
    const next = motionOffset(base, reading);
    if (view === "orbit" || !gazeMoved(offset, next)) return;
    offset = next;
    scene.invalidate();
  };
  const fold = () => {  // the phone's turn kept in the gaze: switching off leaves the view where it is
    if (view !== "orbit") gaze = clampGaze(view, total());
    offset = {yaw: 0, pitch: 0};
    base = null;
  };
  const motionState = (state: "on" | "denied" | null) => {
    motionButton.classList.toggle("u-on", state === "on");
    motionButton.setAttribute("aria-pressed", String(state === "on"));
    motionNote.classList.toggle("v3-hidden", state !== "denied");
    if (state) root.dataset.motion = state; else delete root.dataset.motion;
  };
  const stopMotion = (state: "denied" | null = null) => {
    if (heard !== null) { clearTimeout(heard); heard = null; }
    if (motion) removeEventListener("deviceorientation", onOrientation);
    motion = false;
    fold();
    motionState(state);
  };
  const startMotion = () => {
    motion = true;
    base = null;
    addEventListener("deviceorientation", onOrientation);
    motionState("on");
    heard = setTimeout(() => { heard = null; stopMotion("denied"); }, 2000);  // no sensor answers
  };
  motionButton.addEventListener("click", () => {
    if (motion) { stopMotion(); return; }
    const ask = Orientation?.requestPermission;
    if (typeof ask !== "function") { startMotion(); return; }
    // iOS: asked inside the click; a refusal (or no answer) leaves dragging only
    ask.call(Orientation).then((answer) => { if (answer === "granted") startMotion(); else stopMotion("denied"); },
                               () => stopMotion("denied"));
  });

  const mark = () => {
    buttons.forEach((b, k) => {
      b.className = k === view ? "u-on" : "";
      b.setAttribute("aria-checked", String(k === view));
    });
    root.dataset.view = view;
    line.walker.group.visible = view !== "eyes";
    motionButton.classList.toggle("v3-hidden", view === "orbit");
    lookHint?.classList.toggle("v3-hidden", view === "orbit");
  };

  const self: Views = {
    get current() { return view; },
    set(next: ViewName) {
      if (next === view) return;
      const was = view;
      if (was !== "orbit") fold();  // the turn of the view left stays with it no further
      view = next;
      if (next === "orbit") {
        if (motion) stopMotion();
        scene.view.setOrbit(true);
      } else {
        gaze = {...VIEW_SPECS[next].start};
        offset = {yaw: 0, pitch: 0};
        base = null;  // the phone's motion relative to how it is held now
        if (was === "orbit") scene.view.setOrbit(false);
      }
      mark();
      scene.invalidate();
    },
  };
  scene.onDispose(() => stopMotion());
  mark();
  return self;
}
