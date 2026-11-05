// "Lines from a point" (docs/3d-view-contract.md, "Round 2", point 9), level full only: the tool `point` (order 2,
// a switch of the tool strip). On: a click on the terrain (a press and release within a few pixels; a drag still
// turns the camera) picks a point and asks its reach (edit.ts `reach`: through the lane of "Only valid lines", so
// never two quick requests at once and none beside a profile request, the activity `reach` meanwhile); with the
// answer the overlay shows that reach, a marker stands at the point, the representatives (options.ts) are drawn as
// a fan of webbings (fan.ts) and listed (optionlist.ts). A click on a row or on a webbing's end makes it the line
// (`edit.setAnchors([point, target])`, a moved line: the profile is asked as for any), and the tool goes off; off
// without a choice everything of the tool goes and the switch's overlay returns. Nothing is stored. The root's
// data-point is the number of lines shown ("" while the tool is off, "0" while on without an answer), data-fan the
// number of webbings drawn (tests), and data-reach "point" while the point's overlay shows.

import { t } from "../i18n";
import type { Anchor3d } from "./decode";
import type { Edit } from "./edit";
import { createFan } from "./fan";
import type { LineView } from "./line";
import { createOptionList } from "./optionlist";
import { groupingDistance, isClick, representatives, type Option } from "./options";
import type { SceneCore } from "./scene";

/** The tool's icon: a fan of lines from a point (the `d` of a path in a 16 × 16 box). */
export const POINT_ICON = "M3 13L13 4M3 13L13 8.5M3 13H13M3 13L8 3";

export interface Point {
  /** The tool is on. */
  readonly on: boolean;
  set(on: boolean): void;
}

/** The tool on `scene` for the page's line; null at the phone level (and where `edit` has no reach). Called by
 *  main.ts after `createEdit`: `createPoint(scene, line, edit)`. */
export function createPoint(scene: SceneCore, _line: LineView, edit: Edit): Point | null {
  const reach = edit.reach;
  if (scene.level !== "full" || !reach) return null;
  const root = scene.stage.closest<HTMLElement>("#view3d") ?? document.documentElement;
  const canvas = scene.renderer.domElement;
  let isOn = false, epoch = 0, from: Anchor3d | null = null, options: readonly Option[] = [];

  const hover = (rank: number | null, reveal = false) => { fan.highlight(rank); list.highlight(rank, reveal); };
  const choose = (rank: number) => {
    const o = options.find((x) => x.rank === rank);
    if (!o || o.h === null || !from) return;
    const to: Anchor3d = {x: o.x2, y: o.y2, h: o.h};
    // the sag solver may refuse a span: then the tool stays and nothing changed
    if (edit.setAnchors([{...from}, to])) set(false);
  };
  const fan = createFan(scene, {hover: (rank) => hover(rank, true), choose});
  const list = createOptionList(scene, {hover: (rank) => hover(rank), choose});

  const reset = () => {
    epoch++;
    options = [];
    from = null;
    fan.clear();
    fan.mark(null);
    list.hide();
    reach.show(null);
    root.dataset.fan = "";
  };
  const set = (on: boolean) => {
    if (on === isOn) return;
    isOn = on;
    tool.setPressed(on);
    scene.stage.classList.toggle("v3-picking", on);
    reach.setOn(on);
    reset();
    if (on) {
      list.note(t("ui.view3d.point_hint"));
      root.dataset.point = "0";
    } else root.dataset.point = "";
    scene.invalidate();
  };
  const tool = scene.tools.add({
    id: "point", label: t("ui.view3d.point"), icon: POINT_ICON, order: 2, toggle: true,
    onClick() { set(!isOn); },
  });
  root.dataset.point = "";

  /** A point was picked on the terrain at grid metres (x, y): its reach is asked, the earlier pick forgotten. */
  const pick = (x: number, y: number) => {
    if (scene.heightAt(x, y) === null) return;  // over no data: the server would refuse it
    reset();
    const mine = epoch;
    fan.mark({x, y, h: scene.heightAt(x, y)!});
    list.note(t("ui.view3d.activity_reach"));
    root.dataset.point = "0";
    reach.ask(scene.lonLat(x, y), {
      got(r) {
        if (mine !== epoch) return;
        const h = scene.heightAt(r.meta.anchor.x, r.meta.anchor.y) ?? r.meta.anchor.h;
        from = {x: r.meta.anchor.x, y: r.meta.anchor.y, h};
        options = representatives(r, {distance: groupingDistance(scene.meta), heightAt: (px, py) => scene.heightAt(px, py), h1: h});
        reach.show(r);
        fan.mark(from);
        fan.show(from, options);
        root.dataset.fan = String(fan.count);
        list.show(options, r.meta.quantum);
        root.dataset.point = String(options.length);
      },
      failed(error) {
        if (mine !== epoch) return;
        list.fail(t("ui.view3d.reach_failed", {message: (error as Error)?.message || String(error)}));
        root.dataset.point = "0";
      },
    });
  };

  // The click: the primary button (or a finger) pressed and released within a few pixels, in the orbit view, with no
  // modifier (those pan in the orbit controls) and no second finger; anything else is the camera's
  let press: {id: number; x: number; y: number} | null = null;
  const down = (e: PointerEvent) => {
    if (!isOn) return;
    if (press && e.pointerId !== press.id) { press = null; return; }  // a second finger: a pinch
    const orbit = (root.dataset.view || "orbit") === "orbit";
    press = e.button === 0 && e.isPrimary && orbit && !(e.ctrlKey || e.metaKey || e.shiftKey || e.altKey)
      ? {id: e.pointerId, x: e.clientX, y: e.clientY} : null;
  };
  const up = (e: PointerEvent) => {
    const started = press;
    if (!started || e.pointerId !== started.id) return;
    press = null;
    if (!isOn || !isClick(started.x, started.y, e.clientX, e.clientY)) return;
    const hit = edit.pick(e.clientX, e.clientY);
    if (hit) pick(hit.x, hit.y);
  };
  const cancel = () => { press = null; };
  const key = (e: KeyboardEvent) => { if (isOn && e.key === "Escape") set(false); };
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", cancel);
  addEventListener("keydown", key);
  scene.onDispose(() => {
    canvas.removeEventListener("pointerdown", down);
    canvas.removeEventListener("pointerup", up);
    canvas.removeEventListener("pointercancel", cancel);
    removeEventListener("keydown", key);
    reach.setOn(false);
    fan.dispose();
    tool.remove();
  });

  return {get on() { return isOn; }, set};
}
