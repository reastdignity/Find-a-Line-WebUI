// The list of the result view (docs/line-volume/spec-view.md B.2 items 4, 13; the frame's `list` slot): the head
// (SpotSummary, ViewFilters), then two blocks. The top block follows the map: at the Area level "Start here" (the
// picks P1 …, a pick's name on a line of its own above its numbers); else "Best in view: 10 of 283" with the rows
// B1 … and a button that raises Best ("Show 30", "Show 100", "Show all"), with All "In view: 95 spots" and at most
// 100 rows. Below, "All spots": a tree of the sectors in the list's order ("Sort by": five keys, kept in the
// browser), the first open, 20 rows a page and 40 more per "Show more", "Show on the map" per sector.
//
// A row (the UX session's requirement 13): a list item that is no control itself; its main part is ONE button that
// selects the row's spot (pressed again: ends the selection; `aria-pressed` says it); any other control of a row
// (the door "›", off until a spot's cards exist: DOOR) is the button's sibling. One tab stop per list (the selected
// row, else the first), the arrows, Home and End move inside it; Enter and Space are the button's own. A row reads
// the run's columns (SpotView.values, the columns' `at`): no Line is made for a row. A row's values carry their
// columns' names for a screen reader (the headings above are hidden from it).
//
// This file also holds the pieces the view's other panels share: a row's cells (Cells), metres and the hook that
// follows a view and its panel state (useViewPanels); the marks' shapes are the map's (Shape.tsx). Styles in
// view.css (classes vl-*).

import { Component, type ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { AccessPair } from "../../access";
import { t } from "../../i18n";
import { COLORS } from "../../style";
import { clearanceText, isTight } from "../../tight";
import type { SpotMap } from "../SpotMap";
import type { Best, Pick as SpotPick, SectorRow, SpotView, ViewSort } from "../spots";
import { BEST_ROWS } from "../viewgeom";
import { Icon } from "../../ui/icons";
import { IconButton } from "../../ui/components";
import { count, cx, Swatch, TightIcon, TightKey } from "./common";
import { Shape } from "./Shape";
import type { PanelProps } from "./SpotPanels";  // types only: SpotPanels.tsx imports the slots, which import this file
import { SpotSummary } from "./SpotSummary";
import { clearAll, ViewFilters, ViewMoreFilters } from "./ViewFilters";
import { changePanels, follow, isOpen, limitOf, panelState, showMore, sortBy, SORTS, watchPanels } from "./viewstate";
import "./view.css";

/** The door "›" of a row ("Open spot"): off until a spot's cards exist (spec-view.md B-5: hidden). */
const DOOR = false;

/** Draw the component again after every change of the view, of its model and of its panels' state. */
export function useViewPanels(view: SpotView) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const redraw = () => setTick((n) => n + 1);
    const stops = [view.subscribe(redraw), watchPanels(view, redraw)];
    return () => stops.forEach((stop) => stop());
  }, [view]);
}

/** Metres as the view writes them: "120 m" (a no-break space), "–" when not known. */
export function metres(v: number | null | undefined, digits = 0): string {
  return typeof v === "number" && Number.isFinite(v) ? t("ui.view.metres", {v: v.toFixed(digits)}) : "–";
}

/** A value of a row with its column's name for a screen reader. */
export function Value({name, class: cls, children}: {name: string; class?: string; children: ComponentChildren}) {
  return <span class={cx("vl-v", cls)}><span class="u-sr">{name} </span>{children}</span>;
}

/** Does this run's rows carry the anchors' access marks (a run made with the mark). */
export const withAccess = (view: SpotView): boolean => view.model.hasAccess;

/** Is a line tight (by its row). */
export const tightRow = (view: SpotView, row: number): boolean => isTight(view.values.clr[row]);

/** Is a line over trees or buildings (by its row). */
export const overRow = (view: SpotView, row: number): boolean => view.model.data.columns.over[row] === 1;

/** The cells of a line that every row of the view shares: its colour (clear, or over trees or buildings: then
 *  also in words for a screen reader, unless the row shows them: `words`; a favourite's with the map's gold halo:
 *  `fav`), length, mean height (`height` "hmax": the highest point in its place) and clearance with the tight mark. */
