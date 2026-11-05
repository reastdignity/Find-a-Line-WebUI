// "Only valid lines" (docs/3d-view-contract.md, "Round 2", point 3): the tool `valid` (a switch of the tool strip,
// level full), the reach of each anchor as the fixed one (reach.ts; /api/reach, one request at a time and never
// beside a profile request), the overlay on the terrain (`Scene3D.setOverlay`) showing the reach of the anchor that
// stays, and the snap of a dragged anchor to the nearest valid sample. edit.ts drives it from the drag. The root's
// data-reach is whose reach shows: "1" or "2" (the fixed anchor's number), "" for none (tests).

import { Color, DataTexture, LinearMipmapLinearFilter, NearestFilter, RGBAFormat, SRGBColorSpace, UnsignedByteType }
  from "three";
import { t } from "../i18n";
import "./reach.css";
import type { PageRequest } from "./page";
import {
  fetchReach, nearestValid, pictureUv, reachLane, reachPicture, reachUrl, snapRadius, type Lane, type Reach,
  type ReachGet, type Rgb, type Slot,
} from "./reach";
import type { SceneCore } from "./scene";

/** The tool's icon: a check mark (the `d` of a path in a 16 × 16 box). */
export const VALID_ICON = "M2.5 8.5l3.5 3.5 7.5-8";

export interface Valid {
  /** The switch is on. */
  readonly on: boolean;
  /** Run a profile request through the lane: it waits for a reach request in flight and none starts meanwhile. */
  guard<T>(fetch: () => Promise<T>): Promise<T>;
  /** A profile request is waiting to be sent (true) or nothing waits (false). */
  hold(on: boolean): void;
  /** Handle `k` (0 or 1) is grabbed: the reach of the other anchor shows. */
  grab(k: Slot): void;
  /** Where handle `k` goes for the pointer's hit (grid metres) `distance` metres from the camera: the centre of the
   *  nearest valid sample near it; "free" while the switch is off or the reach of the anchor that stays is not
   *  in yet (the handle moves as without the switch); null when no valid sample is near (it stays). */
  snap(k: Slot, hit: {x: number; y: number}, distance: number): {x: number; y: number} | "free" | null;
  /** Anchor `k` was moved: its reach is stale and asked again. */
  moved(k: Slot): void;
  /** The anchors are the found ones again: the reaches asked again, anchor 1's showing. */
  reset(): void;
}

export interface ValidOptions {
  page: Pick<PageRequest, "run" | "line" | "level">;
  /** The fixed point of slot `k` in [lon, lat]. */
  anchorLonLat(k: Slot): [number, number];
  /** The GET of a reach (tests; default: download.ts). */
  get?: ReachGet;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** A CSS colour as bytes. */
export function rgbOf(css: string): Rgb {
  const c = new Color(css), hex = c.getHex(SRGBColorSpace);
  return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255];
}

/** The tool and its overlay on `scene`; the notes (the hint, a failure) go before `notes.before` of
 *  `notes.parent`. Level full only (the caller makes none at the phone level). */
export function createValid(scene: SceneCore, root: HTMLElement, options: ValidOptions,
                            notes: {parent: HTMLElement; before: Element | null}): Valid {
  const reaches: [Reach | null, Reach | null] = [null, null];
  let showing: Slot = 0, drawn: Reach | null = null;
  const hint = el("p", "v3-note v3-valid-note v3-hidden", t("ui.view3d.valid_hint"));
  const failure = el("p", "v3-note v3-valid-note v3-reach-failed v3-hidden");
  failure.setAttribute("role", "alert");
  notes.parent.insertBefore(hint, notes.before);
  notes.parent.insertBefore(failure, notes.before);

  const showError = (message: string) => {
    failure.textContent = message ? t("ui.view3d.reach_failed", {message}) : "";
    failure.classList.toggle("v3-hidden", !message);
  };

  // The overlay: the reach of the anchor that stays, as one picture over the terrain
  const maxTexture = () => scene.renderer.capabilities?.maxTextureSize || 4096;
  const draw = (reach: Reach | null) => {
    if (!reach) { scene.setOverlay(null); return; }
    const picture = reachPicture(reach, rgbOf(scene.token("--ok")), rgbOf(scene.token("--trees")));
    if (!picture || picture.width > maxTexture() || picture.height > maxTexture()) { scene.setOverlay(null); return; }
    const texture = new DataTexture(picture.rgba, picture.width, picture.height, RGBAFormat, UnsignedByteType);
    texture.colorSpace = SRGBColorSpace;
    texture.flipY = false;
    texture.generateMipmaps = true;
    texture.minFilter = LinearMipmapLinearFilter;
    texture.magFilter = NearestFilter;
    texture.needsUpdate = true;
    scene.setOverlay(texture, pictureUv(picture));
  };
  /** The overlay shows the reach of the anchor that stays (drawn again only when that reach changed). */
  const refresh = () => {
    const reach = lane.on ? reaches[showing] : null;
    if (reach !== drawn) { drawn = reach; draw(reach); }
    root.dataset.reach = reach ? String(showing + 1) : "";
  };

  const lane: Lane = reachLane((slot) => fetchReach(reachUrl(options.page, options.anchorLonLat(slot), (slot + 1) as 1 | 2),
                                                    options.get),
    {
      got(slot, reach) {
        reaches[slot] = reach;
        showError("");
        if (slot === showing) refresh();
      },
      failed(slot, e) {
        reaches[slot] = null;
        showError((e as Error)?.message || String(e));
      },
      busy(on) {
        if (on) scene.activity.set("reach", t("ui.view3d.activity_reach"));
        else scene.activity.clear("reach");
      },
    }, () => showing);

  const forget = (slot: Slot) => {
    reaches[slot] = null;
    lane.drop(slot);
    if (slot === showing) refresh();
  };
  const ask = (slot: Slot) => { reaches[slot] = null; showError(""); lane.want(slot); };

  const turn = (on: boolean) => {
    tool.setPressed(on);
    hint.classList.toggle("v3-hidden", !on);
    if (on) {
      lane.on = true;
      showing = 0;
      ask(0);
      ask(1);
    } else {
      lane.stop();
      reaches[0] = reaches[1] = null;
      showError("");
      refresh();
      scene.activity.clear("reach");
    }
  };
  const tool = scene.tools.add({
    id: "valid", label: t("ui.view3d.valid"), icon: VALID_ICON, order: 1, toggle: true,
    onClick() { turn(!lane.on); },
  });
  scene.onDispose(() => { lane.stop(); scene.activity.clear("reach"); });
  root.dataset.reach = "";

  return {
    get on() { return lane.on; },
    guard: (fetch) => lane.guard(fetch),
    hold: (on) => lane.hold(on),
    grab(k) {
      showing = k === 0 ? 1 : 0;
      refresh();
    },
    snap(k, hit, distance) {
      const reach = lane.on ? reaches[k === 0 ? 1 : 0] : null;
      if (!reach) return "free";
      const radius = snapRadius(distance, scene.camera.fov, scene.renderer.domElement.clientHeight || 1,
                                reach.meta.lattice * reach.meta.res);
      const sample = nearestValid(reach, hit.x, hit.y, radius);
      return sample ? {x: sample.x, y: sample.y} : null;
    },
    moved(k) {
      if (!lane.on) return;
      forget(k);
      ask(k);
    },
    reset() {
      if (!lane.on) return;
      showing = 0;
      reaches[0] = reaches[1] = null;
      refresh();
      ask(0);
      ask(1);
    },
  };
}
