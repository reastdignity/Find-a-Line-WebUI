// The walker's views (docs/3d-view-contract.md, "Wave F"): a switch in the toolbar between the orbit view (the
// default, the only one where anchors are dragged), the walker's eyes (the mannequin, its pin and grip hidden, a
// wider field of view) and behind the walker. Both walker views follow the walker (the slider, the walk, its
// sag): the camera is placed from its pose before every frame (look.ts cameraPose), so they draw on demand as the
// rest. Dragging on the canvas looks around (look.ts dragGaze), the orbit controls off meanwhile; leaving them
// gives back the orbit camera as it was (view.ts setOrbit). The phone's motion (where DeviceOrientationEvent
// exists and the pointer is coarse) turns the gaze on top of the drags, relative to how the phone was held when
// switched on or the view entered; iOS asks for its permission in the button's click. The sensors' readings stay
// in the page. The zoom ("Wave F2"; look.ts): the eyes' horizontal angle (60° by default on every screen, the
// vertical one from the canvas's aspect at every placement), the camera's distance behind the walker; by the
// wheel, a two-finger pinch (which turns nothing) and the +/- buttons beside the switch with the indicator, shown
// in the walker's views only; each view keeps its zoom while the page is open. The root's data-view ("orbit",
// "eyes", "behind"), data-motion ("on", "denied", none) and data-camera (the last frame's camera: its position
// in the scene's metres, its unit direction, its vertical and horizontal fields of view in degrees and, in the
// walker's views, its distance to the point it looks at) are for tests.

