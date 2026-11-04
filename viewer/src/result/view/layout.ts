// The layout of a result on a desktop (C's result: the list on the left, the details on the right, the
// profile card over the bottom of the map) as pure functions: what is kept in localStorage, how the side
// panels fit a window and where the card's edges go. The state on top of them is the caller's; nothing
// here touches the DOM. The rules are the accepted mockup's (DEF, LIM, sane, fit, Mock.insets, setInset).

/** What is kept (localStorage "findaline.layout"): the panels' widths and whether they are open, the
 *  profile card's height, whether it is folded, and its left and right insets in the map. */
export interface Layout {
  v: 1;
  list: {w: number; open: boolean};
  details: {w: number; open: boolean};
  profile: {h: number; folded: boolean; l: number; r: number};
}

export const DEFAULT_LAYOUT: Layout = {v: 1, list: {w: 340, open: true}, details: {w: 380, open: true},
                                       profile: {h: 260, folded: false, l: 12, r: 12}};

/** list, details: the panels' widths; rail: a collapsed panel's width; map: the map's least width beside
 *  the panels; cardMin: the card's least height (its bar and 120 px of chart); cardShare: its greatest
 *  height as a share of the map's; low: a map lower than that opens the card folded; cardWidthMin: the
 *  card's least width (or the map's less two insets); inset: the card's default and least inset. */
export const LIMITS = {list: [260, 560] as [number, number], details: [300, 600] as [number, number], rail: 36,
                       map: 360, cardMin: 160, cardShare: 0.7, low: 420, cardWidthMin: 360, inset: 12};

/** The least height of the profile's chart in the card (Profile.tsx in fill mode). */
export const CHART_MIN = 120;
/** A splitter's keyboard steps (px): an arrow, Shift and an arrow. */
export const STEP = 16, BIG_STEP = 64;
export const LAYOUT_KEY = "findaline.layout";
/** The greatest kept height and insets (the mockup's): larger values are clamped, not refused. */
const MAX_HEIGHT = 2000, MAX_INSET = 4000;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const copy = (layout: Layout): Layout => ({v: 1, list: {...layout.list}, details: {...layout.details},
                                           profile: {...layout.profile}});

/** A kept value made safe: anything that is not a layout of version 1 gives the defaults, and each field
 *  is clamped (a number out of range) or replaced by its default (not a finite number). */
export function sanitize(value: unknown): Layout {
  const d = copy(DEFAULT_LAYOUT);
  const v = value as any;
  if (!v || typeof v !== "object" || v.v !== 1) return d;
  const num = (x: unknown, lo: number, hi: number, fallback: number) =>
    typeof x === "number" && isFinite(x) ? clamp(Math.round(x), lo, hi) : fallback;
  const part = (name: string) => v[name] && typeof v[name] === "object" ? v[name] : {};
  const list = part("list"), details = part("details"), profile = part("profile");
  d.list.w = num(list.w, LIMITS.list[0], LIMITS.list[1], d.list.w);
  d.list.open = list.open !== false;
  d.details.w = num(details.w, LIMITS.details[0], LIMITS.details[1], d.details.w);
  d.details.open = details.open !== false;
  d.profile.h = num(profile.h, LIMITS.cardMin, MAX_HEIGHT, d.profile.h);
  d.profile.folded = profile.folded === true;
  d.profile.l = num(profile.l, LIMITS.inset, MAX_INSET, d.profile.l);
  d.profile.r = num(profile.r, LIMITS.inset, MAX_INSET, d.profile.r);
  return d;
}

/** The kept layout, or the defaults (nothing kept, a bad value, no storage). */
export function loadLayout(): Layout {
  try {
    const text = localStorage.getItem(LAYOUT_KEY);
    return sanitize(text === null ? null : JSON.parse(text));
  } catch {
    return copy(DEFAULT_LAYOUT);
  }
}

/** Keeps the layout (nothing happens without storage: a private window, blocked site data). */
export function saveLayout(layout: Layout): void {
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(sanitize(layout))); } catch { /* not kept */ }
}

/** A side panel in a window: open (or a rail), its width (shrunk to fit when open; the kept one when
 *  collapsed, for its splitter's value), and whether the window collapsed it (`forced`: never kept). */
export interface Column { open: boolean; width: number; forced: boolean }

/** The panels a window `width` px wide allows: when the map would get less than LIMITS.map, the open
 *  panels shrink in proportion to what each has above its minimum, then the details collapse, then the
 *  list; `prefer` (the panel just expanded) collapses the other one first. Nothing of it is kept. */