export function Cells({view, row, height = "hmean", words, fav}: {view: SpotView; row: number; height?: "hmean" | "hmax"; words?: boolean;
                                                                fav?: boolean}) {
  const v = view.values, over = overRow(view, row);
  return <>
    <Swatch color={over ? COLORS.over : COLORS.clean} class={cx("vl-sw", fav && "vl-sw-fav")} />
    {over && !words && <span class="u-sr">{t("ui.result.legend_over")} </span>}
    <Value name={t("ui.list.col.length")}>{metres(v.len[row])}</Value>
    {height === "hmax" ? <Value name={t("ui.list.col.highest")}>{metres(v.hmax[row])}</Value>
      : <Value name={t("ui.list.col.mean")}>{metres(v.hmean[row], 1)}</Value>}
    <Value name={t("ui.view.col.clear")} class="vl-clr">
      {tightRow(view, row) && <TightIcon lift={view.model.data.lift} />}{metres(Number(clearanceText(v.clr[row])), 1)}</Value>
  </>;
}

/** A row's words for a line over trees or buildings (R4.2: the list says it in words), on a line of their own under
 *  the row's values. */
export function OverWords() {
  return <span class="vl-over-words">{t("ui.view.over_words")}</span>;
}

/** The two access marks of a line's anchors (by its row). */
export function RowAccess({view, row}: {view: SpotView; row: number}) {
  const c = view.model.data.columns;
  return <span class="vl-cell-acc"><AccessPair line={{access1: c.access1.at(row), access2: c.access2.at(row)}} /></span>;
}

/** Arrows, Home and End move the focus among a list's rows (`.vl-main` under the element that has the handler); a row's
 *  star (its button's sibling, out of the tab order) is reached by the right arrow from the row and left by the left
 *  arrow, and from a star the others move to the next row's star, as in a grid's column (to the row's button in a row
 *  without one). */
export function rowKeys(e: KeyboardEvent) {
  const target = e.target as HTMLElement, star = target.closest?.(".vl-star") as HTMLElement | null;
  const at = (star ? star.parentElement?.querySelector(":scope > .vl-main") : target.closest?.(".vl-main")) as HTMLElement | null;
  if (!at) return;
  const starOf = (main: HTMLElement | undefined) => main?.parentElement?.querySelector<HTMLElement>(":scope > .vl-star") ?? null;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const to = e.key === "ArrowRight" ? (star ? null : starOf(at)) : (star ? at : null);
    if (to) { e.preventDefault(); to.focus(); }
    return;
  }
  const by = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
  if (!by && e.key !== "Home" && e.key !== "End") return;
  const all = Array.from((e.currentTarget as HTMLElement).querySelectorAll<HTMLElement>(".vl-main"));
  const to = by ? all[all.indexOf(at) + by] : e.key === "Home" ? all[0] : all[all.length - 1];
  e.preventDefault();
  (star && starOf(to)) ? starOf(to)!.focus() : to?.focus();
}

/** The rows of this run's favourites (from ResultModel.favouriteLines: a Line is made for each favourite, never one per
 *  row), kept while the view's version stands (a change of the favourites counts as one: SpotView.version) and while
 *  the page keeps favourites as it did. */
const favouritesOf = new WeakMap<SpotView, {version: number; on: boolean; rows: Set<number>}>();
export function favouriteRows(view: SpotView): Set<number> {
  const model = view.model, on = model.favouritesOn;
  let known = favouritesOf.get(view);
  if (!known || known.version !== view.version || known.on !== on) {
    const rows = new Set<number>();
    if (on) {
      for (const l of model.favouriteLines()) {
        const at = model.indexOf(l);
        if (at >= 0 && at < view.count) rows.add(at);
      }
    }
    known = {version: view.version, on, rows};
    favouritesOf.set(view, known);
  }
  return known.rows;
}

/** A row's star (LinesTable's: today's names and titles): a press adds the row's line to the folder used last, or
 *  removes it (ResultModel.toggleFavourite: its Line made at the press only). Out of the tab order: the list's arrows
 *  reach it (rowKeys). */
function RowStar({view, row}: {view: SpotView; row: number}) {
  const on = favouriteRows(view).has(row), model = view.model;
  return <button type="button" class={cx("vl-star", on && "vl-on")} tabIndex={-1} data-row={row}
                 aria-label={on ? "Remove from favourites" : "Add to favourites"} aria-pressed={on}
                 title={on ? "favourite" : "add to favourites"} onClick={() => model.toggleFavourite(model.lineAt(row))}>
    <Icon name="star" fav={on} /></button>;
}

