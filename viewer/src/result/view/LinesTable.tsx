// The sortable list of the spots of a result (model.rows): length, mean height, clearance (a tight line
// marked, with the mark's key above the list), the anchors' access marks when a run shown has them (access.tsx:
// two dots, anchor 1 and anchor 2; "–" for a line of a run without them; not sortable), lines in the spot and
// the favourite star; the selected row
// highlighted with the shell's details under it, a spot's lines unfolded under its row in the spot's order
// (model.membersOf; the shown one marked), "only in the map's view" (the selected
// spot stays, marked outside the view), the first 100 rows and then more. Rows take the focus; Enter
// selects. Sorting is model.list (list.ts).

import { Fragment, type ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "../../ui/icons";
import { useMedia } from "../../ui/components";
import { useWidthOf } from "../../ui/SidePanel";
import { formatValue, sortKey, SORT_KEYS, type SortKey } from "../../list";
import type { Line } from "../../types";
import { LineGroup, type ResultModel, type Spot } from "../model";
import type { ResultMap } from "../ResultMap";
import { cx, LineCells, TightKey, useModel } from "./common";
import { isTight } from "../../tight";
import { t } from "../../i18n";
import { AccessPair } from "../../access";

const PAGE = 100;
// The list's width (px) from which the column "Anchors" has its full size (the default list of 372 px: 356), and
// under which it is left out
const ACC_FULL = 356, ACC_MIN = 300;
type Column = {key: string; head: string; title: string};
const LENGTH: Column = {key: "len", head: "ui.list.col.length", title: "ui.list.col.length_title"};
const MEAN: Column = {key: "hmean", head: "ui.list.col.mean", title: "ui.list.col.mean_title"};
const HIGHEST: Column = {key: "hmax", head: "ui.list.col.highest", title: "ui.list.col.highest_title"};
const CLEAR: Column = {key: "clr", head: "ui.list.col.clear", title: "ui.list.col.clear_title"};
const LINES: Column = {key: "n", head: "ui.list.col.lines", title: "ui.list.col.lines_title"};

/** The list's columns (their texts' keys): length, the mean height (sorted by the highest point: that value in its
 *  place), clearance, the lines of the spot. */
const columnsOf = (sort: string): Column[] => [LENGTH, sort === "hmax" ? HIGHEST : MEAN, CLEAR, LINES];

export interface LinesTableProps {
  model: ResultModel;
  /** The map layer: hover highlights and "only in the map's view" (hidden without it). */
  view?: ResultMap | null;
  /** Shown right under the selected row (e.g. <LineDetails>). */
  details?: ComponentChildren;
  /** A row or a line of a spot was selected by the user (e.g. to bring it into the map's view). */
  onSelect?(line: Line): void;
  /** Rows shown before "show more" (default 100). */
  page?: number;
  /** Scroll the list to the selected row when the selection changes (default true). */
  follow?: boolean;
}

/** Scroll the nearest scrolling ancestor of a row so that the row is in it (not scrollIntoView, which
 *  would scroll every ancestor, the map's too). */
function scrollToRow(row: HTMLElement) {
  for (let box = row.parentElement; box; box = box.parentElement) {
    const overflow = getComputedStyle(box).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && box.scrollHeight > box.clientHeight) {
      const r = row.getBoundingClientRect(), b = box.getBoundingClientRect();
      const head = box.querySelector<HTMLElement>(".r-head")?.offsetHeight || 0;  // the sticky heading
      if (r.top < b.top + head) box.scrollTop -= b.top + head - r.top;
      else if (r.bottom > b.bottom) box.scrollTop += Math.min(r.bottom - b.bottom, r.top - b.top - head);
      return;
    }
  }
}