export function fitColumns(layout: Layout, width: number,
                           prefer: "list" | "details" | null): {list: Column; details: Column} {
  let listOpen = layout.list.open, detailsOpen = layout.details.open, listForced = false, detailsForced = false;
  const order: ("list" | "details")[] = prefer === "details" ? ["list", "details"] : ["details", "list"];
  const result = (lw: number, dw: number) => ({list: {open: listOpen, width: lw, forced: listForced},
                                               details: {open: detailsOpen, width: dw, forced: detailsForced}});
  for (let guard = 0; guard < 3; guard++) {
    const room = width - LIMITS.map - (listOpen ? 0 : LIMITS.rail) - (detailsOpen ? 0 : LIMITS.rail);
    let lw = layout.list.w, dw = layout.details.w;
    const need = (listOpen ? lw : 0) + (detailsOpen ? dw : 0);
    if (need <= room) return result(lw, dw);
    const spareList = listOpen ? lw - LIMITS.list[0] : 0, spareDetails = detailsOpen ? dw - LIMITS.details[0] : 0;
    const cut = need - room, spare = spareList + spareDetails;
    if (cut <= spare) {
      if (spare > 0) { lw -= cut * spareList / spare; dw -= cut * spareDetails / spare; }
      return result(Math.floor(lw), Math.floor(dw));
    }
    const side = order.find((s) => s === "list" ? listOpen : detailsOpen);
    if (!side) break;
    if (side === "list") { listOpen = false; listForced = true; } else { detailsOpen = false; detailsForced = true; }
  }
  return result(layout.list.w, layout.details.w);
}

/** The widest a panel may be dragged in a window `width` px wide, beside the other as `fit` has it. */
export function maxColumnWidth(side: "list" | "details", width: number,
                               fit: {list: Column; details: Column}): number {
  const other = side === "list" ? (fit.details.open ? fit.details.width : LIMITS.rail)
    : (fit.list.open ? fit.list.width : LIMITS.rail);
  return Math.max(LIMITS[side][0], Math.min(LIMITS[side][1], width - LIMITS.map - other));
}

/** The card's least width in a map `mapWidth` px wide. */
export function cardWidthMin(mapWidth: number): number {
  return Math.min(LIMITS.cardWidthMin, mapWidth - 2 * LIMITS.inset);
}

/** The card's left and right insets in a map `mapWidth` px wide: the kept ones, both narrowed in
 *  proportion to what each has above LIMITS.inset when the card would be narrower than its least width
 *  (not kept). */
export function cardInsets(layout: Layout, mapWidth: number): [number, number] {
  const least = cardWidthMin(mapWidth);
  let l = layout.profile.l, r = layout.profile.r;
  const over = least - (mapWidth - l - r);
  if (over > 0) {
    const spareL = l - LIMITS.inset, spareR = r - LIMITS.inset, spare = spareL + spareR || 1;
    l -= over * spareL / spare;
    r -= over * spareR / spare;
  }
  return [Math.round(Math.max(LIMITS.inset, l)), Math.round(Math.max(LIMITS.inset, r))];
}

/** Moves one edge of the card to `inset` while the other stays where `from` (cardInsets of the map) has
 *  it: the moved inset is kept at least the card's least width from the other edge, and both are kept. */
export function moveCardEdge(layout: Layout, edge: "l" | "r", inset: number, from: [number, number],
                             mapWidth: number): Layout {
  const least = cardWidthMin(mapWidth), next = copy(layout);
  if (edge === "l") {
    next.profile.l = Math.round(clamp(inset, LIMITS.inset, mapWidth - from[1] - least));
    next.profile.r = from[1];
  } else {
    next.profile.r = Math.round(clamp(inset, LIMITS.inset, mapWidth - from[0] - least));
    next.profile.l = from[0];
  }
  return next;
}

/** The card's greatest height in a map `mapHeight` px high. */
export function cardMaxHeight(mapHeight: number): number {
  return Math.max(LIMITS.cardMin, Math.round(mapHeight * LIMITS.cardShare));
}

/** The card's height (unfolded) in a map `mapHeight` px high: the kept one within
 *  [LIMITS.cardMin, LIMITS.cardShare · mapHeight]. */
export function cardHeight(layout: Layout, mapHeight: number): number {
  return clamp(layout.profile.h, LIMITS.cardMin, cardMaxHeight(mapHeight));
}

/** A map so low that the card opens folded. */
export function isLowMap(mapHeight: number): boolean {
  return mapHeight < LIMITS.low;
}