// the line a row thickens on the map while the mouse is over it
let hovered: {map: Pick<SpotMap, "highlight">; row: number} | null = null;

/** The mouse over a row and away from it (`pointer`: the event's pointer type; only a mouse counts): the row's line
 *  is drawn wider on the map; `gone`: the row went (or shows another line), which ends its own highlight only. */
export function hoverOf(map: Pick<SpotMap, "highlight"> | null, row: number) {
  const end = () => {
    if (hovered && hovered.row === row) { hovered.map.highlight(null); hovered = null; }
  };
  return {
    enter(pointer: string) {
      if (pointer !== "mouse" || !map) return;
      hovered = {map, row};
      map.highlight(row);
    },
    leave(pointer: string) { if (pointer === "mouse") end(); },
    gone: end,
  };
}

/** A row's handlers for the mouse over it (hoverOf); a row that goes while the mouse is over it (a filter, the
 *  map moving under a list that follows it) never sees the pointer leave, so it ends the highlight itself. */
export function useHover(map: SpotMap | null, row: number) {
  const hover = hoverOf(map, row);
  useEffect(() => hover.gone, [map, row]);
  return {onPointerEnter: (e: PointerEvent) => hover.enter(e.pointerType), onPointerLeave: (e: PointerEvent) => hover.leave(e.pointerType)};
}

// The record of the element that last took the focus, kept only while a loss of it may still be repaired (the
// planner's rule of 2026-11-17: the focus is repaired once, at the moment the focused element leaves the page, never
// by a later selection). It is cleared when keepFocus used it, when the person presses anywhere else (the focus then
// goes where the press puts it, or nowhere), and when the focus went nowhere and no repair came within LOSS_FRAMES frames
// (Chromium tells of a focused element's removal by a `focusout` with no element to go to). A row of a list also
// records its place (the list and its index), for the row that takes its place when it goes (lostRowPlaces).
let focused: Element | null = null, focusedPlace: {list: string; index: number; head: string | null} | null = null;
/** Frames after a loss within which a repair may come: keepFocus starts at the next frame (or after the panel's
 *  effect, a frame later) and tries for 6. */
const LOSS_FRAMES = 12;

/** A row's list and index, when the element is a row's button of the top block or of a sector. */
function placeOf(e: Element): typeof focusedPlace {
  const li = e.classList.contains("vl-main") || e.classList.contains("vl-star") ? e.parentElement : null, ul = li?.parentElement;
  if (!li || !ul?.classList.contains("vl-rows")) return null;
  const sec = ul.closest<HTMLElement>(".vl-sec"), index = Array.prototype.indexOf.call(ul.children, li);
  if (sec) return {list: `.vl-sec[data-sector="${sec.dataset.sector}"] .vl-rows`, index, head: `#vl-sec-${Number(sec.dataset.sector) + 1}`};
  return ul.closest(".vl-topblock") ? {list: ".vl-topblock .vl-rows", index, head: null} : null;
}

if (typeof document !== "undefined") {
  document.addEventListener("focusin", (e) => { focused = e.target as Element; focusedPlace = placeOf(focused); }, true);
  // a press elsewhere than on the focused element (a press on it keeps it: no focusin follows)
  document.addEventListener("pointerdown", (e) => {
    if (!focused || !focused.contains(e.target as Node)) focused = focusedPlace = null;
  }, true);
  document.addEventListener("focusout", (e) => {
    if ((e as FocusEvent).relatedTarget) return;  // to another element: its focusin records it
    const was = e.target as Element;
    let frames = LOSS_FRAMES;
    const wait = () => {
      if (focused !== was || document.activeElement === was) return;  // repaired, moved on, or only the window lost it
      if (--frames > 0) requestAnimationFrame(wait);
      else focused = focusedPlace = null;
    };
    requestAnimationFrame(wait);
  }, true);
}

/** The focus must not fall to the page's body when the control that held it went away: once the page has drawn,
 *  if the element that had the focus is gone and nothing has it, it goes to the first of `selectors` that is there
 *  and can take it (then, or after its tries, the record is used up). A focus that was nowhere, or is still where it
 *  was (a press on the map or on a row selected something), is left alone. */
