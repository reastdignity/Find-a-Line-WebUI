// The walk (docs/3d-view-contract.md, "Wave 3", V3a): a Walk / Stop button beside the walker's slider, from the
// walker's place towards the second anchor at 1 m/s (×1 or ×4: the speed button), stopping at the end; Walk at
// the end starts again from the first anchor. The scene keeps drawing ("walk") only while it walks. Under
// prefers-reduced-motion: reduce there is no walk, a note says so; the slider stays. The root's data-walk is "1"
// while it walks.

import { t } from "../i18n";
import { SPEEDS, walkStep } from "./geometry";
import { walkFrom } from "./interact";
import type { LineView } from "./line";
import type { SceneCore } from "./scene";

export interface Walk {
  stop(): void;
}

export function createWalk(scene: SceneCore, line: LineView, root: HTMLElement): Walk {
  const motion = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
  const button = document.createElement("button"), speed = document.createElement("button");
  button.type = speed.type = "button";
  button.className = "u-btn v3-walk";
  speed.className = "u-btn v3-speed";
  speed.setAttribute("aria-label", t("ui.view3d.speed"));
  speed.title = t("ui.view3d.speed");
  const note = document.createElement("span");
  note.className = "u-small v3-reduced";
  note.textContent = t("ui.view3d.reduced_motion");
  const box = document.createElement("span");
  box.className = "v3-walkbox";
  box.append(button, speed, note);
  line.field.after(box);

  let speedIndex = 0, walking = false, unsubscribe: (() => void) | null = null;
  const show = () => {
    const reduced = !!motion?.matches;
    button.classList.toggle("v3-hidden", reduced);
    speed.classList.toggle("v3-hidden", reduced);
    note.classList.toggle("v3-hidden", !reduced);
    if (reduced) self.stop();
  };
  const label = () => {
    button.textContent = t(walking ? "ui.view3d.stop" : "ui.view3d.walk");
    button.setAttribute("aria-pressed", String(walking));
    speed.textContent = t("ui.view3d.speed_value", {times: SPEEDS[speedIndex]});
    root.dataset.walk = walking ? "1" : "0";
  };
  const self: Walk = {
    stop() {
      if (!walking) return;
      walking = false;
      unsubscribe?.();
      unsubscribe = null;
      scene.keepDrawing("walk", false);
      label();
    },
  };
  const go = () => {
    if (motion?.matches) return;
    walking = true;
    line.setWalker(walkFrom(line.s, line.span));
    unsubscribe = scene.onFrame((seconds) => {
      const next = walkStep(line.s, seconds, line.span, SPEEDS[speedIndex], 1, !!motion?.matches);
      line.setWalker(next.s);
      if (next.done) self.stop();
    });
    scene.keepDrawing("walk", true);
    label();
  };
  button.addEventListener("click", () => { if (walking) self.stop(); else go(); });
  speed.addEventListener("click", () => { speedIndex = (speedIndex + 1) % SPEEDS.length; label(); });
  line.slider.addEventListener("input", () => self.stop());
  motion?.addEventListener?.("change", show);
  scene.onDispose(() => { self.stop(); motion?.removeEventListener?.("change", show); });
  label();
  show();
  return self;
}
