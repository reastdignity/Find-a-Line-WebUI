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

/** Of the shown marks `among` (fan dots, other lines' labels), the one whose centre lies nearest to the press at
 *  (clientX, clientY), else null: a mark's target is larger than the mark (24 px, 44 px on a touch screen:
 *  view3d.css) and two may overlap, where the nearer mark's centre wins, not the order they are drawn in. */
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

/** The mark a click goes to: the nearest's (nearestMark) for a press of a pointer, the clicked one itself for a
 *  click without a place (a key, a script's click: `detail` 0). */
export function pressedMark<T extends HTMLElement>(clicked: T, among: Iterable<T>, e: MouseEvent): T {
  return e.detail > 0 ? nearestMark(among, e.clientX, e.clientY) ?? clicked : clicked;
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
 *  the orbit controls are off meanwhile. Window listeners (synthetic events and lost captures work too). */
export function draggable(scene: SceneCore, element: HTMLElement, handlers: {
  start?(): void; move(clientX: number, clientY: number): void; end?(): void;
}) {
  element.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    try { element.setPointerCapture(e.pointerId); } catch { /* a synthetic pointer */ }
    scene.view.setControls(false);
    element.classList.add("v3-dragging");
    handlers.start?.();
    const move = (m: PointerEvent) => { if (m.pointerId === e.pointerId) handlers.move(m.clientX, m.clientY); };
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
