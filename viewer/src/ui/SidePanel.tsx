// A side panel beside a map, shared by C's result (result/view/ResultColumns.tsx: the list and the details) and
// the highline layer (app/c/Account.tsx MapPage: the filters and the histograms): its content, its edge to the map
// (a Splitter for the width: a double click the default, Enter collapses) with the round collapse tab beside it (a
// sibling: a separator's children are presentational); collapsed a rail, one button expanding it, marked "auto"
// when the window collapsed it. The content stays drawn while collapsed (hidden: its scroll and state are kept).
// The widths are the caller's (result/view/layout.ts fitPanels); styles in sidepanel.css.

import type { ComponentChildren, RefObject } from "preact";
import { useEffect, useLayoutEffect, useState } from "preact/hooks";
import { Splitter } from "./components";
import { Icon, type IconName } from "./icons";
import type { Column, PanelSide } from "../result/view/layout";
import "./sidepanel.css";

const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");

/** The width of the element `ref` holds: measured after every render (where no frame is drawn too), on a window
 *  resize and by a ResizeObserver. */
export function useWidthOf(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => { if (ref.current) setWidth(ref.current.clientWidth); });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(element.clientWidth);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(element);
    addEventListener("resize", measure);
    return () => { observer?.disconnect(); removeEventListener("resize", measure); };
  }, []);
  return width;
}

export interface SidePanelProps {
  /** Which side of the map: the left panel's edge grows to the right, the right one's to the left. */
  side: PanelSide;
  /** The panel's name in its controls' labels: "Width of the <name>", "Collapse the <name>", "Expand the <name>". */
  name: string;
  /** The panel's accessible name. */
  label: string;
  /** The panel as the window allows it (fitPanels), its least width, the widest it may be dragged, a rail's width. */
  column: Column;
  min: number;
  max: number;
  railWidth: number;
  /** A drag or a key moved the edge (`onCommit` after a drag or a key: keep it); a double click: the default. */
  onWidth(width: number): void;
  onCommit(): void;
  onReset(): void;
  /** The tab, Enter or the rail: collapse or expand. */
  onOpen(open: boolean): void;
  /** A collapsed panel's rail: its icon and its vertical label. */
  rail: {icon: IconName; text: string};
  class?: string;
  children: ComponentChildren;
}

export function SidePanel({side, name, label, column, min, max, railWidth, onWidth, onCommit, onReset, onOpen, rail,
                           class: cls, children}: SidePanelProps) {
  const left = side === "left";
  const style = {"--c-w": `${column.open ? column.width : railWidth}px`} as Record<string, string>;
  return <aside class={cx(cls, "c-col-side", left ? "c-col-left" : "c-col-right", !column.open && "c-collapsed",
                          !column.open && column.forced && "c-forced")}
                style={style} aria-label={label}>
    {children}
    {column.open ? <>
      <Splitter orientation="vertical" class="c-split" label={`Width of the ${name}`} grow={left ? 1 : -1}
                value={column.width} min={min} max={max} onChange={onWidth} onCommit={onCommit} onReset={onReset}
                onToggle={() => onOpen(false)} />
      <button type="button" class="u-split-tab c-col-tab" aria-label={`Collapse the ${name}`}
              title={`Collapse the ${name}`} onClick={() => onOpen(false)}>
        <Icon name={left ? "back" : "next"} /></button>
    </> : <button type="button" class="c-rail" aria-label={`Expand the ${name}`} title={`Expand the ${name}`}
                  onClick={() => onOpen(true)}>
      <Icon name={rail.icon} />
      <span class="c-rail-text">{rail.text}</span>
      <span class="u-split-tab c-rail-tab" aria-hidden="true"><Icon name={left ? "next" : "back"} /></span>
      {column.forced && <span class="c-rail-auto">auto</span>}
    </button>}
  </aside>;
}