export function keepFocus(...selectors: (string | null | undefined)[]) {
  const go = (tries: number) => {
    const at = document.activeElement;
    if (at && at !== document.body && at.isConnected) return;
    if (!focused || focused.isConnected) return;  // the focus was not lost with its element: nothing to restore
    for (const selector of selectors) {
      const to = selector ? document.querySelector<HTMLElement>(selector) : null;
      if (!to || (to as HTMLButtonElement).disabled) continue;
      to.focus({preventScroll: true});
      if (document.activeElement === to) return;  // not one that cannot take it (inert: a phone's low sheet's body)
    }
    if (tries > 0) requestAnimationFrame(() => go(tries - 1));
    else focused = focusedPlace = null;
  };
  requestAnimationFrame(() => go(5));
}

/** Is the recorded element a row of a list that left the page (its place known); `since`: it was on the page then. */
function lostRow(since: Element | null): boolean {
  return !!focused && focused === since && !focused.isConnected && !!focusedPlace;
}

/** Where the focus goes after a row it was on went (a filter, the map's move under the top block): the row that took
 *  its place in the same list, else that list's last row, else its sector's head. */
function lostRowPlaces(): string[] {
  const p = focusedPlace;
  return p ? [`${p.list} > li:nth-child(${p.index + 1}) > .vl-main`, `${p.list} > li:last-child > .vl-main`, p.head ?? ""] : [];
}

/** Where the focus goes when nothing better is there: the list's tab stop, then the map. */
export const FOCUS_REST = [".vl-tree .vl-main[tabindex='0']", ".vl-topblock .vl-main[tabindex='0']", ".v-map .leaflet-container"];

/** The rows drawn so far (window.FINDALINE_ROWS: tests and measurements of what a redraw costs). */
export const drawn = {rows: 0};
if (typeof window !== "undefined") (window as any).FINDALINE_ROWS = drawn;  // for tests and the browser console

interface RowProps extends PanelProps {
  spot: number;
  /** The row's line: the spot's shown line, or a pick's. */
  row: number;
  id: string;
  /** The row carries the list's tab stop. */
  tab: boolean;
  /** The mark it carries on the map now ("B3", "P1"); none: the spot's fixed label. */
  mark?: string | null;
  /** A pick's name, on a line of its own above the numbers. */
  pick?: string;
  height: "hmean" | "hmax";
}

/** A row of the top block or of the tree. */
function Row({view, map, padding, spot, row, id, tab, mark, pick, height}: RowProps) {
  const sel = view.selected;
  // a pick's row is the selected one only while its own line is selected (another line of the spot: the row
  // selects the pick's line)
  const on = !!sel && sel.spot === spot && (!pick || sel.row === row);
  const press = () => {
    if (on) { view.select(null); return; }
    panelState(view).pressed = {id, spot};  // the list keeps this row in view (SpotList's follow)
    view.select(spot, pick ? row : undefined);
    const now = view.selected;
    if (now) map?.reveal(now.row, padding());  // a list's selection may move the map
  };
  const label = view.label(spot), hover = useHover(map, row), over = overRow(view, row);
  const stars = view.model.favouritesOn;
  drawn.rows++;
  return <li class={cx("vl-row", on && "vl-sel", pick && "vl-pick", over && "vl-over")} id={id}>
    <button type="button" class="vl-main" aria-pressed={on} tabIndex={tab ? 0 : -1} data-spot={spot} data-row={row}
            onClick={press}
            {...hover}>
      {mark ? <Shape text={mark} /> : <span class="vl-num">{label}</span>}
      {pick && <span class="vl-lab" title={pick}>{pick}</span>}
      <Cells view={view} row={row} height={height} words fav={stars && favouriteRows(view).has(row)} />
      {withAccess(view) && <RowAccess view={view} row={row} />}
      <Value name={t("ui.list.col.lines")} class="vl-n">{count(view.passingCount(spot))}</Value>
      {over && <OverWords />}
    </button>
    {stars && <RowStar view={view} row={row} />}
    {DOOR && <button type="button" class="vl-door" aria-label={t("ui.view.door_label", {label})} title={t("ui.view.door")}>›</button>}
  </li>;
}

/** A heading of a list's column, hidden from a screen reader (a row's values carry their names); `by`: the list is
 *  sorted by it (the kit's "sort" icon before its words). */
export function Head({by, text}: {by: boolean; text: string}) {
  return <span class={by ? "vl-by" : undefined} aria-hidden="true">{by && <Icon name="sort" />}{text}</span>;
}

