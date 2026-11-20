// The stage's DOM overlay (the anchors' handles, the walker's grip and pin) and the conversions between the scene
// and the screen: a scene point to CSS pixels of the stage, a pointer to its ray. Overlay elements are placed
// through the CSSOM (element.style), never with style attributes (the CSP's style-src 'self').

import { Raycaster, Vector2, Vector3 } from "three";
import type { SceneCore } from "./scene";
import type { Vec3 } from "./interact";

/** The overlay over the canvas (made on first use). */
export function overlayOf(scene: SceneCore): HTMLElement {
  let layer = scene.stage.querySelector<HTMLElement>(".v3-overlay");
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "v3-overlay";
    scene.stage.append(layer);
  }
  return layer;
}

/** A scene point in CSS pixels of the canvas; null behind the camera. */
export function toScreen(scene: SceneCore, v: Vector3): {x: number; y: number} | null {
  const canvas = scene.renderer.domElement, p = v.clone().project(scene.camera);
  if (!(p.z > -1 && p.z < 1)) return null;
  return {x: (p.x + 1) / 2 * canvas.clientWidth, y: (1 - p.y) / 2 * canvas.clientHeight};
}

/** Place an overlay element's reference point at (x, y) CSS pixels; hidden when null. */
export function place(element: HTMLElement, at: {x: number; y: number} | null) {
  element.classList.toggle("v3-hidden", !at);
  if (at) element.style.transform = `translate(${at.x.toFixed(1)}px, ${at.y.toFixed(1)}px)`;
}

/** Half of a mark's target on a touch screen (44 px, view3d.css) and the most a target is moved off its mark's
 *  centre (so it still covers the drawn mark: 18 px). */
export const TARGET_HALF_PX = 22;
export const TARGET_SHIFT_MAX_PX = 13;

/** How far a target centred at `v` is moved to lie inside 0..`size` (CSS pixels; positive: towards larger values),
 *  at most TARGET_SHIFT_MAX_PX either way. */
export function targetShift(v: number, size: number): number {
  const shift = Math.max(0, TARGET_HALF_PX - v) - Math.max(0, v + TARGET_HALF_PX - size);
  return Math.min(TARGET_SHIFT_MAX_PX, Math.max(-TARGET_SHIFT_MAX_PX, shift));
}

/** Keep the touch target of the mark `element`, placed at `at`, inside the stage: `--v3-tx` and `--v3-ty` on the
 *  mark move its target (the mark's own place stays; point.css uses them on a touch screen only). */
export function targetInside(scene: SceneCore, element: HTMLElement, at: {x: number; y: number} | null) {
  if (!at) return;
  const canvas = scene.renderer.domElement;
  element.style.setProperty("--v3-tx", `${targetShift(at.x, canvas.clientWidth).toFixed(1)}px`);
  element.style.setProperty("--v3-ty", `${targetShift(at.y, canvas.clientHeight).toFixed(1)}px`);
}

/** Of the shown marks `among` (fan dots, other lines' labels), the one whose centre lies nearest to the point
 *  (clientX, clientY), else null: a mark's target is larger than the mark (24 px, 44 px on a touch screen:
 *  view3d.css) and two may overlap, where the nearer mark's centre wins, not the order they are drawn in
 *  (pressedMark: for a press on no mark's drawn box). */
export function nearestMark<T extends HTMLElement>(among: Iterable<T>, clientX: number, clientY: number): T | null {
  let best: T | null = null, bestDistance = Infinity;
  for (const mark of among) {
    if (mark.classList.contains("v3-hidden") || mark.closest(".v3-hidden")) continue;
    const r = mark.getBoundingClientRect();
    if (!r.width && !r.height) continue;  // not drawn (its view hides it)
    const d = Math.hypot(r.left + r.width / 2 - clientX, r.top + r.height / 2 - clientY);
    if (d < bestDistance) { best = mark; bestDistance = d; }
  }
  return best;
}

