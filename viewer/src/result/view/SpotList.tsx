// The list of the result view (docs/line-volume/spec-view.md B.2 items 4, 13; the frame's `list` slot): the head
// (SpotSummary, ViewFilters), then two blocks. The top block follows the map: at the Area level "Start here" (the
// picks P1 …, a pick's name on a line of its own above its numbers); else "Best in view: 10 of 283" with the rows
// B1 … and a button that raises Best ("Show 30", "Show 100", "Show all"), with All "In view: 95 spots" and at most
// 100 rows. Below, "All spots": a tree of the sectors in the list's order ("Sort by": five keys, and beside it the
// direction, "Largest first" / "Smallest first", step 3d's P4: it orders the tree only; both kept in the browser), the
// first open, 20 rows a page and 40 more per "Show more", "Show on the map" per sector.
//
// A row (the UX session's requirement 13): a list item that is no control itself; its main part is ONE button that
// selects the row's spot (pressed again: ends the selection; `aria-pressed` says it); any other control of a row
// (its star where the page keeps favourites, step 3c; the door "›", off until a spot's cards exist: DOOR) is the
// button's sibling. One tab stop per list (the selected row, else the first), the arrows, Home and End move inside it
// (the right arrow to a row's star, rowKeys); Enter and Space are the button's own. A row reads the run's columns
// (SpotView.values, the columns' `at`): no Line is made for a row (a star's state comes from the favourites' rows,
// its Line at a press). A row's values carry their columns' names for a screen reader (the headings above are hidden
// from it, the columns' help button is not).
//
// Step 3c also put here: the model's note first in the list (ListNote), the list's place when no line passes the
// filters (NonePass), and the columns' help under the top block's heads (ColumnHelp).
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
import { FavouritePicker } from "./FavouritePicker";
import { Shape } from "./Shape";
import type { PanelProps } from "./SpotPanels";  // types only: SpotPanels.tsx imports the slots, which import this file
import { SpotSummary } from "./SpotSummary";
import { clearAll, useEscCloses, ViewFilters, ViewMoreFilters } from "./ViewFilters";
import { changePanels, follow, isOpen, limitOf, panelState, reverse, showMore, sortBy, SORTS, watchPanels } from "./viewstate";
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
  const at = (star ? star.closest(".vl-row")?.querySelector(":scope > .vl-main") : target.closest?.(".vl-main")) as HTMLElement | null;
  if (!at) return;
  if (e.key === "Tab") {
    // one tab stop per list: Tab (Shift+Tab) from a row or a star the arrows reached leaves the list in one press, also
    // when the list's tab stop lies after it (before it): the stop is out of the tab order for this press only (never
    // focused on the way: a row's focus may draw its line on the map, the table of spots'), back once the browser moved
    // the focus
    const list = e.currentTarget as HTMLElement, stop = list.querySelector<HTMLElement>(".vl-main[tabindex='0']");
    if (stop && stop !== target && target.compareDocumentPosition(stop) & (e.shiftKey ? 2 : 4)) {
      stop.tabIndex = -1;
      // back only while it is still the list's stop: a drawing in between that made another row the stop set that
      // row's 0 (never two stops in a list)
      setTimeout(() => {
        if (stop.isConnected && stop.tabIndex === -1 && !list.querySelector(".vl-main[tabindex='0']")) stop.tabIndex = 0;
      });
    }
    return;
  }
  const starOf = (main: HTMLElement | undefined) =>
    main?.parentElement?.querySelector<HTMLElement>(":scope > .vl-star, :scope > .r-popwrap > .vl-star") ?? null;
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

/** The row whose star has its folders open, per view (its list item's id and its line): that row draws the folder
 *  picker in its star's place while it is open (one Line, made for it alone); every other row, and that row once the
 *  picker closed, the plain star. */
const pickerOf = new WeakMap<SpotView, {id: string; row: number}>();

/** Where the focus goes when a row's open picker went: the row's plain star, else the row that took the row's place in
 *  its list (`place`: as lostRowPlaces), else the list's rest. */