/** The columns' names and their help texts (today's titles of the list's columns: LinesTable), in a row's order. */
function columnHelp(view: SpotView): [string, string][] {
  const out: [string, string][] = [[t("ui.list.col.length"), t("ui.list.col.length_title")],
    view.sort === "hmax" ? [t("ui.list.col.highest"), t("ui.list.col.highest_title")] : [t("ui.list.col.mean"), t("ui.list.col.mean_title")],
    [t("ui.view.col.clear"), t("ui.list.col.clear_title")]];
  if (withAccess(view)) out.push([t("ui.list.col.anchors"), t("ui.list.col.anchors_title")]);
  out.push([t("ui.list.col.lines"), t("ui.list.col.lines_title")]);
  return out;
}

const COL_HELP = "vl-help-cols";  // the id of the columns' help text

/** The headings of the rows (each hidden from a screen reader: a row's values carry their names); sorted by the
 *  highest point, that value stands in the mean height's column; `ranked`: the column the list is sorted by is marked
 *  with the sort icon (not for the picks, which are not ranked); `help`: the columns' info button in the first cell,
 *  above the marks (the top block's heads only; a screen reader reaches it); `stars`: the rows end with a star. */
function Heads({view, ranked, help, stars}: {view: SpotView; ranked: boolean; help?: {open: boolean; toggle(): void}; stars: boolean}) {
  const by = !ranked ? "" : view.sort === "len" ? "len" : view.sort === "clr" ? "clr" : view.sort === "n" ? "n" : "h";
  const head = (key: string, text: string) => <Head by={by === key} text={text} />;
  return <div class={cx("vl-cols", withAccess(view) && "vl-with-acc", stars && "vl-starred")}>
    {help ? <IconButton icon="info" label={t("ui.view.col.about")} plain expanded={help.open} aria-controls={COL_HELP}
                        class="vl-info vl-cols-info" onClick={help.toggle} />
      : <span aria-hidden="true" />}
    <span aria-hidden="true" />
    {head("len", t("ui.list.col.length"))}
    {head("h", t(view.sort === "hmax" ? "ui.list.col.highest" : "ui.list.col.mean"))}
    {head("clr", t("ui.view.col.clear"))}
    {withAccess(view) && <span class="vl-cell-acc" aria-hidden="true">{t("ui.list.col.anchors")}</span>}
    {head("n", t("ui.list.col.lines"))}
  </div>;
}

/** The columns' help, opened in place under the heads by their info button: each column's name and today's words
 *  for it (no box: R8). */
function ColumnHelp({view}: {view: SpotView}) {
  return <dl class="vl-helpt" id={COL_HELP}>
    {columnHelp(view).map(([name, text]) => <div key={name}><dt>{name}</dt><dd>{text}</dd></div>)}
  </dl>;
}

/** The rows' list: its label, the keys, the class of a run with the access marks and of rows with stars. */
function Rows({view, label, stars, children}: {view: SpotView; label: string; stars: boolean; children: ComponentChildren}) {
  return <ul class={cx("vl-rows", withAccess(view) && "vl-with-acc", stars && "vl-starred")} aria-label={label} onKeyDown={rowKeys}>
    {children}</ul>;
}

/** Which row of a list carries its tab stop: the selected spot's when it is among them, else the first. */
function tabStop(view: SpotView, spots: ArrayLike<number>): number {
  const sel = view.selected?.spot;
  if (sel !== undefined) for (let k = 0; k < spots.length; k++) if (spots[k] === sel) return k;
  return 0;
}

const NEXT_BEST: Record<string, {best: Best; text: string}> = {
  10: {best: 30, text: "ui.view.show_30"}, 30: {best: 100, text: "ui.view.show_100"}, 100: {best: "all", text: "ui.view.show_all"}};

/** The top block: "Start here" at the Area level, else the best spots in view (with All: the spots in view); the
 *  columns' help under its heads. */
