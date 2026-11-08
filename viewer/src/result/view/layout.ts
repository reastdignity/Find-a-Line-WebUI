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
 *  the panels; cardMin: the card's least height whatever its content (its bar and 120 px of chart; ProfileCard
 *  measures the real one: the profile's head, legend and readout take more); cardShare: its greatest
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

/** Two side panels' limits: each one's least and greatest width, a rail's width, the map's least width. */
export interface PanelLimits { left: [number, number]; right: [number, number]; rail: number; map: number }
/** A side panel as kept: its width and whether it is open. */
export interface PanelState { w: number; open: boolean }
export type PanelSide = "left" | "right";

/** Two panels a window `width` px wide allows (the left and the right of a map): when the map would get less
 *  than `limits.map`, the open panels shrink in proportion to what each has above its least width, then the
 *  right one collapses, then the left; `prefer` (the panel just expanded) collapses the other one first.
 *  Nothing of it is kept. */
export function fitPanels(left: PanelState, right: PanelState, limits: PanelLimits, width: number,
                          prefer: PanelSide | null): {left: Column; right: Column} {
  let leftOpen = left.open, rightOpen = right.open, leftForced = false, rightForced = false;
  const order: PanelSide[] = prefer === "right" ? ["left", "right"] : ["right", "left"];
  const result = (lw: number, rw: number) => ({left: {open: leftOpen, width: lw, forced: leftForced},
                                               right: {open: rightOpen, width: rw, forced: rightForced}});
  for (let guard = 0; guard < 3; guard++) {
    const room = width - limits.map - (leftOpen ? 0 : limits.rail) - (rightOpen ? 0 : limits.rail);
    let lw = left.w, rw = right.w;
    const need = (leftOpen ? lw : 0) + (rightOpen ? rw : 0);
    if (need <= room) return result(lw, rw);
    const spareLeft = leftOpen ? lw - limits.left[0] : 0, spareRight = rightOpen ? rw - limits.right[0] : 0;
    const cut = need - room, spare = spareLeft + spareRight;
    if (cut <= spare) {
      if (spare > 0) { lw -= cut * spareLeft / spare; rw -= cut * spareRight / spare; }
      return result(Math.floor(lw), Math.floor(rw));
    }
    const side = order.find((s) => s === "left" ? leftOpen : rightOpen);
    if (!side) break;
    if (side === "left") { leftOpen = false; leftForced = true; } else { rightOpen = false; rightForced = true; }
  }
  return result(left.w, right.w);
}

/** The widest a panel may be dragged in a window `width` px wide, beside the other as `fit` has it. */
export function maxPanelWidth(side: PanelSide, width: number, fit: {left: Column; right: Column},
                              limits: PanelLimits): number {
  const other = side === "left" ? fit.right : fit.left;
  return Math.max(limits[side][0], Math.min(limits[side][1], width - limits.map - (other.open ? other.width : limits.rail)));
}

/** The result's panels as fitPanels' left and right. */
const RESULT_LIMITS: PanelLimits = {left: LIMITS.list, right: LIMITS.details, rail: LIMITS.rail, map: LIMITS.map};

/** The panels a window `width` px wide allows: when the map would get less than LIMITS.map, the open
 *  panels shrink in proportion to what each has above its minimum, then the details collapse, then the
 *  list; `prefer` (the panel just expanded) collapses the other one first. Nothing of it is kept. */
export function fitColumns(layout: Layout, width: number,
                           prefer: "list" | "details" | null): {list: Column; details: Column} {
  const fit = fitPanels(layout.list, layout.details, RESULT_LIMITS, width,
                        prefer === "list" ? "left" : prefer === "details" ? "right" : null);
  return {list: fit.left, details: fit.right};
}

/** The widest a panel may be dragged in a window `width` px wide, beside the other as `fit` has it. */
export function maxColumnWidth(side: "list" | "details", width: number,
                               fit: {list: Column; details: Column}): number {
  return maxPanelWidth(side === "list" ? "left" : "right", width, {left: fit.list, right: fit.details}, RESULT_LIMITS);
}

// The highline layer's panels (app/c/LayerPage: the filters on the left, the histograms on the right of the map):
// their own limits and kept value, under their own key; the same fitting

/** What the layer keeps (localStorage "findaline.layer.layout"): each panel's width and whether it is open. */
export interface LayerLayout { v: 1; left: PanelState; right: PanelState }
/** left: 320-560 px (the filters' two columns fit from 320); right: 300-640 (620 holds two charts of 288 px a row). */
export const LAYER_LIMITS: PanelLimits = {left: [320, 560], right: [300, 640], rail: 36, map: 360};
export const DEFAULT_LAYER_LAYOUT: LayerLayout = {v: 1, left: {w: 400, open: true}, right: {w: 620, open: true}};
export const LAYER_LAYOUT_KEY = "findaline.layer.layout";

/** A kept value of the layer's panels made safe (as sanitize). */
export function sanitizeLayer(value: unknown): LayerLayout {
  const d: LayerLayout = {v: 1, left: {...DEFAULT_LAYER_LAYOUT.left}, right: {...DEFAULT_LAYER_LAYOUT.right}};
  const v = value as any;
  if (!v || typeof v !== "object" || v.v !== 1) return d;
  for (const side of ["left", "right"] as const) {
    const part = v[side] && typeof v[side] === "object" ? v[side] : {};
    const [lo, hi] = LAYER_LIMITS[side];
    if (typeof part.w === "number" && isFinite(part.w)) d[side].w = clamp(Math.round(part.w), lo, hi);
    d[side].open = part.open !== false;
  }
  return d;
}

/** The layer's kept panels, or the defaults. */
export function loadLayerLayout(): LayerLayout {
  try {
    const text = localStorage.getItem(LAYER_LAYOUT_KEY);
    return sanitizeLayer(text === null ? null : JSON.parse(text));
  } catch {
    return sanitizeLayer(null);
  }
}

/** Keeps the layer's panels (nothing happens without storage). */
export function saveLayerLayout(layout: LayerLayout): void {
  try { localStorage.setItem(LAYER_LAYOUT_KEY, JSON.stringify(sanitizeLayer(layout))); } catch { /* not kept */ }
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
