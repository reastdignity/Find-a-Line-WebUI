// A number's shape as the result view's map draws it (SpotMap.ts: B a box with round corners, a best spot in view;
// P a diamond, a pick of "Start here"; L a six-sided tag, a line from here; A a circle, an anchor of the selected
// line), for the legend and for a row: one drawing for both. Styles in mapbar.css (.v-sh: the map's own paper and
// ink, which do not change with the theme, as the map's tiles do not).

import type { MarkKind } from "../SpotMap";
import "./mapbar.css";

export type { MarkKind };

const SHAPES: Record<MarkKind, string> = {
  B: "M6 2h28a4 4 0 0 1 4 4v12a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V6a4 4 0 0 1 4-4z", P: "M20 1.2 38.8 12 20 22.8 1.2 12z",
  L: "M8 2h24l6.8 10L32 22H8L1.2 12z", A: "M9.4 12a10.6 10.6 0 1 0 21.2 0a10.6 10.6 0 1 0-21.2 0z"};

/** The shape of `kind` with `text` inside ("B3", "P1", "L4", "A1"): 32 × 19 px, its text read out as its name.
 *  `kind` defaults to the text's first letter. */
export function Shape({text, kind = text[0] as MarkKind}: {text: string; kind?: MarkKind}) {
  return <svg class="v-sh" viewBox="0 0 40 24" role="img" aria-label={text} data-shape={kind}>
    <path d={SHAPES[kind] ?? SHAPES.B} /><text x="20" y="12.5">{text}</text></svg>;
}