function pickerFocus(id: string, place: ReturnType<typeof placeOf>) {
  keepFocus(`#${id} > .vl-star`, ...(place ? [`${place.list} > li:nth-child(${place.index + 1}) > .vl-main`,
                                             `${place.list} > li:last-child > .vl-main`, place.head] : []), ...FOCUS_REST);
}

/** The folder picker in a row's star's place while it is open (RowStar). Closed, the row draws its plain star again
 *  and the focus goes to it (or where a row's focus goes when the row went: a removal under "Favourites only"). The
 *  row leaving the list while it is open (the map moved under "Best in view", its sector closed or paged away) ends
 *  it too, so it never opens again by itself when the row comes back (the code review's G1). */
function RowPicker({view, picked}: {view: SpotView; picked: {id: string; row: number}}) {
  const model = view.model, {id, row} = picked;
  // the row's place while it is drawn (its list and index), for the focus once it went
  const place = useRef<ReturnType<typeof placeOf>>(null);
  useEffect(() => {
    const main = document.getElementById(id)?.querySelector(":scope > .vl-main");
    place.current = main ? placeOf(main) : null;
  });
  useEffect(() => () => {
    if (pickerOf.get(view) !== picked) return;  // closed already (onOpen)
    pickerOf.delete(view);
    pickerFocus(id, place.current);
  }, []);
  return <FavouritePicker model={model} line={model.lineAt(row)} icon opened buttonClass="vl-star" buttonTabIndex={-1}
                          onOpen={(open) => {
                            if (open) return;
                            const main = document.getElementById(id)?.querySelector(":scope > .vl-main");
                            if (main) place.current = placeOf(main);
                            changePanels(view, () => { if (pickerOf.get(view) === picked) pickerOf.delete(view); });
                            pickerFocus(id, place.current);
                          }} />;
}

/** A row's star (LinesTable's titles; its name names the row's spot as the row shows it, `label`: "Add B3 to
 *  favourites", the user's G-G a): a press opens the same folder list as the details' star (FavouritePicker, under
 *  the row's right end; the user's gate-2 answer 13 a): the row then draws the picker, mounted open (its Line made
 *  at the press only), until it closes (a folder chosen, Esc, a press elsewhere): the plain star again, the focus on
 *  it where the picker had it; a phone's sheet rises to full for it, as for the details' star. Out of the tab order:
 *  the list's arrows reach it (rowKeys). */
