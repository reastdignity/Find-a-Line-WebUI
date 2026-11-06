// The walker's grip and pin (docs/3d-view-contract.md, "Decisions at the wave-2 checkpoint", round 2 point 1): the
// walker stays at true scale; while it is under PIN_BELOW_PX high on the screen a contrasting pin (a DOM marker of
// the overlay, moved after each frame drawn) shows above it: its tip PIN_LIFT_PX over the unloaded webbing at the
// walker's place (over the head where that is higher), a thin leader from the head to the tip (interact.ts
// pinPlacement). At level `full` the grip over the walker drags it along the line (to the point of the span
// nearest the pointer's ray). The root's data-pin is "1" while the pin shows.

import { Vector3 } from "three";
import { nearestOnSegment, pinPlacement, pinShown, segmentBox, type Vec3 } from "./interact";
import type { LineView } from "./line";
import type { SceneCore } from "./scene";
import { draggable, overlayOf, place, pointerRay, toScreen } from "./screen";
import { WALKER_HEIGHT } from "./webbing";

/** The grip's least height and width (CSS pixels): a touch target over a small walker. */
const GRIP_MIN = 28;

export interface Pin {
  shown: boolean;
}

/** The pin of `line`'s walker; `onDrag`: the walker is grabbed (the walk stops). */
export function createPin(scene: SceneCore, line: LineView, root: HTMLElement, onDrag: () => void): Pin {
  const grip = document.createElement("div");
  grip.className = "v3-grip" + (scene.level === "full" ? " v3-grab" : "");
  grip.setAttribute("aria-hidden", "true");
  const pin = document.createElement("div");
  pin.className = "v3-pin";
  pin.setAttribute("aria-hidden", "true");
  const tipBox = document.createElement("div");  // a point at the pin's tip, which the pin stands on
  tipBox.className = "v3-pin-tip";
  tipBox.append(pin);
  const leader = document.createElement("div");  // from the pin's tip down to the walker's head
  leader.className = "v3-leader";
  leader.setAttribute("aria-hidden", "true");
  const at = document.createElement("div");  // a point at the walker's feet; the grip and the pin stand on it
  at.className = "v3-at";
  at.append(grip, leader, tipBox);
  overlayOf(scene).append(at);
  const self: Pin = {shown: false};
  const feet = new Vector3(), head = new Vector3();

  scene.view.onDrawn(() => {
    const group = line.walker.group;
    group.updateMatrixWorld();
    feet.setFromMatrixPosition(group.matrixWorld);
    head.copy(feet).setY(feet.y + WALKER_HEIGHT);
    const a = toScreen(scene, feet), b = toScreen(scene, head);
    if (!a || !b) { place(at, null); return; }
    const px = Math.hypot(a.x - b.x, a.y - b.y);
    self.shown = pinShown(px);
    at.classList.toggle("v3-pin-on", self.shown);
    root.dataset.pin = self.shown ? "1" : "0";
    // the grip spans the walker (at least GRIP_MIN)
    grip.style.height = `${Math.max(GRIP_MIN, px).toFixed(1)}px`;
    if (self.shown) {
      // the pin over the unloaded webbing at the walker's place, the leader from the head to its tip (both
      // relative to the feet); the webbing's point is behind the camera or missing: over the head alone
      const w = line.unloadedAt(line.s), wp = w ? toScreen(scene, scene.toScene(...w)) : null;
      const {tip, leader: ends} = pinPlacement(a, b, wp);
      const box = segmentBox(ends.from, ends.to);
      tipBox.style.transform = `translate(${(tip.x - a.x).toFixed(1)}px, ${(tip.y - a.y).toFixed(1)}px)`;
      leader.style.transform = `translate(${(tip.x - a.x).toFixed(1)}px, ${(tip.y - a.y).toFixed(1)}px) ` +
                               `rotate(${box.angle.toFixed(4)}rad)`;
      leader.style.height = `${box.length.toFixed(1)}px`;
    }
    place(at, a);
  });

  if (scene.level === "full") {
    draggable(scene, grip, {
      start: onDrag,
      move(x, y) {
        const ray = pointerRay(scene, x, y), [p, q] = line.anchors;
        const t = nearestOnSegment(ray.origin, ray.dir, scene.toScene(p.x, p.y, p.h).toArray() as Vec3,
                                   scene.toScene(q.x, q.y, q.h).toArray() as Vec3);
        line.setWalker(t * line.span);
      },
    });
  }
  return self;
}
