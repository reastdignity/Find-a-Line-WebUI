// What the result view's panels keep (docs/line-volume/spec-view.md B.2 items 12-13, B.4): in the browser's
// storage only the list's sort, its direction (step 3d's P4: an optional field; a value kept before it reads as the
// key's own first direction) and whether the hint is shown (key "findaline.view.v1"; storage blocked: nothing is
// kept, the page works); per view, for as long as its run is open, what is unfolded in the panels (the sectors
// open, their pages, "Why so many?", the filter being edited, the pointer last used). The frame draws the panels
// again when the window crosses the phone's width (another tree, the same SpotView), so this state hangs on the
// view, not on a component. "Top level only" is neither: it is the view's own (SpotView.topOnly), on at every
// start. Plain TypeScript without the DOM's elements, so its rules run under Node (tests/test_view_list_units.py).

import type { SpotView, ViewSort } from "../spots";

export const VIEW_KEY = "findaline.view.v1";
export const SORTS: ViewSort[] = ["hmean", "clr", "len", "hmax", "n"];
/** Rows of a sector's first page (a selection pages a sector in steps of it), and what "Show more" adds. */
export const PAGE = 20, MORE = 40;

/** Each key's first direction: largest first (true), as today's list (list.ts SORT_KEYS' `desc`); another key
 *  chosen starts in it. */
export const FIRST_DESC: Record<ViewSort, boolean> = {hmean: true, clr: true, len: true, hmax: true, n: true};

export interface Kept { sort: ViewSort; hint: boolean; desc: boolean }
const DEFAULTS: Kept = {sort: "hmean", hint: true, desc: FIRST_DESC.hmean};

/** What a stored text keeps (anything else, or a part that is not known: the default; no direction, or one that is
 *  not known: the kept key's first direction). */
export function parseKept(text: string | null | undefined): Kept {
  let found: unknown = null;
  try {
    found = text ? JSON.parse(text) : null;
  } catch { /* not JSON: nothing kept */ }
  const o = found && typeof found === "object" ? found as Record<string, unknown> : {};
  const sort = SORTS.includes(o.sort as ViewSort) ? o.sort as ViewSort : DEFAULTS.sort;
  return {sort, hint: typeof o.hint === "boolean" ? o.hint : DEFAULTS.hint,
          desc: typeof o.desc === "boolean" ? o.desc : FIRST_DESC[sort]};
}

/** The kept sort, direction and hint. */
export function kept(): Kept {
  try {
    return parseKept(localStorage.getItem(VIEW_KEY));
  } catch {
    return {...DEFAULTS};  // storage blocked
  }
}

/** Keep the sort, its direction and the hint: the direction only when it is not the key's first (so a value is
 *  written as before step 3d while the tree is largest first). */
export function keep(k: Kept) {
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify(k.desc === FIRST_DESC[k.sort] ? {sort: k.sort, hint: k.hint}
                                                    : {sort: k.sort, hint: k.hint, desc: k.desc}));
  } catch { /* storage blocked: nothing is kept */ }
}

/** The rows a sector shows after one of them, at place `rank` from 0, was selected: its page of PAGE rows is in,
 *  never fewer than `limit`. */
export function pageFor(rank: number, limit: number): number {
  return rank >= limit ? Math.ceil((rank + 1) / PAGE) * PAGE : limit;
}

/** Does the hint speak of a finger ("Press and hold"): always in the phone layout; else by the pointer last
 *  pressed (a mouse: no; a finger or a pen: yes), before any press by the device (`coarse`: pointer: coarse). */
export function byFinger(wide: boolean, pressedBy: string, coarse: boolean): boolean {
  return !wide || (pressedBy ? pressedBy !== "mouse" : coarse);
}

/** What the panels of one view hold while its run is open. */
export interface PanelState {
  /** A sector (its index from 0) opened or closed by the user or a selection; not there: the first shown is open. */
  open: Map<number, boolean>;
  /** The rows a sector shows by the user's "Show more" (not there: PAGE). */
  limit: Map<number, number>;
  /** The rows a sector shows because the selected spot's row lies beyond them: they go back when the selection
   *  leaves the sector or ends. */
  paged: Map<number, number>;
  /** What opened "Lines from here" from the details (the selector of its button), for the focus when it closes. */
  fanFrom: string | null;
  /** The hint is shown (kept). */
  hint: boolean;
  /** "Why so many?" is open. */
  why: boolean;
  /** The main filter being edited, or "more": More filters. */
  editing: "len" | "clr" | "height" | "more" | null;
  /** The pointer type of the last press on the page ("": none yet). */
  pressedBy: string;
  /** The spot whose selection the list has followed (its sector opened and paged). */
  followed: number | null;
  /** The list's order when it followed (the sort, its direction and the lines that pass): another order is followed
   *  again. */
  followedOrder: string;
  /** The list still has to scroll to the followed spot's row. */
  scroll: boolean;
  /** That scroll follows another spot (a phone's sheet goes to its top only then, not for a new order). */
  scrollNew: boolean;
  /** The list's row whose press (a click, Enter) made the selection, and its spot: while that spot stays selected the
   *  list keeps that row in view, not the spot's "Best in view" row (the planner's decision of 2026-11-18); a
   *  selection's end forgets it. */
  pressed: {id: string; spot: number} | null;
  /** The next follow of a new order pages the selected spot's sector but does not scroll the list: the direction's
   *  press keeps its button where it is (the final design review's F4). */
  still: boolean;
}

