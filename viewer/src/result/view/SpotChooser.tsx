// The table of spots under a press (docs/line-volume/spec-view.md B.2 item 9; the frame's `chooser` slot, opened
// by the canvas when a press reached several spots about as near): "{n} spots here: which one?", at most six rows:
// the spots that carry a number on the map first, by their number and with their shape (such a row selects the
// spot's bold line), then the others by their distance from the press under their fixed label ("1.3"); each with
// its line's colour, length, mean height and clearance (the tight mark; its key under the rows). A row is a list
// item with one button (SpotList's rows); the pointer over a row or its focus thickens its line on the map; a press
// selects and closes (the map does not move: a press on the map never moves it). Its ×, a press outside, and by
// the frame Esc, a move of the map and any change of the view close it. Beside the press's point within the free
// part of the map; on a phone at the bottom of the screen.

import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { Icon } from "../../ui/icons";
import { t } from "../../i18n";
import type { SpotChoice } from "../spots";
import { cx, TightKey } from "./common";
import type { Area } from "./LineChooser";
import { Shape } from "./Shape";
import { Cells, FOCUS_REST, keepFocus, rowKeys, tightRow } from "./SpotList";
import type { ChooserProps } from "./SpotPanels";

const GAP = 12;  // px between the press's point and the panel
export const CHOICES = 6;

/** The rows in the table's order: a spot once, numbered first by their number, then by the distance from the
 *  press; at most CHOICES. */
export function chooserRows(choices: SpotChoice[]): SpotChoice[] {
  const number = (c: SpotChoice) => c.label ? Number(c.label.slice(1)) : Infinity;
  const seen = new Set<number>();
  return choices.filter((c) => !seen.has(c.spot) && !!seen.add(c.spot)).sort((a, b) => (a.label ? 0 : 1) - (b.label ? 0 : 1) || (a.label && b.label ? number(a) - number(b) : a.px - b.px))
    .slice(0, CHOICES);
}

/** The panel's corner: beside the point (right and below, else left or above), within the area (LineChooser's
 *  placing). */
export function place(at: {x: number; y: number}, w: number, h: number, area: Area): {left: number; top: number} {
  const fit = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));
  const right = Math.min(area.right, innerWidth) - 4, bottom = Math.min(area.bottom, innerHeight) - 4;
  const left0 = Math.max(area.left, 0) + 4, top0 = Math.max(area.top, 0) + 4;
  const x = at.x + GAP + w <= right ? at.x + GAP : at.x - GAP - w;
  const y = at.y + GAP + h <= bottom ? at.y + GAP : at.y - GAP - h;
  return {left: Math.max(left0, fit(x, left0, right - w)), top: Math.max(top0, fit(y, top0, bottom - h))};
}

export function SpotChooser({view, map, wide, choices, at, area, onClose}: ChooserProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{left: number; top: number} | null>(null);
  const dock = !wide, placed = dock || !!pos;
  const rows = chooserRows(choices);

  useLayoutEffect(() => {
    const box = panel.current;
    if (box && !dock) setPos(place(at, box.offsetWidth, box.offsetHeight, area));
  }, [at.x, at.y]);

  // The first row takes the focus once the panel is placed (hidden before, it could not)
  useEffect(() => {
    if (placed) panel.current?.querySelector<HTMLElement>(".vl-main")?.focus({preventScroll: true});
  }, [placed]);

  useEffect(() => {
    const outside = (e: Event) => { if (panel.current && !panel.current.contains(e.target as Node)) onClose(); };
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      map?.highlight(null);
      // closed (its ×, Esc, a row): the focus to the selected spot's row, else to the map
      const sel = view.selected?.spot;
      keepFocus(sel === undefined ? null : `#vl-row-${sel} .vl-main`, sel === undefined ? null : `#vl-top-${sel} .vl-main`,
                ".v-map .leaflet-container", ...FOCUS_REST);
    };
  }, []);

  const choose = (c: SpotChoice) => {
    onClose();
    view.select(c.spot, c.row);
  };
  const style = dock ? undefined : pos ? {left: `${pos.left}px`, top: `${pos.top}px`} : {left: `${at.x}px`, top: `${at.y}px`};
  return <div ref={panel} class={cx("u-panel vl-choose", dock && "vl-choose-dock", !placed && "vl-choose-new")} role="dialog"
              aria-label={t("ui.view.chooser.label")} style={style}>
    <p class="u-small vl-choose-title"><span class="u-grow">{t("ui.view.chooser.title", {n: rows.length})}</span>
      <button type="button" class="r-note-x vl-choose-x" aria-label={t("ui.view.chooser.close")} onClick={onClose}>
        <Icon name="close" /></button></p>
    <div class="vl-cols" aria-hidden="true"><span /><span />
      <span>{t("ui.list.col.length")}</span><span>{t("ui.list.col.mean")}</span><span>{t("ui.list.col.clear")}</span></div>
    <ul class="vl-rows" aria-label={t("ui.view.chooser.label")} onKeyDown={rowKeys}>
      {rows.map((c, k) => <li class={cx("vl-row", view.selected?.spot === c.spot && "vl-sel")} key={c.spot}>
        <button type="button" class="vl-main" tabIndex={k === 0 ? 0 : -1} data-spot={c.spot} data-row={c.row}
                aria-pressed={view.selected?.spot === c.spot} onClick={() => choose(c)}
                onFocus={() => map?.highlight(c.row)}
                onPointerEnter={() => map?.highlight(c.row)} onPointerLeave={() => map?.highlight(null)}>
          {c.label ? <Shape text={c.label} /> : <span class="vl-num">{view.label(c.spot)}</span>}
          <Cells view={view} row={c.row} />
        </button>
      </li>)}
    </ul>
    {rows.some((c) => tightRow(view, c.row)) && <TightKey lift={view.model.data.lift} />}
  </div>;
}