import { Vector3 } from "three";
import { t } from "../i18n";
import type { LineView } from "./line";
import {
  BEHIND_CLEARANCE, behindDistance, cameraFov, cameraPose, clampGaze, clampZoom, deviceLook, dragGaze, gazeMoved,
  motionOffset, pinchFactor, screenAngle, VIEW_SPECS, VIEWS, wheelFactor, zoomLabel, zoomRange, zoomStep,
  type Gaze, type ViewName,
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
const ICONS: Record<ViewName | "motion" | "zoomIn" | "zoomOut", [string, Record<string, string>][]> = {
  orbit: [["path", {d: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.8 3.4v3.6h-3.6"}], ["circle", {cx: "12", cy: "12", r: "2"}]],
  eyes: [["path", {d: "M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"}],
         ["circle", {cx: "12", cy: "12", r: "3"}]],
  behind: [["circle", {cx: "12", cy: "5", r: "2.4"}], ["path", {d: "M12 8.5v6.5M8 21l4-6 4 6M5 11.5h14"}]],
  motion: [["rect", {x: "8", y: "3", width: "8", height: "18", rx: "2"}], ["path", {d: "M11 18h2M4.5 8.5a7 7 0 0 0 0 7M19.5 8.5a7 7 0 0 1 0 7"}]],
  zoomIn: [["path", {d: "M12 5v14M5 12h14"}]],
  zoomOut: [["path", {d: "M5 12h14"}]],
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
type WalkerView = Exclude<ViewName, "orbit">;
type WithPermission = {requestPermission?: () => Promise<string>};

/** The views of `line`'s walker; `hints`: where the look hint goes (before `before`, null: last) at level full. */
export function createViews(scene: SceneCore, line: LineView, root: HTMLElement,
                            hints: {parent: HTMLElement; before: Element | null}): Views {
  let view: ViewName = "orbit", gaze: Gaze = {yaw: 0, pitch: 0}, offset: Gaze = {yaw: 0, pitch: 0};
  const zooms: Record<WalkerView, number> = {eyes: 1, behind: 1};

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

  // The zoom: - , the indicator, + (in the walker's views only)
  const zoomBox = document.createElement("span");
  zoomBox.className = "v3-zoom v3-hidden";
  const zoomButton = (name: "zoomIn" | "zoomOut", key: string, direction: 1 | -1) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "u-ib v3-zoom-" + (direction > 0 ? "in" : "out");
    b.append(icon(name));
    b.setAttribute("aria-label", t(key));
    b.title = t(key);
    b.onclick = () => { if (view !== "orbit") setZoom(zoomStep(view, zooms[view], direction)); };
    return b;
  };
  const zoomOut = zoomButton("zoomOut", "ui.view3d.zoom_out", -1), zoomIn = zoomButton("zoomIn", "ui.view3d.zoom_in", 1);
  const zoomValue = document.createElement("span");
  zoomValue.className = "v3-zoom-value";
  zoomValue.setAttribute("aria-live", "polite");
  zoomBox.append(zoomOut, zoomValue, zoomIn);
  box.append(zoomBox);

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
    const pose = cameraPose(view, {feet: [p.x, p.y, p.z], yaw: group.rotation.y}, total(),
                            behindDistance(zooms.behind));
    from.set(...pose.position);
    to.set(...pose.target);
    if (view === "behind") {  // never under the terrain behind the walker
      const g = scene.fromScene(from), ground = scene.heightAt(g.x, g.y);
      if (ground !== null && g.h < ground + BEHIND_CLEARANCE) from.y += ground + BEHIND_CLEARANCE - g.h;
    }
    // the vertical angle from the canvas's aspect now: a resize draws again, so placed again
    scene.view.place(from, to, cameraFov(view, zooms[view], scene.camera.aspect));
  });
  const camera = scene.camera, looking = new Vector3();
  scene.view.onDrawn(() => {
    camera.getWorldDirection(looking);
    const r = Math.PI / 180, horizontal = 2 * Math.atan(Math.tan(camera.fov * r / 2) * camera.aspect) / r;
    root.dataset.camera = [...camera.position.toArray().map((v) => v.toFixed(2)),
                           ...looking.toArray().map((v) => v.toFixed(3)), camera.fov.toFixed(1), horizontal.toFixed(1),
                           ...(view === "orbit" ? [] : [from.distanceTo(to).toFixed(2)])].join(",");
  });

  // The zoom of the view shown
  const showZoom = () => {
    if (view === "orbit") return;
    const z = zooms[view], [lo, hi] = zoomRange(view);
    zoomValue.textContent = t(view === "eyes" ? "ui.view3d.zoom_factor" : "ui.view3d.zoom_distance",
                              {value: zoomLabel(view, z)});
    zoomValue.title = t(view === "eyes" ? "ui.view3d.zoom_factor_title" : "ui.view3d.zoom_distance_title");
    zoomIn.disabled = z >= hi - 1e-9;
    zoomOut.disabled = z <= lo + 1e-9;
  };
  const setZoom = (z: number) => {
    if (view === "orbit") return;
    const next = clampZoom(view, z);
    if (next === zooms[view]) return;
    zooms[view] = next;
    showZoom();
    scene.invalidate();
  };

  // Looking around by dragging on the canvas, zooming by two fingers (a pinch turns nothing: once two fingers were
  // down, the gaze stays until every finger is lifted) and by the wheel
  const canvas = scene.renderer.domElement;
  const pointers = new Map<number, {x: number; y: number}>();
  let pinch: {ids: [number, number]; start: number[]; zoom: number} | null = null, pinched = false;
  const fingers = (ids: [number, number]) => {
    const a = pointers.get(ids[0])!, b = pointers.get(ids[1])!;
    return [a.x, a.y, b.x, b.y];
  };
  const move = (m: PointerEvent) => {
    const at = pointers.get(m.pointerId);
    if (!at) return;
    const dx = m.clientX - at.x, dy = m.clientY - at.y;
    at.x = m.clientX;
    at.y = m.clientY;
    if (view === "orbit") return;
    if (pinch) {
      setZoom(pinch.zoom * pinchFactor(pinch.start, fingers(pinch.ids)));
    } else if (!pinched && (dx || dy)) {
      gaze = dragGaze(view, gaze, dx, dy, canvas.clientHeight, view === "eyes" ? camera.fov * Math.PI / 180 : undefined);
      scene.invalidate();
    }
  };
  const up = (u: PointerEvent) => {
    if (!pointers.delete(u.pointerId)) return;
    if (pinch?.ids.includes(u.pointerId)) pinch = null;
    if (!pointers.size) {
      pinched = false;
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      removeEventListener("pointercancel", up);
    }
  };
  canvas.addEventListener("pointerdown", (e) => {
    if (view === "orbit" || e.button !== 0) return;
    if (!e.isPrimary && !pointers.size) return;  // a second finger whose first did not start here
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch { /* a synthetic pointer */ }
    if (!pointers.size) {
      addEventListener("pointermove", move);
      addEventListener("pointerup", up);
      addEventListener("pointercancel", up);
    }
    pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pointers.size === 2) {
      const ids = [...pointers.keys()] as [number, number];
      pinch = {ids, start: fingers(ids), zoom: zooms[view]};
      pinched = true;
    }
  });
  canvas.addEventListener("wheel", (e) => {
    if (view === "orbit") return;  // the orbit controls' own
    e.preventDefault();
    setZoom(zooms[view] * wheelFactor(e.deltaY, e.deltaMode));
  }, {passive: false});
  scene.onDispose(() => {
    pointers.clear();
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
    removeEventListener("pointercancel", up);
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
    zoomBox.classList.toggle("v3-hidden", view === "orbit");
    showZoom();
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