interface Held { state: PanelState; listeners: Set<() => void> }
const held = new WeakMap<SpotView, Held>();

function holdOf(view: SpotView): Held {
  let h = held.get(view);
  if (!h) {
    const k = kept();
    h = {state: {open: new Map(), limit: new Map(), paged: new Map(), fanFrom: null, hint: k.hint, why: false, editing: null,
                 pressedBy: "", followed: null, followedOrder: "", scroll: false, scrollNew: false, pressed: null, still: false},
         listeners: new Set()};
    held.set(view, h);
    // the kept sort and direction, once per view and before anything is drawn from its order (the B numbers follow
    // the sort, the tree both)
    if (k.sort !== view.sort) view.setSort(k.sort);
    if (k.desc !== view.desc) view.setDesc(k.desc);
  }
  return h;
}

/** The panels' state of a view (made at its first use, which also gives the view its kept sort). */
export function panelState(view: SpotView): PanelState {
  return holdOf(view).state;
}

/** Change the panels' state of a view and draw its panels again. */
export function changePanels(view: SpotView, change: (s: PanelState) => void) {
  const h = holdOf(view);
  change(h.state);
  h.listeners.forEach((f) => f());
}

/** Call `f` after every change of a view's panel state; returns the function that stops it. */
export function watchPanels(view: SpotView, f: () => void): () => void {
  const h = holdOf(view);
  h.listeners.add(f);
  return () => { h.listeners.delete(f); };
}

/** Sort the list of spots and keep the choice (written only when it changes): another key starts in its own first
 *  direction (today's LinesTable). */
export function sortBy(view: SpotView, sort: ViewSort) {
  const hint = holdOf(view).state.hint;  // first: a view's first use of its panel state gives it the kept sort
  if (sort === view.sort) return;
  view.setSort(sort);
  view.setDesc(FIRST_DESC[sort]);
  keep({sort, hint, desc: view.desc});
}

/** Reverse the tree's direction ("Largest first" / "Smallest first") and keep it; the list follows a selection into
 *  the new order without scrolling (`still`: the button stays under the pointer). */
export function reverse(view: SpotView) {
  const state = holdOf(view).state, hint = state.hint;  // first: the view's kept sort and direction
  state.still = !!view.selected;
  view.setDesc(!view.desc);
  keep({sort: view.sort, hint, desc: view.desc});
}

/** Show or hide the hint and keep the choice (written only when it changes). */
export function showHint(view: SpotView, on: boolean) {
  if (holdOf(view).state.hint === on) return;
  changePanels(view, (s) => { s.hint = on; });
  keep({sort: view.sort, hint: on, desc: view.desc});
}

/** The rows a sector shows: the user's pages ("Show more"), or more while the selected spot's row needs them. */
export function limitOf(s: PanelState, sector: number): number {
  return Math.max(s.limit.get(sector) ?? PAGE, s.paged.get(sector) ?? 0);
}

/** "Show more" of a sector: the user's own pages grow by MORE from the user's own (never from the pages a selection
 *  opened, which still go back when it ends); while a selection has paged the sector further, those pages grow by
 *  MORE too, so that the press shows 40 more rows now. */
export function showMore(s: PanelState, sector: number) {
  const own = s.limit.get(sector) ?? PAGE, paged = s.paged.get(sector);
  s.limit.set(sector, own + MORE);
  if (paged !== undefined && paged > own) s.paged.set(sector, paged + MORE);
}

/** Is a sector open: as the user or a selection left it, else the first one shown (`k` 0). */
export function isOpen(s: PanelState, sector: number, k: number): boolean {
  return s.open.get(sector) ?? k === 0;
}

/** The list follows a selection: the selected spot's sector opens (once per selected spot: the user may close it
 *  again) and shows pages until its row; again when the list's order changed under the selection (another sort,
 *  other lines passing). The pages a selection needed go back when it leaves the sector or ends; the user's own
 *  ("Show more") stay. True when the list has to scroll to the row. */
export function follow(s: PanelState, view: SpotView): boolean {
  const sel = view.selected;
  if (!sel) {
    s.followed = null;
    s.pressed = null;
    s.scroll = false;
    s.paged.clear();
    return false;
  }
  const order = `${view.sort}|${view.desc}|${view.version}`, same = s.followed === sel.spot;
  if (same && s.followedOrder === order) return s.scroll;
  const n = view.sectorOf(sel.spot), sector = view.sectors.find((x) => x.n === n);
  if (!same) s.open.set(n, true);
  if (!same && s.pressed?.spot !== sel.spot) s.pressed = null;  // another spot, not by that row's press
  s.followed = sel.spot;
  s.followedOrder = order;
  s.scroll = !(same && s.still);
  s.still = false;
  s.scrollNew = !same;
  s.paged.clear();
  const mine = s.limit.get(n) ?? PAGE, needed = sector ? pageFor(sector.spots.indexOf(sel.spot), mine) : mine;
  if (needed > mine) s.paged.set(n, needed);
  return s.scroll;
}
