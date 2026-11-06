// The fan of the lines from a point (docs/3d-view-contract.md, "Round 2", point 9): the unloaded webbings from the
// picked point to the representatives, thin at about 55 % in `--clear` or `--trees` by their class (one batch of
// segments with a colour per vertex), the one under the pointer or the list's pointer full and thicker, a dot at
// each webbing's end (a DOM button: hover marks the row, a click chooses the line) and a marker at the point.
// Overlay elements are placed through the CSSOM (no style attributes: the CSP).

import { Color, Vector3 } from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { t } from "../i18n";
import type { Anchor3d } from "./decode";
import type { InterleavedBufferAttribute } from "three";
import type { Option } from "./options";
import type { SceneCore } from "./scene";
import { overlayOf, place, toScreen } from "./screen";
import { CURVE_POINTS, resample, webbing, writeSegments } from "./webbing";
import "./point.css";

/** Points of a fan webbing (segments: one fewer). */
export const FAN_POINTS = 21;
/** Opacity and width (pixels) of the fan's webbings, and of the one highlighted. */
export const FAN_OPACITY = 0.55;
export const FAN_WIDTH = 1.5;
export const HIGHLIGHT_WIDTH = 4;

export interface FanHandlers {
  /** The pointer is over the line of rank `rank` (its dot), or left it (null). */
  hover(rank: number | null): void;
  /** The line of rank `rank` is chosen (its dot clicked). */
  choose(rank: number): void;
}

export interface Fan {
  /** A marker at the picked point (null: none). */
  mark(at: Anchor3d | null): void;
  /** The webbings from `from` to the options (their `h` null: left out); replaces the earlier fan. */
  show(from: Anchor3d, options: readonly Option[]): void;
  /** Mark the line of rank `rank` (null: none); the dot gets its class too. */
  highlight(rank: number | null): void;
  /** The fan and its dots away (the marker stays). */
  clear(): void;
  dispose(): void;
  /** Lines drawn (for tests). */
  readonly count: number;
}