function TopBlock(p: PanelProps) {
  const {view} = p, area = view.level === "area", all = view.best === "all", v = view.inView;
  const height = view.sort === "hmax" ? "hmax" : "hmean", stars = view.model.favouritesOn;
  const [help, setHelp] = useState(false);
  let title: string, rows: ComponentChildren[] = [], note = "", more: {best: Best; text: string} | null = null, tight = false;
  if (area) {
    title = t("ui.view.start");
    const picks: SpotPick[] = view.picks();
    const stop = Math.max(0, picks.findIndex((k) => view.selected?.spot === k.spot && view.selected.row === k.row));
    rows = picks.map((k, r) => <Row key={k.kind} {...p} spot={k.spot} row={k.row} id={`vl-top-${k.kind}`} tab={r === stop}
                                    mark={"P" + k.n} pick={t(`ui.view.pick.${k.kind}`)} height={height} />);
    tight = picks.some((k) => tightRow(view, k.row));
  } else {
    title = all ? t("ui.view.in_view", {count: v.m, n: count(v.m)}) : t("ui.view.best", {n: v.best.length, m: count(v.m)});
    const shown = v.best.subarray(0, BEST_ROWS), stop = tabStop(view, shown);
    shown.forEach((spot, r) => {
      const n = v.numbered ? view.numberOf(spot) : 0, row = view.shownOf(spot);
      if (tightRow(view, row)) tight = true;
      rows.push(<Row key={spot} {...p} spot={spot} row={row} id={`vl-top-${spot}`} tab={r === stop}
                     mark={n ? "B" + n : null} height={height} />);
    });
    if (all && v.best.length > BEST_ROWS) note = t("ui.view.first_rows", {shown: BEST_ROWS, n: count(v.best.length)});
    if (!v.m) note = t("ui.view.none_in_view");
    if (!all && v.m > v.best.length) more = NEXT_BEST[String(view.best)] ?? null;
  }
  return <section class="vl-block vl-topblock" aria-labelledby="vl-top-title">
    <div class="vl-block-head"><h3 id="vl-top-title">{title}</h3><span class="u-grow" />
      {more && <button type="button" class="u-btn vl-more-best" onClick={() => {
        view.setBest(more!.best);
        // "Show all" goes with Best at All: the focus to the block's rows ("Show 30", "Show 100": the same button)
        keepFocus(".vl-topblock .vl-more-best", ".vl-topblock .vl-main[tabindex='0']", ...FOCUS_REST);
      }}>{t(more.text)}</button>}</div>
    {note && <p class="u-small vl-note">{note}</p>}
    {rows.length > 0 && <>
      <Heads view={view} ranked={!area} stars={stars} help={{open: help, toggle: () => setHelp(!help)}} />
      {help && <ColumnHelp view={view} />}
      <Rows view={view} label={title} stars={stars}>{rows}</Rows>
    </>}
    {tight && <TightKey lift={view.model.data.lift} drawn />}
  </section>;
}

/** A sector of the tree: its head (number and word, spots and their highest mean height, lines and their lengths),
 *  "Show on the map", and while open its rows by pages. */
function SectorRows({p, sector, k}: SectorProps) {
  const {view, map} = p, ui = panelState(view), n = sector.n;
  const open = isOpen(ui, n, k), limit = limitOf(ui, n);
  const name = t("ui.view.sector", {n: n + 1, word: sector.word});
  const height = view.sort === "hmax" ? "hmax" : "hmean", stars = view.model.favouritesOn;
  const shown = open ? sector.spots.slice(0, limit) : [], stop = tabStop(view, shown), rest = sector.spots.length - limit;
  const up = Number.isFinite(sector.hmeanMax) ? sector.hmeanMax.toFixed(0) : "–";
  return <div class="vl-sec" data-sector={n}>
    <div class="vl-sec-head">
      <button type="button" class="vl-toggle" id={`vl-sec-${n + 1}`} aria-expanded={open}
              onClick={() => changePanels(view, (s) => { s.open.set(n, !open); })}>
        <Icon name={open ? "down" : "next"} class="vl-caret" />
        <span><span class="vl-sec-name">{name}</span>
          <span class="vl-meta">{t("ui.view.sector_spots", {count: sector.spots.length, n: count(sector.spots.length), m: up})}</span>
          <span class="vl-meta2">{t("ui.view.sector_lines", {count: sector.lines, n: count(sector.lines),
                                                            a: Math.round(sector.len[0]), b: Math.round(sector.len[1])})}</span></span>
      </button>
      <button type="button" class="vl-sec-map" aria-label={t("ui.view.sector_map_label", {n: n + 1})} title={t("ui.view.sector_map")}
              onClick={() => map?.showSector(n)}><Icon name="locate" /></button>
    </div>
    {open && <>
      <Heads view={view} ranked stars={stars} />
      <Rows view={view} label={name} stars={stars}>
        {shown.map((spot, r) => <Row key={spot} {...p} spot={spot} row={view.shownOf(spot)} id={`vl-row-${spot}`}
                                     tab={r === stop} height={height} />)}
      </Rows>
      {rest > 0 && <button type="button" class="u-btn vl-more" data-sector={n}
                           onClick={() => {
                             changePanels(view, (s) => showMore(s, n));
                             // the last "Show more" goes: the focus to the first row it showed, else the sector's head
                             keepFocus(`.vl-sec[data-sector="${n}"] .vl-more`,
                                       `.vl-sec[data-sector="${n}"] .vl-rows > li:nth-child(${limit + 1}) > .vl-main`, `#vl-sec-${n + 1}`, ...FOCUS_REST);
                           }}>
        {t("ui.view.show_more", {n: count(rest)})}</button>}
    </>}
  </div>;
}