function RowStar({view, row, id, label, sheet}: {view: SpotView; row: number; id: string; label: string; sheet?: PanelProps["sheet"]}) {
  const on = favouriteRows(view).has(row), model = view.model, picked = pickerOf.get(view);
  if (picked && picked.id === id && picked.row === row) return <RowPicker view={view} picked={picked} />;
  return <button type="button" class={cx("vl-star", on && "vl-on")} tabIndex={-1} data-row={row}
                 aria-label={t(on ? "ui.view.star_remove" : "ui.view.star_add", {label})} aria-pressed={on}
                 title={on ? "favourite" : "add to favourites"} onClick={() => {
                   sheet?.setSnap("full");
                   changePanels(view, () => { pickerOf.set(view, {id, row}); });
                 }}>
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

/** A row's list and index, when the element is a row's button (or its star) of the top block or of a sector. */
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
function Row({view, map, padding, sheet, spot, row, id, tab, mark, pick, height}: RowProps) {
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
    {stars && <RowStar view={view} row={row} id={id} label={mark ?? label} sheet={sheet} />}
    {DOOR && <button type="button" class="vl-door" aria-label={t("ui.view.door_label", {label})} title={t("ui.view.door")}>›</button>}
  </li>;
}

/** A heading of a list's column, hidden from a screen reader (a row's values carry their names); `by`: the list is
 *  sorted by it (the kit's "sort" icon before its words, pointing up for smallest first: `asc`). */
export function Head({by, text, asc}: {by: boolean; text: string; asc?: boolean}) {
  return <span class={by ? cx("vl-by", asc && "vl-asc") : undefined} aria-hidden="true">{by && <Icon name="sort" />}{text}</span>;
}

/** The columns' names and their help texts (today's titles of the list's columns: LinesTable), in a row's order. */
function columnHelp(view: SpotView): [string, string][] {
  const out: [string, string][] = [[t("ui.list.col.length"), t("ui.list.col.length_title")],
    view.sort === "hmax" ? [t("ui.list.col.highest"), t("ui.list.col.highest_title")] : [t("ui.list.col.mean"), t("ui.list.col.mean_title")],
    [t("ui.view.col.clear"), t("ui.list.col.clear_title")]];
  if (withAccess(view)) out.push([t("ui.list.col.anchors"), t("ui.list.col.anchors_title")]);
  out.push([t("ui.list.col.lines"), t("ui.view.col.lines_title")]);  // the view's own words (the user's G-F a)
  return out;
}

const COL_HELP = "vl-help-cols";  // the id of the columns' help text

/** The sort key a head of the tree sorts by: its column's (the height's column: the highest point while the list is
 *  sorted by it, else the mean height). */
function headKey(view: SpotView, key: string): ViewSort {
  return key === "h" ? (view.sort === "hmax" ? "hmax" : "hmean") : key as ViewSort;
}

/** A head of the tree (the user's gate-2 answer 12 a): a button that sorts the tree by its column, in the column's
 *  own first direction; on the sorted column it reverses the order. Its name is the column's, the sorted one's with
 *  the order (today's words); the mark as Head's (on the grid's cell, which holds the button). The Sort box and the
 *  direction button follow (the same view). */
function SortHead({view, column, text, sector}: {view: SpotView; column: string; text: string; sector: number}) {
  const key = headKey(view, column), by = view.sort === key;
  const name = by ? text + t(view.desc ? "ui.list.sorted_desc" : "ui.list.sorted_asc") : text;
  const press = (e: Event) => {
    const button = e.currentTarget as HTMLElement;
    const had = document.activeElement === button;  // pressed by the keyboard, or focused by the press
    const top = button.getBoundingClientRect().top;
    // the sector the person sorts from stays open (else the first sector of the new order would be the only one open by
    // itself, and this one, with the pressed head, would close)
    changePanels(view, (s) => { if (sector >= 0 && !s.open.has(sector)) s.open.set(sector, true); });
    if (by) reverse(view); else sortBy(view, key, true);
    // the new order moves the sectors (Preact moves their nodes, which drops a focus inside them): the pressed head
    // keeps its place under the pointer (the code review's G4) and, where it had it, the focus (the design review's
    // G2-F1, as the stepper keeps its own)
    keepHead(`.vl-sec[data-sector="${sector}"] > .vl-cols .vl-head[data-col="${column}"]`, top, had);
  };
  return <span class={cx("vl-hcell", by && "vl-by", by && !view.desc && "vl-asc")}>
    <button type="button" class="vl-head" data-col={column} aria-label={name} aria-pressed={by} onClick={press}>
      {by && <Icon name="sort" />}{text}</button></span>;
}

/** While the page draws the new order (a few frames: the drawing may come after the first), a pressed head
 *  (`selector`) is put back at `top` (the viewport's px it stood at) by its list's scroll, and, with `focus`, given the
 *  focus wherever it fell to the page's body (its node was moved); a focus the person moved elsewhere meanwhile is
 *  left alone. */
function keepHead(selector: string, top: number, focus: boolean) {
  let frames = 6;
  const go = () => {
    const head = document.querySelector<HTMLElement>(selector);
    if (head) {
      const box = head.closest<HTMLElement>(".vl-body, .u-sheet-body"), moved = head.getBoundingClientRect().top - top;
      if (box && Math.abs(moved) >= 1) box.scrollTop += moved;
      const at = document.activeElement;
      if (focus && (!at || at === document.body || !at.isConnected)) head.focus({preventScroll: true});
    }
    if (--frames > 0) requestAnimationFrame(go);
  };
  requestAnimationFrame(go);
}

/** The headings of the rows (each hidden from a screen reader: a row's values carry their names); sorted by the
 *  highest point, that value stands in the mean height's column; `ranked`: the column the list is sorted by is marked
 *  with the sort icon (not for the picks, which are not ranked); `tree`: the tree's heads, buttons that sort the tree
 *  (SortHead: their mark follows the direction; the top block's stay marks, best first); `help`: the columns' info
 *  button in the first cell, above the marks (the top block's heads only; a screen reader reaches it); `stars`: the
 *  rows end with a star. */
function Heads({view, ranked, tree, help, stars, sector = -1}: {view: SpotView; ranked: boolean; tree?: boolean;
                                                                help?: {open: boolean; toggle(): void}; stars: boolean; sector?: number}) {
  const by = !ranked ? "" : view.sort === "len" ? "len" : view.sort === "clr" ? "clr" : view.sort === "n" ? "n" : "h";
  const head = (key: string, text: string) => tree ? <SortHead view={view} column={key} text={text} sector={sector} />
    : <Head by={by === key} text={text} />;
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
  const anchors = t("ui.list.col.anchors");  // (its entry goes with its column in a list under 300 px: view.css)
  return <dl class="vl-helpt" id={COL_HELP}>
    {columnHelp(view).map(([name, text]) => <div key={name} class={name === anchors ? "vl-help-acc" : undefined}>
      <dt>{name}</dt><dd>{text}</dd></div>)}
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
  useEscCloses(help, COL_HELP, () => setHelp(false));
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
      <Heads view={view} ranked tree stars={stars} sector={n} />
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

/** Everything a sector's picture depends on: the lines that pass and their order (the view's version, the sort and
 *  its direction; a change of the favourites counts in the version), whether it is open and how many rows, the
 *  selected spot when it is one of its own, the canvas, and whether the page keeps favourites (the rows' stars: known
 *  after the first draw, and with none saved the version stays). */
function sectorSig({view, map, wide}: PanelProps, sector: SectorRow, k: number): string {
  const ui = panelState(view), sel = view.selected;
  const mine = sel && view.sectorOf(sel.spot) === sector.n ? sel.spot : -1;
  return [view.version, view.sort, view.desc ? 1 : 0, k, isOpen(ui, sector.n, k), limitOf(ui, sector.n), mine, map ? 1 : 0, wide ? 1 : 0,
          view.model.favouritesOn ? 1 : 0, pickerOf.get(view)?.id ?? ""].join("|");
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

/** "All spots": the sort, its direction (the button says the order as today's LinesTable: "Largest first" /
 *  "Smallest first"; a press reverses it, another key starts largest first) and the tree of sectors. */
function Tree(p: PanelProps) {
  const {view} = p, ui = panelState(view), sectors = view.sectors;
  const tight = sectors.some((s, k) => isOpen(ui, s.n, k) &&
    s.spots.slice(0, limitOf(ui, s.n)).some((spot) => tightRow(view, view.shownOf(spot))));
  return <section class="vl-block vl-tree" aria-labelledby="vl-tree-title">
    <div class="vl-block-head"><h3 id="vl-tree-title">{t("ui.view.all_spots")}</h3><span class="u-grow" />
      <label class="vl-sort"><span class="u-small">{t("ui.view.sort_by")}</span>
        <select class="r-sort" value={view.sort} onChange={(e) => sortBy(view, e.currentTarget.value as ViewSort)}>
          {SORTS.map((s) => <option key={s} value={s}>{t(`ui.view.sort.${s}`)}</option>)}</select></label>
      <IconButton icon="sort" label={t(view.desc ? "ui.view.dir_desc" : "ui.view.dir_asc")}
                  class={cx("vl-dir", !view.desc && "vl-asc")} onClick={() => reverse(view)} /></div>
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
  if (!note) return null;  // a new note is brought into view by SpotList (useNoteInView)
  return <div class="vl-lnote" role="status"><Icon name="info" />
    <p class="vl-lnote-text">{note.text}
      {note.action && <>{" "}<button type="button" class="r-link vl-lnote-act" onClick={() => note.onAction?.()}>{note.action}</button></>}</p>
    <IconButton icon="close" label="Close" plain class="vl-lnote-x" onClick={() => {
      model.setNote(null);
      keepFocus(...FOCUS_REST);  // the × goes with the note
    }} />
  </div>;
}

/** A note's place in its scroller (the list's body, a phone's sheet body: neither scrolls the page or the map, which
 *  scrollIntoView would): where the note is not wholly in its view, the scroller puts it at its top (8 px under its
 *  edge); one wholly in view stays where it is. */
function noteIntoView(note: HTMLElement) {
  const box = note.closest<HTMLElement>(".vl-body, .u-sheet-body");
  if (!box || !note.isConnected) return;
  const r = note.getBoundingClientRect(), b = box.getBoundingClientRect();
  if (r.top < b.top || r.bottom > b.bottom) box.scrollTop += r.top - b.top - 8;
}

/** How long a phone's sheet may take to come to rest at its new stop before a note is placed all the same, ms (it
 *  moves in .22 s: ui.css .u-sheet; SpotColumns.tsx waits as long for its own checks). */
const SHEET_REST_MS = 1500;

/** `then` once a phone's sheet rests at a stop above the low one (its drawn height its style's), or after
 *  SHEET_REST_MS; returns what cancels the wait. */
function whenSheetRests(sheet: HTMLElement | null, then: () => void): () => void {
  const started = performance.now();
  let frame = 0;
  const check = () => {
    const target = sheet ? parseFloat(sheet.style.height) : NaN;
    const resting = !sheet || (!sheet.classList.contains("u-peek") && target > 0
                               && Math.abs(sheet.getBoundingClientRect().height - target) < 1);
    if (resting || performance.now() - started > SHEET_REST_MS) then();
    else frame = requestAnimationFrame(check);
  };
  frame = requestAnimationFrame(check);
  return () => cancelAnimationFrame(frame);
}

/** The notes each view has brought into view: a note is placed once (model.ts makes a new object for every note, so
 *  the same text again is a new note; the same object drawn again, or the list drawn again across the phone's width,
 *  is not). */
const notesPlaced = new WeakMap<SpotView, object>();

/** A new note of the model (a link's, a favourite's failure) brought into view where it stands, first in the list
 *  (`root`: the list's body on a desktop, the list in a phone's sheet). Called by SpotList after its own scroll that
 *  follows a selection, so that within one commit the note comes last and wins: a refused save's rollback brings the
 *  note and a new version of the view, which follows the selected row again (the code review 2's F1: the note's
 *  scroll, a child's effect, ran first and the row's undid it). A phone's low sheet rises to half first, and the note
 *  is placed once the sheet rests there (at the low stop its body has no height: the code review 2's L1). */
function useNoteInView(view: SpotView, root: {current: HTMLElement | null}, sheet: PanelProps["sheet"]) {
  const pending = useRef<(() => void) | null>(null);
  useEffect(() => () => pending.current?.(), []);
  useEffect(() => {
    const note = view.model.note, el = root.current?.querySelector<HTMLElement>(".vl-lnote");
    if (!note || !el || notesPlaced.get(view) === note) return;
    notesPlaced.set(view, note);
    pending.current?.();
    pending.current = null;
    if (sheet?.snap === "peek") {
      sheet.setSnap("half");
      pending.current = whenSheetRests(el.closest<HTMLElement>(".u-sheet"), () => { pending.current = null; noteIntoView(el); });
      return;
    }
    noteIntoView(el);
  });
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
 *  every ancestor, the map's too), clear of its block's heads, which stay at the scroller's top (the user's 11 a). */
function scrollToRow(row: HTMLElement) {
  const heads = row.closest(".vl-sec, .vl-topblock")?.querySelector<HTMLElement>(":scope > .vl-cols")?.offsetHeight ?? 0;
  for (let box = row.parentElement; box; box = box.parentElement) {
    const overflow = getComputedStyle(box).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && box.scrollHeight > box.clientHeight) {
      const r = row.getBoundingClientRect(), b = box.getBoundingClientRect(), top = b.top + 8 + heads;
      if (r.top < top) box.scrollTop -= top - r.top;
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
  // after the scroll above: a new note comes last and wins (useNoteInView)
  useNoteInView(view, root, p.sheet);
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