export function createFan(scene: SceneCore, handlers: FanHandlers): Fan {
  const clear = new Color(scene.token("--clear")), trees = new Color(scene.token("--trees"));
  const fanMaterial = new LineMaterial({color: 0xffffff, linewidth: FAN_WIDTH, vertexColors: true, transparent: true,
                                        opacity: FAN_OPACITY, depthWrite: false});
  const markMaterial = new LineMaterial({color: clear, linewidth: HIGHLIGHT_WIDTH});
  const materials = [fanMaterial, markMaterial];
  scene.view.onResize((size) => { for (const m of materials) m.resolution.copy(size); });

  // The highlighted webbing: a Line2 of CURVE_POINTS points written in place
  const markGeometry = new LineGeometry();
  markGeometry.setPositions(new Array(3 * CURVE_POINTS).fill(0));
  const marked = new Line2(markGeometry, markMaterial);
  marked.renderOrder = 3;
  marked.frustumCulled = false;
  marked.visible = false;
  const markBuffer = (markGeometry.getAttribute("instanceStart") as InterleavedBufferAttribute).data;
  scene.add(marked);

  let batch: LineSegments2 | null = null;
  let shown: {from: Anchor3d; options: readonly Option[]; curves: (Option | null)[]; anchors: Anchor3d[]}
      | null = null;
  const dots: HTMLButtonElement[] = [];
  const marker = document.createElement("div");
  marker.className = "v3-point-marker v3-hidden";
  marker.setAttribute("aria-hidden", "true");
  overlayOf(scene).append(marker);
  let markerAt: Anchor3d | null = null;
  const at = new Vector3();

  const free = () => {
    if (batch) { scene.remove(batch); batch.geometry.dispose(); batch = null; }
    for (const d of dots) d.remove();
    dots.length = 0;
    shown = null;
    marked.visible = false;
  };
  const reposition = () => {
    if (markerAt) place(marker, toScreen(scene, at.copy(scene.toScene(markerAt.x, markerAt.y, markerAt.h))));
    if (!shown) return;
    dots.forEach((dot, k) => {
      const a = shown!.anchors[k];
      place(dot, toScreen(scene, at.copy(scene.toScene(a.x, a.y, a.h))));
    });
  };
  scene.view.onDrawn(reposition);

  const self: Fan = {
    get count() { return dots.length; },
    mark(point) {
      markerAt = point;
      marker.classList.toggle("v3-hidden", !point);
      reposition();
      scene.invalidate();
    },
    show(from, options) {
      free();
      const positions: number[] = [], colours: number[] = [], anchors: Anchor3d[] = [], curves: (Option | null)[] = [];
      for (const o of options) {
        if (o.h === null) { curves.push(null); continue; }
        const to: Anchor3d = {x: o.x2, y: o.y2, h: o.h};
        const w = webbing([from, to], scene.meta.rigging);
        // a span the sag solver refuses is drawn as its chord
        const points = w ? resample(w.unloaded, FAN_POINTS)
                         : resample([[from.x, from.y, from.h], [to.x, to.y, to.h]], FAN_POINTS);
        const segments = new Float32Array(6 * (points.length - 1));
        writeSegments(points, scene.origin, segments);
        const c = o.over ? trees : clear;
        for (let k = 0; k < points.length - 1; k++) colours.push(c.r, c.g, c.b, c.r, c.g, c.b);
        for (const v of segments) positions.push(v);
        anchors.push(to);
        curves.push(o);
      }
      if (positions.length) {
        const geometry = new LineSegmentsGeometry();
        geometry.setPositions(positions);
        geometry.setColors(colours);
        batch = new LineSegments2(geometry, fanMaterial);
        batch.frustumCulled = false;
        batch.renderOrder = 1;
        scene.add(batch);
      }
      shown = {from, options, curves, anchors};
      const host = overlayOf(scene);
      for (const o of curves) {
        if (!o) continue;
        const dot = document.createElement("button");
        dot.type = "button";
        dot.tabIndex = -1;
        dot.className = "v3-opt-dot v3-hidden" + (o.over ? " v3-over" : "");
        dot.dataset.rank = String(o.rank);
        dot.setAttribute("aria-label", `${t("ui.view3d.point_length")} ${o.len.toFixed(1)} m`);
        dot.addEventListener("pointerenter", () => handlers.hover(o.rank));
        dot.addEventListener("pointerleave", () => handlers.hover(null));
        dot.addEventListener("click", () => handlers.choose(o.rank));
        host.append(dot);
        dots.push(dot);
      }
      reposition();
      scene.invalidate();
    },
    highlight(rank) {
      for (const d of dots) d.classList.toggle("v3-on", rank !== null && d.dataset.rank === String(rank));
      const k = shown && rank !== null ? shown.curves.findIndex((o) => o?.rank === rank) : -1;
      if (!shown || k < 0) { marked.visible = false; scene.invalidate(); return; }
      const o = shown.curves[k]!, to = {x: o.x2, y: o.y2, h: o.h!};
      const w = webbing([shown.from, to], scene.meta.rigging);
      const points = resample(w ? w.unloaded : [[shown.from.x, shown.from.y, shown.from.h], [to.x, to.y, to.h]]);
      writeSegments(points, scene.origin, markBuffer.array as Float32Array);
      markBuffer.needsUpdate = true;
      markGeometry.computeBoundingBox();
      markGeometry.computeBoundingSphere();
      markMaterial.color.copy(o.over ? trees : clear);
      marked.visible = true;
      scene.invalidate();
    },
    clear() { free(); scene.invalidate(); },
    dispose() {
      free();
      marker.remove();
      scene.remove(marked);
      markGeometry.dispose();
      for (const m of materials) m.dispose();
    },
  };
  return self;
}