interface SectorProps { p: PanelProps; sector: SectorRow; k: number; sig?: string }

/** Everything a sector's picture depends on: the lines that pass and their order (the view's version, the sort; a
 *  change of the favourites counts in the version), whether it is open and how many rows, the selected spot when it is
 *  one of its own, the canvas, and whether the page keeps favourites (the rows' stars: known after the first draw, and
 *  with none saved the version stays). */
function sectorSig({view, map, wide}: PanelProps, sector: SectorRow, k: number): string {
  const ui = panelState(view), sel = view.selected;
  const mine = sel && view.sectorOf(sel.spot) === sector.n ? sel.spot : -1;
  return [view.version, view.sort, k, isOpen(ui, sector.n, k), limitOf(ui, sector.n), mine, map ? 1 : 0, wide ? 1 : 0,
          view.model.favouritesOn ? 1 : 0].join("|");
}

/** A sector, drawn again only when its picture changes (a move of the map redraws the list at its end: the top
 *  block follows the view, the tree does not). */
class Sector extends Component<SectorProps> {
  shouldComponentUpdate(next: SectorProps) {
    return next.sig !== this.props.sig || next.p.view !== this.props.p.view || next.p.map !== this.props.p.map;
  }
  render() {
    return <SectorRows {...this.props} />;
  }
}

/** "All spots": the sort and the tree of sectors. */
function Tree(p: PanelProps) {
  const {view} = p, ui = panelState(view), sectors = view.sectors;
  const tight = sectors.some((s, k) => isOpen(ui, s.n, k) &&
    s.spots.slice(0, limitOf(ui, s.n)).some((spot) => tightRow(view, view.shownOf(spot))));
  return <section class="vl-block vl-tree" aria-labelledby="vl-tree-title">
    <div class="vl-block-head"><h3 id="vl-tree-title">{t("ui.view.all_spots")}</h3><span class="u-grow" />
      <label class="vl-sort"><span class="u-small">{t("ui.view.sort_by")}</span>
        <select class="r-sort" value={view.sort} onChange={(e) => sortBy(view, e.currentTarget.value as ViewSort)}>
          {SORTS.map((s) => <option key={s} value={s}>{t(`ui.view.sort.${s}`)}</option>)}</select></label></div>
    {sectors.map((s, k) => <Sector key={s.n} p={p} sector={s} k={k} sig={sectorSig(p, s, k)} />)}
    {tight && <TightKey lift={view.model.data.lift} drawn />}
  </section>;
}

/** The model's note first in the list (item 8 of the accepted mock-up, the user's "11 a"): a link's ("The line of the
 *  link is hidden by the filters." with its action "clear filters", not in the run, not measured: model.ts openLinked)
 *  or a favourite's failure, in today's words; a plain line with the info icon, the action a link in the sentence, and
 *  today's × (the planner's choice of 2026-11-20: a favourite's failure stays dismissable). */
function ListNote({view}: {view: SpotView}) {
  const model = view.model, note = model.note;
  if (!note) return null;
  return <div class="vl-lnote" role="status"><Icon name="info" />
    <p class="vl-lnote-text">{note.text}
      {note.action && <>{" "}<button type="button" class="r-link vl-lnote-act" onClick={() => note.onAction?.()}>{note.action}</button></>}</p>
    <IconButton icon="close" label="Close" plain class="vl-lnote-x" onClick={() => {
      model.setNote(null);
      keepFocus(...FOCUS_REST);  // the × goes with the note
    }} />
  </div>;
}