/** Whether the point lies on the mark's own drawn box (not only on its larger, invisible target). */
function onDrawnBox(mark: HTMLElement, clientX: number, clientY: number): boolean {
  if (mark.classList.contains("v3-hidden") || mark.closest(".v3-hidden")) return false;
  const r = mark.getBoundingClientRect();
  return (r.width > 0 || r.height > 0) && clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
}

/** The mark a click on `clicked` goes to. A press on a mark's own drawn box goes to that mark: the clicked one when
 *  the press is on its box, else the mark whose drawn box lies under the press (another mark's invisible target may
 *  lie over it and take the click); the nearest centre if several drawn boxes hold it. Only a press on no drawn box
 *  is decided by the centres alone: the nearest (nearestMark) of the marks whose targets hold the press (the
 *  elements at that point: a target's press reports its mark). With a mouse the targets are smaller (24 px, none
 *  for a label) and the same order holds. A click without a place (a key, a script's click: `detail` 0) stays with
 *  the clicked mark. */
export function pressedMark<T extends HTMLElement>(clicked: T, among: Iterable<T>, e: MouseEvent): T {
  if (!(e.detail > 0)) return clicked;
  const x = e.clientX, y = e.clientY, marks = [...among];
  if (onDrawnBox(clicked, x, y)) return clicked;
  const drawn = marks.filter((m) => onDrawnBox(m, x, y));
  if (drawn.length) return nearestMark(drawn, x, y) ?? clicked;
  const under = new Set<Element>(typeof document.elementsFromPoint === "function" ? document.elementsFromPoint(x, y) : []);
  return nearestMark(marks.filter((m) => m === clicked || under.has(m)), x, y) ?? clicked;
}

const raycaster = new Raycaster();
raycaster.firstHitOnly = true;  // three-mesh-bvh: the nearest hit only

/** The pointer's ray in the scene (origin and unit direction) and a raycaster set to it. */
export function pointerRay(scene: SceneCore, clientX: number, clientY: number):
    {origin: Vec3; dir: Vec3; raycaster: Raycaster} {
  const rect = scene.renderer.domElement.getBoundingClientRect();
  const ndc = new Vector2((clientX - rect.left) / (rect.width || 1) * 2 - 1,
                          -((clientY - rect.top) / (rect.height || 1)) * 2 + 1);
  scene.camera.updateMatrixWorld();
  raycaster.setFromCamera(ndc, scene.camera);
  const {origin, direction} = raycaster.ray;
  return {origin: origin.toArray() as Vec3, dir: direction.toArray() as Vec3, raycaster};
}

/** A drag of an overlay element with the pointer: `move` gets the pointer's client coordinates while it is down;
 *  the orbit controls are off meanwhile. Window listeners (synthetic events and lost captures work too).
 *  `fromCentre`: `move` gets the place of the element's centre instead, as the pointer carries it: the press's
 *  offset from the centre is kept, so a press on the rim of a mark's target (22 px from the centre on a touch
 *  screen) moves the mark by the pointer's movement and not by that offset too. */
export function draggable(scene: SceneCore, element: HTMLElement, handlers: {
  start?(): void; move(clientX: number, clientY: number): void; end?(): void;
}, fromCentre = false) {
  element.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const box = element.getBoundingClientRect();
    const dx = fromCentre ? box.left + box.width / 2 - e.clientX : 0, dy = fromCentre ? box.top + box.height / 2 - e.clientY : 0;
    try { element.setPointerCapture(e.pointerId); } catch { /* a synthetic pointer */ }
    scene.view.setControls(false);
    element.classList.add("v3-dragging");
    handlers.start?.();
    const move = (m: PointerEvent) => { if (m.pointerId === e.pointerId) handlers.move(m.clientX + dx, m.clientY + dy); };
    const up = (u: PointerEvent) => {
      if (u.pointerId !== e.pointerId) return;
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      removeEventListener("pointercancel", up);
      element.classList.remove("v3-dragging");
      scene.view.setControls(true);
      handlers.end?.();
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    addEventListener("pointercancel", up);
  });
}