export function LinesTable({model, view, details, onSelect, page = PAGE, follow = true}: LinesTableProps) {
  useModel(model);
  const [limit, setLimit] = useState(page);
  // The unfolded spot by the key of its first line: compute() makes new groups on every filter or star
  const [unfolded, setUnfolded] = useState<string | null>(null);
  const hovered = useRef<Line | null>(null);  // the line highlighted on the map by the pointer
  const [, setMoved] = useState(0);
  const canHover = useMedia("(hover: hover)");
  const listRef = useRef<HTMLDivElement>(null);
  const width = useWidthOf(listRef);  // 0 until it is laid out
  const list = model.list, inView = list.inView && !!view;

  useEffect(() => view ? view.onMove(() => setMoved((n) => n + 1)) : undefined, [view]);

  const selected = model.selected;
  const rows: Spot[] = inView ? model.rows.filter((r) => view!.inView(r.line) || r.group === selected?.group)
    : model.rows;
  const at = selected ? rows.findIndex((r) => r.group === selected.group) : -1;
  // The selected spot is always among the rows shown
  useEffect(() => { if (at >= limit) setLimit(Math.ceil((at + 1) / page) * page); }, [at]);
  useEffect(() => {
    const row = listRef.current?.querySelector<HTMLElement>(".r-row.r-sel");
    if (row && follow) scrollToRow(row);
  }, [selected?.line, at < limit]);  // again when "show more" brings it in

  const key = sortKey(list.sort);
  const sortBy = (k: string) => {
    const known = sortKey(k);
    model.setList({...list, sort: known.key, desc: list.sort === known.key ? !list.desc : known.desc});
  };
  /** A row: selects its spot, or unselects it when it is selected; a line of a spot: selects it as the spot's. */
  const pick = (target: LineGroup | Line) => {
    if (target instanceof LineGroup && selected?.group === target) { model.select(null); return; }
    model.select(target);
    if (model.selected) onSelect?.(model.selected.line);
  };
  const hover = (l: Line | null) => {
    if (!canHover) return;
    hovered.current = l;
    view?.highlight(l);
  };
  // A row that goes (a filter, a star with "only favourites") never sees the pointer leave: its line
  // would stay highlighted
  useEffect(() => {
    const l = hovered.current;
    const g = l && model.groupOf(l);
    if (l && !rows.slice(0, limit).some((r) => r.line === l || r.group === g)) hover(null);
  });
  const keys = (e: KeyboardEvent, target: LineGroup | Line) => {
    const el = e.currentTarget as HTMLElement;
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(target); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const all = Array.from(listRef.current?.querySelectorAll<HTMLElement>(".r-row[tabindex]") || []);
      all[all.indexOf(el) + (e.key === "ArrowDown" ? 1 : -1)]?.focus();
    }
  };
  const star = (l: Line) => model.favouritesOn
    ? <button type="button" class={cx("r-star", model.isFavourite(l) && "r-on")}
              aria-label={model.isFavourite(l) ? "Remove from favourites" : "Add to favourites"}
              aria-pressed={model.isFavourite(l)} title={model.isFavourite(l) ? "favourite" : "add to favourites"}
              onClick={(e) => { e.stopPropagation(); model.toggleFavourite(l); }}>
        <Icon name="star" fav={model.isFavourite(l)} /></button>
    : <span />;
  const height = key.key === "hmax" ? "hmax" : "hmean";
  // The column "Anchors": only when a run shown was made with the access mark (a run without it: the list of
  // before), and only where the list has room for it: tighter columns below ACC_FULL px, none below ACC_MIN (a
  // list dragged narrow; the marks stay in the details and the legend)
  const access = model.hasAccess && !(width > 0 && width < ACC_MIN);
  const tightAcc = access && width > 0 && width < ACC_FULL;
  const cells = (l: Line) => <><LineCells line={l} height={height} lift={model.liftOf(l)} />
    {access && <span class="r-cell-acc"><AccessPair line={l} /></span>}</>;
  const shownRows = rows.slice(0, limit);
  const unfoldedRow = shownRows.find((r) => unfolded === model.keyOf(r.group.rep) && r.n > 1);
  const tight = shownRows.some((r) => isTight(r.line.clr))
    || (!!unfoldedRow && model.membersOf(unfoldedRow.group).some((m) => isTight(m.clr)));

  return <div class={cx("r-table", access && "r-with-acc", tightAcc && "r-acc-tight")} ref={listRef}>
    <div class="r-table-tools">
      <label class="r-sortby"><span class="u-small">Sort by</span>
        <select class="r-sort" value={key.key} onChange={(e) => {
          const k = sortKey(e.currentTarget.value);
          model.setList({...list, sort: k.key, desc: k.desc});
        }}>{SORT_KEYS.map((k: SortKey) => <option key={k.key} value={k.key}>{k.label}</option>)}</select></label>
      <button type="button" class="r-dir" aria-label={list.desc ? "Largest first" : "Smallest first"}
              title={list.desc ? "largest first" : "smallest first"}
              onClick={() => model.setList({...list, desc: !list.desc})}>{list.desc ? "↓" : "↑"}</button>
      <span class="u-grow" />
      {view && <label class="r-check r-inview"><input type="checkbox" checked={list.inView}
                                                     onChange={(e) => model.setList({...list, inView: e.currentTarget.checked})} />
        Only in the map's view</label>}
    </div>
    {tight && <TightKey lift={model.data.lift} />}
    <div class="r-row r-head" role="presentation">
      <span />
      {columnsOf(key.key).map((c) => <Fragment key={c.key}>
        {/* the anchors' marks stand before "Lines" */}
        {access && c === LINES && <span class="r-col r-col-plain r-cell-acc" title={t("ui.list.col.anchors_title")}>
          {t("ui.list.col.anchors")}</span>}
        {/* the order said in the button's name: aria-sort belongs to a column header, which this row is not */}
        <button type="button" title={t(c.title)} class={cx("r-col", key.key === c.key && "r-on")}
                onClick={() => sortBy(c.key)}>
        {t(c.head)}{key.key === c.key && (list.desc ? " ↓" : " ↑")}
        {key.key === c.key && <span class="u-sr">{list.desc ? ", sorted largest first" : ", sorted smallest first"}</span>}
        </button></Fragment>)}
      <span />
    </div>
    <div class="r-rows" role="listbox" aria-label="Lines">
      {rows.length === 0 && <p class="u-small r-empty">{inView ? "No lines in the map's view." : "No lines pass the filters."}</p>}
      {shownRows.map((r) => {
        const isSel = selected?.group === r.group, open = unfolded === model.keyOf(r.group.rep) && r.n > 1;
        const outside = inView && isSel && !view!.inView(r.line);
        return <div class={cx("r-spot", isSel && "r-spot-sel")} key={model.keyOf(r.group.rep)}>
          {outside && <p class="u-small r-outside">Selected, outside the map's view</p>}
          <div class={cx("r-row", isSel && "r-sel", r.line.over && "r-over")} role="option" aria-selected={isSel}
               tabIndex={0} onClick={() => pick(r.group)} onKeyDown={(e) => keys(e, r.group)}
               onPointerEnter={() => hover(r.line)} onPointerLeave={() => hover(null)}>
            {cells(r.line)}
            {r.n > 1 ? <button type="button" class={cx("r-unfold", open && "r-on")} aria-expanded={open}
                               aria-label={`${r.n} similar lines: ${open ? "fold" : "unfold"}`}
                               onClick={(e) => { e.stopPropagation(); setUnfolded(open ? null : model.keyOf(r.group.rep)); }}>
                {formatValue(sortKey("n"), r)}<Icon name="down" /></button>
              : <span class="r-muted">1</span>}
            {star(r.line)}
          </div>
          {open && model.membersOf(r.group).map((m, k) => {
            const shown = m === r.line;
            return <div key={k} class={cx("r-row r-member", shown && "r-shown", isSel && shown && "r-sel")}
                        role="option" aria-selected={isSel && shown} tabIndex={0}
                        title={k === 0 ? "the line the spot shows first" : undefined}
                        onClick={() => pick(m)} onKeyDown={(e) => keys(e, m)}
                        onPointerEnter={() => hover(m)} onPointerLeave={() => hover(null)}>
              {cells(m)}
              <span class="r-muted">{shown ? "shown" : k === 0 ? "first" : ""}</span>
              {star(m)}
            </div>;
          })}
          {isSel && details && <div class="r-details-slot">{details}</div>}
        </div>;
      })}
      {rows.length > limit && <button type="button" class="u-btn u-ghost u-full r-showmore"
                                      onClick={() => setLimit(limit + page)}>
        Show more ({rows.length - limit} more)</button>}
    </div>
  </div>;
}