/** No line passes the filters (W9 a): the sentence and "Clear all", which clears what the chips' "Clear all" clears
 *  (every filter of the model and both kinds of lines; "Top level only" stays). */
function NonePass({view}: {view: SpotView}) {
  return <div class="vl-none">
    <p class="vl-none-text">{t("ui.view.none_pass")}</p>
    <button type="button" class="u-btn vl-none-clear" onClick={() => {
      clearAll(view);
      // the block goes: the focus to the list's rows
      keepFocus(".vl-topblock .vl-main[tabindex='0']", ...FOCUS_REST);
    }}>{t("ui.view.chip.clear")}</button>
  </div>;
}

/** Scroll the nearest scrolling ancestor of a row so that the row is in it (not scrollIntoView, which would scroll
 *  every ancestor, the map's too). */
function scrollToRow(row: HTMLElement) {
  for (let box = row.parentElement; box; box = box.parentElement) {
    const overflow = getComputedStyle(box).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && box.scrollHeight > box.clientHeight) {
      const r = row.getBoundingClientRect(), b = box.getBoundingClientRect();
      if (r.top < b.top + 8) box.scrollTop -= b.top + 8 - r.top;
      else if (r.bottom > b.bottom - 8) box.scrollTop += r.bottom - b.bottom + 8;
      return;
    }
  }
}

/** The list panel. In the columns: a head that stays (the summary, the filters) over a body that scrolls; on a
 *  phone one flow in the sheet's body, the headline in the sheet's head while nothing is selected. */
export function SpotList(p: PanelProps) {
  const {view, wide} = p;
  useViewPanels(view);
  const ui = panelState(view), root = useRef<HTMLDivElement>(null);
  // a selection opens its sector and pages it until the row; the list then scrolls to the row, again after the
  // order changed under it (a phone's sheet goes to its top, where the details stand, for another spot only)
  follow(ui, view);
  useEffect(() => {
    if (!ui.scroll || !root.current) return;
    ui.scroll = false;
    if (!wide) {
      const body = root.current.closest<HTMLElement>(".u-sheet-body");
      if (body && ui.scrollNew) body.scrollTop = 0;
      return;
    }
    // a selection made by pressing a row keeps that row in view (it moves nothing where the row is in view); any other
    // (the map, a key on the map, the table of spots) goes to the spot's row in "Best in view" where it has one there
    // (that block and its head stay in view), else to its row in the tree: the planner's decisions of 2026-11-18
    const pressed = ui.pressed && ui.pressed.spot === ui.followed ? ui.pressed.id : null;
    const row = (pressed ? root.current.querySelector<HTMLElement>(`#${pressed}`) : null)
      ?? root.current.querySelector<HTMLElement>(`#vl-top-${ui.followed}`)
      ?? root.current.querySelector<HTMLElement>(`#vl-row-${ui.followed}`);
    if (row) scrollToRow(row);
  });
  // a focused row this drawing took away (a filter, the map's move under the top block): the focus to the row that
  // took its place; only a row that was on the page when this drawing began (the moment of its loss)
  const live = useRef<Element | null>(null);
  if (focused?.isConnected) live.current = focused;
  useEffect(() => {
    if (lostRow(live.current)) keepFocus(...lostRowPlaces(), ...FOCUS_REST);
    live.current = null;
  });
  // no line passes the filters: the sentence and its "Clear all" in the blocks' place (on a phone first in the sheet's
  // body, before the summary and the filters: in view at the stop the state opens at)
  const none = view.counts.lines === 0;
  const blocks = <><ViewMoreFilters view={view} />{!none && <><TopBlock {...p} /><Tree {...p} /></>}</>;
  if (wide) {
    return <>
      <div class="c-col-head vl-head"><SpotSummary view={view} /><ViewFilters view={view} /></div>
      <div class="c-col-body vl-body" ref={root}><ListNote view={view} />{none && <NonePass view={view} />}{blocks}</div>
    </>;
  }
  return <div class="vl-list" ref={root}>
    <ListNote view={view} />
    {none && <NonePass view={view} />}
    <SpotSummary view={view} headline={!!view.selected || !!view.fan} />
    <ViewFilters view={view} />
    {blocks}
  </div>;
}
