// What the result view's panels keep (docs/line-volume/spec-view.md B.2 items 12-13, B.4): in the browser's
// storage only the list's sort and whether the hint is shown (key "findaline.view.v1"; storage blocked: nothing is
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

export interface Kept { sort: ViewSort; hint: boolean }
const DEFAULTS: Kept = {sort: "hmean", hint: true};

/** What a stored text keeps (anything else, or a part that is not known: the default). */
export function parseKept(text: string | null | undefined): Kept {
  let found: unknown = null;
  try {
    found = text ? JSON.parse(text) : null;
  } catch { /* not JSON: nothing kept */ }
  const o = found && typeof found === "object" ? found as Record<string, unknown> : {};
  return {sort: SORTS.includes(o.sort as ViewSort) ? o.sort as ViewSort : DEFAULTS.sort,
          hint: typeof o.hint === "boolean" ? o.hint : DEFAULTS.hint};
}

/** The kept sort and hint. */
export function kept(): Kept {
  try {
    return parseKept(localStorage.getItem(VIEW_KEY));
  } catch {
    return {...DEFAULTS};  // storage blocked
  }
}

/** Keep the sort and the hint. */
export function keep(k: Kept) {
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify({sort: k.sort, hint: k.hint}));
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
  /** The rows a sector shows (not there: PAGE). */
  limit: Map<number, number>;
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
  /** The list still has to scroll to the followed spot's row. */
  scroll: boolean;
}

interface Held { state: PanelState; listeners: Set<() => void> }
const held = new WeakMap<SpotView, Held>();

function holdOf(view: SpotView): Held {
  let h = held.get(view);
  if (!h) {
    const k = kept();
    h = {state: {open: new Map(), limit: new Map(), hint: k.hint, why: false, editing: null, pressedBy: "",
                 followed: null, scroll: false},
         listeners: new Set()};
    held.set(view, h);
    // the kept sort, once per view and before anything is drawn from its order (the B numbers follow it)
    if (k.sort !== view.sort) view.setSort(k.sort);
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

/** Sort the list of spots and keep the choice. */
export function sortBy(view: SpotView, sort: ViewSort) {
  view.setSort(sort);
  keep({sort, hint: holdOf(view).state.hint});
}

/** Show or hide the hint and keep the choice. */
export function showHint(view: SpotView, on: boolean) {
  changePanels(view, (s) => { s.hint = on; });
  keep({sort: view.sort, hint: on});
}

/** Is a sector open: as the user or a selection left it, else the first one shown (`k` 0). */
export function isOpen(s: PanelState, sector: number, k: number): boolean {
  return s.open.get(sector) ?? k === 0;
}

/** The list follows a selection: the selected spot's sector opens and pages until its row (once per selected spot:
 *  the user may close the sector again); true when the list has to scroll to the row. Nothing selected: forgotten. */
export function follow(s: PanelState, view: SpotView): boolean {
  const sel = view.selected;
  if (!sel) {
    s.followed = null;
    s.scroll = false;
    return false;
  }
  if (s.followed === sel.spot) return s.scroll;
  s.followed = sel.spot;
  s.scroll = true;
  const n = view.sectorOf(sel.spot), sector = view.sectors.find((x) => x.n === n);
  s.open.set(n, true);
  if (sector) s.limit.set(n, pageFor(sector.spots.indexOf(sel.spot), s.limit.get(n) ?? PAGE));
  return true;
}
