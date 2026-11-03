// The choice of spots a click on the map reached about as near (ResultMap's onChoose): a small panel
// next to the click's point, kept within the free part of the map, a row per spot (its line's colour,
// length, clearance, height and its place in the list); the pointer over a row or its focus highlights
// its line, a click or Enter selects it. Esc, a press outside, the map moving and any change of the model
// close it. Styles in result.css (r-choose).

import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { ResultModel } from "../model";
import type { Choice, ResultMap } from "../ResultMap";
import { cx, LineCells } from "./common";

/** A rectangle of the viewport (client px). */
export interface Area { left: number; top: number; right: number; bottom: number }

export interface LineChooserProps {
  model: ResultModel;
  view: ResultMap;
  choices: Choice[];
  /** The click's point in the viewport. */
  at: {x: number; y: number};
  /** The part of the viewport the map shows free of panels. */
  area: Area;
  onClose(): void;
}

const GAP = 12;  // px between the click's point and the panel

/** The panel's corner: beside the point (right and below, else left or above), within the area. */
function place(at: {x: number; y: number}, w: number, h: number, area: Area): {left: number; top: number} {
  const fit = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));
  const right = Math.min(area.right, innerWidth) - 4, bottom = Math.min(area.bottom, innerHeight) - 4;
  const left0 = Math.max(area.left, 0) + 4, top0 = Math.max(area.top, 0) + 4;
  const x = at.x + GAP + w <= right ? at.x + GAP : at.x - GAP - w;
  const y = at.y + GAP + h <= bottom ? at.y + GAP : at.y - GAP - h;
  return {left: Math.max(left0, fit(x, left0, right - w)), top: Math.max(top0, fit(y, top0, bottom - h))};
}

export function LineChooser({model, view, choices, at, area, onClose}: LineChooserProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{left: number; top: number} | null>(null);

  useLayoutEffect(() => {
    const box = panel.current;
    if (box) setPos(place(at, box.offsetWidth, box.offsetHeight, area));
  }, [at.x, at.y]);

  // The first row takes the focus once the panel is placed (hidden before, it could not)
  useEffect(() => {
    if (pos) panel.current?.querySelector<HTMLElement>(".r-row[tabindex]")?.focus({preventScroll: true});
  }, [!!pos]);

  useEffect(() => {
    const outside = (e: Event) => { if (panel.current && !panel.current.contains(e.target as Node)) onClose(); };
    document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("pointerdown", outside); view.highlight(null); };
  }, []);

  const choose = (c: Choice) => { onClose(); view.choose(c); };
  const keys = (e: KeyboardEvent, c: Choice) => {
    const el = e.currentTarget as HTMLElement;
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(c); }
    else if (e.key === "Escape") {
      e.preventDefault();  // the selection stays (ResultMap's Escape)
      onClose();
      view.focusMap();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const all = Array.from(panel.current?.querySelectorAll<HTMLElement>(".r-row[tabindex]") || []);
      all[all.indexOf(el) + (e.key === "ArrowDown" ? 1 : -1)]?.focus();
    }
  };
  const spot = (c: Choice) => {
    const k = model.rows.findIndex((r) => r.group === c.group);
    return k < 0 ? "" : `Spot ${k + 1}`;
  };
  const selected = model.selected?.group;

  return <div ref={panel} class={cx("u-panel r-choose", !pos && "r-choose-new")} role="dialog"
              aria-label="Spots at this point" style={pos ? {left: `${pos.left}px`, top: `${pos.top}px`}
                                                          : {left: `${at.x}px`, top: `${at.y}px`}}>
    <p class="u-small r-choose-title">{choices.length} spots here: which one?</p>
    <div class="r-row r-head" role="presentation">
      <span /><span class="r-col">Length</span><span class="r-col">Clear.</span><span class="r-col">Height</span><span />
    </div>
    <div role="listbox" aria-label="Spots">
      {choices.map((c, k) => <div key={k} class={cx("r-row", c.group === selected && "r-sel", c.line.over && "r-over")}
                                  role="option" aria-selected={c.group === selected} tabIndex={0}
                                  onClick={() => choose(c)} onKeyDown={(e) => keys(e, c)}
                                  onFocus={() => view.highlight(c.line)}
                                  onPointerEnter={() => view.highlight(c.line)} onPointerLeave={() => view.highlight(null)}>
        <LineCells line={c.line} /><span class="r-muted">{spot(c)}</span>
      </div>)}
    </div>
  </div>;
}
