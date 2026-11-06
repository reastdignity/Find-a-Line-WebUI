// The profile chart's frame and its labels, pure (Profile.tsx draws them; tests/test_viewer.py checks in Node that
// the labels of the quarry line never overlap at the result's and the 3D card's widths): the scales from the values
// drawn, and the labels of the anchors, the smallest clearance, the A-frames, the no-fall zone and the webbing's
// highest point as specs for labels.ts' layout.

import { layoutLabels, type Box, type LabelSpec, type PlacedLabel } from "./labels";

/** The chart's margins: the heights' axis on the left, the distances' below. */
export const MARGIN = {l: 58, r: 20, t: 18, b: 24};

export interface Frame {
  W: number; H: number; pw: number; ph: number;
  sx: number; sy: number; xoff: number; zmid: number;
  visibleMin: number; visibleMax: number;
  X(d: number): number;
  Y(z: number): number;
}

/** The scales of a chart W × H px over a line of `len` metres showing `values` (heights; NaN and null left out);
 *  `equal`: the same metres per pixel on both axes. */
export function chartFrame(W: number, H: number, len: number, values: (number | null)[], equal: boolean): Frame {
  const M = MARGIN, pw = W - M.l - M.r, ph = H - M.t - M.b;
  const finite = values.filter((v): v is number => v !== null && isFinite(v));
  let zmin = Math.min(...finite), zmax = Math.max(...finite);
  const pad = Math.max((zmax - zmin) * 0.08, 1);
  zmin -= pad; zmax += pad;
  let sx = pw / len, sy = ph / (zmax - zmin), xoff = 0;
  if (equal) {  // same metres per pixel on both axes
    sx = sy = Math.min(sx, sy);
    xoff = (pw - len * sx) / 2;
  }
  const zmid = (zmin + zmax) / 2;
  return {W, H, pw, ph, sx, sy, xoff, zmid, visibleMin: zmid - ph / 2 / sy, visibleMax: zmid + ph / 2 / sy,
          X: (d: number) => M.l + xoff + d * sx, Y: (z: number) => M.t + ph / 2 - (z - zmid) * sy};
}

/** An anchor as drawn: its distance (0 or the length), the ground, its A-frame's height and its label. */
export interface AnchorMark { d: number; ground: number; post: number; text: string }

/** A vertical marker (the smallest clearance, over trees, the highest point): from height `top` down to `bottom`,
 *  its texts (the full one first); `below`: its label preferably under the marker, else over it (the smallest
 *  clearance) or at its middle (the highest point). */
export interface MarkerMark { d: number; top: number; bottom: number; texts: string[]; at: "below" | "above" | "middle" }

export interface ChartMarks {
  len: number;
  anchors: [AnchorMark, AnchorMark];
  /** The A-frames' texts (the full one first), when the anchors stand on A-frames. */
  aframe?: [string[], string[]];
  min?: MarkerMark | null;
  trees?: MarkerMark | null;
  highest?: MarkerMark | null;
  /** The no-fall zone's metres at each end and its texts. */
  zone?: {metres: number; texts: string[]} | null;
}

/** The legs of an A-frame of `post` metres drawn at a scale: half its height in pixels, 4 to 7 px. */
export function frameLeg(frame: Frame, ground: number, post: number): number {
  return Math.max(4, Math.min(7, (frame.Y(ground) - frame.Y(ground + post)) * 0.45));
}

/** The labels' place: the plot's width (and the right margin), from the top of the chart to the distances' axis. */
export function labelBounds(frame: Frame): Box {
  return {left: MARGIN.l, top: 0, right: frame.W - 2, bottom: frame.H - MARGIN.b};
}

const ROOM = 40;  // how far an anchor's or an A-frame's label may move from its own place, px

/** The labels' specs of a chart (labels.ts): `width(text, bold)` measures a text in pixels. */
export function labelSpecs(frame: Frame, marks: ChartMarks, width: (text: string, bold: boolean) => number): LabelSpec[] {
  const {X, Y, H} = frame, M = MARGIN, specs: LabelSpec[] = [];
  const texts = (list: string[], bold = false) => list.map((text) => ({text, width: width(text, bold)}));
  marks.anchors.forEach((a, k) => {
    const side = k === 0 ? 1 : -1, top = Y(a.ground + a.post), y = top - 7;
    specs.push({id: `anchor${k + 1}`, priority: 1, texts: texts([a.text], true), x: X(a.d) + side * 6,
                anchor: side > 0 ? "start" : "end", y, yMin: y - ROOM, yMax: top + ROOM});
  });
  const marker = (id: string, priority: number, m: MarkerMark) => {
    const right = m.d > marks.len / 2, gap = right ? -4 : 4;  // the inner side first, so it is not cut off
    const yTop = Y(m.top), yBottom = Y(m.bottom);
    const y = m.at === "below" ? yBottom + 12 : m.at === "above" ? yTop - 4 : (yTop + yBottom) / 2;
    specs.push({id, priority, texts: texts(m.texts), x: X(m.d) + gap, anchor: right ? "end" : "start",
                flipX: X(m.d) - gap, y, yMin: Math.min(yTop, yBottom) - ROOM, yMax: Math.max(yTop, yBottom) + 12 + ROOM});
  };
  if (marks.min) marker("min", 2, marks.min);
  if (marks.trees) marker("trees", 2, marks.trees);
  if (marks.aframe) {
    marks.anchors.forEach((a, k) => {
      if (!(a.post > 0)) return;
      // beside the post when it is tall enough to hold its label, else under its feet: the webbing and the anchor's
      // label run at its top
      const side = k === 0 ? 1 : -1, leg = frameLeg(frame, a.ground, a.post);
      const foot = Y(a.ground), head = Y(a.ground + a.post);
      const y = foot - head >= 24 ? (foot + head) / 2 + 4 : foot + 13;
      specs.push({id: `aframe${k + 1}`, priority: 3, texts: texts(marks.aframe![k]), x: X(a.d) + side * (leg + 4),
                  anchor: side > 0 ? "start" : "end", flipX: X(a.d) - side * (leg + 4), y, yMin: head - ROOM,
                  yMax: y + ROOM});
    });
  }
  if (marks.zone && marks.zone.metres > 0) {
    const z = marks.zone.metres, y = H - M.b - 6, yMin = M.t + 10;
    specs.push({id: "zone1", priority: 4, texts: texts(marks.zone.texts), x: X(z) + 4, anchor: "start", flipX: X(z) - 4,
                y, yMin, yMax: y});
    specs.push({id: "zone2", priority: 4, texts: texts(marks.zone.texts), x: X(marks.len - z) - 4, anchor: "end",
                flipX: X(marks.len - z) + 4, y, yMin, yMax: y});
  }
  if (marks.highest) marker("highest", 5, marks.highest);
  return specs;
}

/** The labels of a chart placed (labelSpecs, then labels.ts' layout within labelBounds). */
export function chartLabels(frame: Frame, marks: ChartMarks, width: (text: string, bold: boolean) => number): PlacedLabel[] {
  return layoutLabels(labelSpecs(frame, marks, width), labelBounds(frame));
}
