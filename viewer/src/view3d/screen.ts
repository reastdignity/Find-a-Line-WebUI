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
