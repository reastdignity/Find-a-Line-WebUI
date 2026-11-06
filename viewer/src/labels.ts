// The labels of the profile chart placed so that none overlaps another or leaves the chart: a pure pass over the
// labels' boxes (tested in Node at the result's and the 3D card's widths, tests/test_viewer.py). Each label says
// where it would like to stand (a text anchor and a baseline), the other side of its marker it may flip to, and how
// far it may move up and down; shorter texts it may fall back to. The labels are placed one by one in their
// priority's order, each at the first free place nearest its own; one that finds none is left out.

export type TextAnchor = "start" | "end";

export interface LabelText { text: string; width: number }

export interface LabelSpec {
  id: string;
  /** Lower first: the anchors 1, the smallest clearance 2, the A-frames 3, the zone 4, the highest point 5. */
  priority: number;
  /** The texts in the order they are tried (the full one first), each with its width in pixels. */
  texts: LabelText[];
  /** The preferred text anchor's x and side. */
  x: number;
  anchor: TextAnchor;
  /** The x of the other side of the marker (the anchor flipped there); none: it does not flip. */
  flipX?: number;
  /** The preferred baseline and the range it may move within. */
  y: number;
  yMin: number;
  yMax: number;
}

export interface PlacedLabel { id: string; text: string; x: number; y: number; anchor: TextAnchor }

export interface Box { left: number; top: number; right: number; bottom: number }

export interface LayoutOptions {
  /** Above and below the baseline, pixels (11 px text). */
  ascent?: number;
  descent?: number;
  /** Space kept free around each box. */
  pad?: number;
  /** The vertical step of the moves. */
  step?: number;
}

const DEFAULTS = {ascent: 9, descent: 3, pad: 1, step: 2};

/** The box of a text of `width` at (x, baseline y) with its anchor. */
export function boxOf(x: number, y: number, width: number, anchor: TextAnchor, o: LayoutOptions = {}): Box {
  const {ascent, descent} = {...DEFAULTS, ...o};
  const left = anchor === "start" ? x : x - width;
  return {left, top: y - ascent, right: left + width, bottom: y + descent};
}

/** Whether two boxes overlap (touching edges do not). */
export function intersects(a: Box, b: Box): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

const inside = (b: Box, bounds: Box) =>
  b.left >= bounds.left && b.right <= bounds.right && b.top >= bounds.top && b.bottom <= bounds.bottom;

/** The baselines a label tries: its own first, then alternately below and above in `step`s, within its range. */
function baselines(spec: LabelSpec, step: number): number[] {
  const lo = Math.min(spec.yMin, spec.y), hi = Math.max(spec.yMax, spec.y), out = [spec.y];
  for (let k = 1; spec.y + k * step <= hi || spec.y - k * step >= lo; k++) {
    if (spec.y + k * step <= hi) out.push(spec.y + k * step);
    if (spec.y - k * step >= lo) out.push(spec.y - k * step);
  }
  return out;
}

/** Place the labels inside `bounds`: by priority (then their order), each text in turn at the first baseline and
 *  side (its own, then flipped) whose box, grown by `pad`, is inside the bounds and meets no box placed before; a
 *  label with no such place is left out. The boxes of the result never intersect. */
export function layoutLabels(specs: LabelSpec[], bounds: Box, options: LayoutOptions = {}): PlacedLabel[] {
  const o = {...DEFAULTS, ...options};
  const order = specs.map((s, k) => [s, k] as const).sort((a, b) => a[0].priority - b[0].priority || a[1] - b[1]);
  const taken: Box[] = [], placed: PlacedLabel[] = [];
  const grow = (b: Box): Box => ({left: b.left - o.pad, top: b.top - o.pad, right: b.right + o.pad, bottom: b.bottom + o.pad});
  for (const [spec] of order) {
    const sides: [number, TextAnchor][] = [[spec.x, spec.anchor]];
    if (spec.flipX !== undefined) sides.push([spec.flipX, spec.anchor === "start" ? "end" : "start"]);
    const ys = baselines(spec, o.step);
    search: for (const text of spec.texts) {
      for (const y of ys) {
        for (const [x, anchor] of sides) {
          const box = grow(boxOf(x, y, text.width, anchor, o));
          if (!inside(box, bounds) || taken.some((t) => intersects(t, box))) continue;
          taken.push(box);
          placed.push({id: spec.id, text: text.text, x, y, anchor});
          break search;
        }
      }
    }
  }
  return placed;
}

/** The width of an 11 px text when nothing measures it (Node, a page before its fonts): a little wider than
 *  system-ui's average, so the boxes are not too small. */
export function estimateWidth(text: string, bold = false, size = 11): number {
  return text.length * size * (bold ? 0.62 : 0.57) + 2;
}

let context: CanvasRenderingContext2D | null | undefined;

/** A text's width in pixels in `font` (a CSS font family) at 11 px, measured by a canvas; the estimate without one.
 *  A little is added for the halo the chart draws around its labels. */
export function textWidth(text: string, bold: boolean, family: string, size = 11): number {
  if (context === undefined) {
    try { context = typeof document !== "undefined" ? document.createElement("canvas").getContext("2d") : null; }
    catch { context = null; }
  }
  if (!context) return estimateWidth(text, bold, size);
  context.font = `${bold ? "bold " : ""}${size}px ${family || "sans-serif"}`;
  const width = context.measureText(text).width;
  return width > 0 ? width + 2 : estimateWidth(text, bold, size);
}
