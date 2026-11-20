// The result view's frame (docs/line-volume/spec-view.md B.2: "Today's page stays as the frame"), beside today's
// page (ResultColumns.tsx, which opens it only behind the flag: viewWanted, opensView): a header (the caller's way
// back, the run's name and date without the line count (the user's W8), the caller's actions, then the run's:
// Measure, Compare, Share, Download, RunActions as on today's page) and three columns: the list | the map with its
// bar (MapBar) and the selected line's profile in a card over the map's bottom (ProfileCard, today's) | the details;
// the side panels' edges, rails and kept widths are today's (ui/SidePanel, layout.ts). While the card is open the
// map's foot is the short one (MapBar `short`: the legend behind "Legend", the run's data credits behind theirs) and
// the card stands on the credits' line, the scale above it (the user's 4 a; corners.ts), its height not "in view"
// (the canvas's covered term). On phones (< 768 px) the map with a sheet holding the hint, the details and the list;
// the run's actions are icons in the top bar's pill (no Compare, as today). The columns' contents are slots
// (SpotPanels.tsx: PANELS), filled by the view's panels; the frame owns the Leaflet map (base layers with the run's
// orthophoto, the shore's and the coarser terrain's overlays, the layers button with the kit's icon, the scale, the
// run's data credits), the canvas (SpotMap), the toast, the run's actions, the profile's card, where the table of
// spots stands, and Esc.
//
// Measuring (RunActions' Measure on the canvas): on a desktop the tip stands beside "Cancel"; on a phone the sheet
// goes low and the tip is the status line's first line (MapBar `tip`) while the canvas holds the map still. The
// measured line, Measure's or a link's outside the run (viewlink.ts), is kept here across the phone's width
// (SpotColumns' `measured`), drawn on the canvas, its profile in the card (a desktop) or first in the sheet's body at
// half (a phone); a link's measured line is fitted into the map, Measure's only where it is not in sight; its close
// clears it (and model.measuredLink). The route's line (`line`, `nav`) opens in the view and the selection goes into
// the hash (`hashOf`): viewlink.ts. On a phone a selected line that the sheet (or the data credits band above it)
// covers when it moves is brought back into sight (useSheetKeeps), and a link that ends in a note raises the sheet to
// half (also when the window crossed the phone's width while the link's line was measured).
//
// For tests and the console: window.FINDALINE_MAP is the Leaflet map (as on today's page) and
// window.FINDALINE_VIEW = {view, map} (the SpotView and the SpotMap) is set once the view was drawn for the first
// time, its `measured` the frame's measured line (null: none); window.FINDALINE_RESULT is not set in this view (its
// `view` is a ResultMap).

import L from "leaflet";
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, IconButton, Sheet, type Snap } from "../../ui/components";
import { SidePanel, useWidthOf } from "../../ui/SidePanel";
import { ICONS, type IconName } from "../../ui/icons";
import { baseLayers } from "../../baselayers";
import { Layers } from "../../layersControl";
import { addShore } from "../../shoreLayer";
import { addCoarser } from "../../coarserLayer";
import { t } from "../../i18n";
import { measure } from "../../perf";
import { when } from "../../time";
import type { Line, RunData } from "../../types";
import type { ResultModel } from "../model";
import type { Padding } from "../ResultMap";
import { SpotMap } from "../SpotMap";
import { createSpotView, viewOf, type SpotChoice, type SpotView } from "../spots";
import { count, cx } from "./common";
import { useCornersAboveCard, useCornersAboveSheet } from "./corners";
import { useRunCredits } from "./credits";
import type { Area } from "./LineChooser";
import { DEFAULT_LAYOUT, LIMITS, fitColumns, maxColumnWidth, type Column, type Layout } from "./layout";
import { MapBar } from "./MapBar";
import { ProfileCard } from "./ProfileCard";
import { ProfileDock } from "./ProfileDock";
import type { BackAction, ResultColumnsProps } from "./ResultColumns";
import { RunActions, useMeasureTip, type RunActionsMap } from "./RunActions";
import { PANELS, useSpotView, type PanelProps, type SpotPanels } from "./SpotPanels";
import { useLayout, type LayoutState } from "./useLayout";
import { useViewLink } from "./viewlink";
import "./columns.css";
import "./mapbar.css";

// --- the flag ---

const VIEW_KEY = "findaline.view";

/** Is the result view asked for in this browser: `?view=b` in the address asks for it and is remembered
 *  (localStorage "findaline.view" = "b"), `?view=today` ends it; the address decides this load also where the
 *  storage is blocked (nothing is remembered then). */
export function viewWanted(): boolean {
  let asked: string | null = null;
  try {
    asked = new URLSearchParams(location.search).get("view");
  } catch { /* no address to read */ }
  try {
    if (asked === "b") localStorage.setItem(VIEW_KEY, "b");
    else if (asked === "today") localStorage.removeItem(VIEW_KEY);
  } catch { /* storage blocked: only this load */ }
  if (asked === "b" || asked === "today") return asked === "b";
  try {
    return localStorage.getItem(VIEW_KEY) === "b";
  } catch {
    return false;
  }
}

/** Does this run open in the result view: the flag is set and the run can be shown there (spots.ts viewOf: the
 *  view's columns, its spots in runs, a grid the fit reaches). A run that cannot opens in today's page, and the
 *  console says why. */
export function opensView(data: RunData): boolean {
  if (!viewWanted()) return false;
  const base = viewOf(data);
  if (typeof base !== "string") return true;
  console.warn(`Find-a-Line: the result view cannot show the run ${data.run.id} (${base}); today's page opens.`);
  return false;
}

// --- the frame ---

export interface SpotColumnsProps extends ResultColumnsProps {
  /** The run's model, built without the grouping (ResultOptions.ungrouped) on a run that opensView accepts. */
  model: ResultModel;
  data: RunData;
  /** What stands in the slots (default: SpotPanels.tsx PANELS). */
  panels?: SpotPanels;
}

interface FrameProps extends SpotColumnsProps {
  view: SpotView;
  panels: SpotPanels;
  /** The measured line: Measure's, or a line outside the run that a link named (viewlink.ts); null: none. */
  measured: Line | null;
  onMeasured(l: Line | null): void;
}

/** A press's choice of the spots it reached about as near, at its point in the viewport. */
type ChoiceAt = {choices: SpotChoice[]; at: {x: number; y: number}};

/** The canvas with the members the frame calls besides SpotMap's of step 3b (SESSION B1/interface.md: Measure's
 *  RunActionsMap, a measured line's zoom and drawing, the card's covered term). Optional until the canvas has them
 *  (the catch-up merge of view-3c drops the Partial). */
type FrameMap = SpotMap & Partial<RunActionsMap & {
  zoomToLine(line: Line, padding?: Padding): void;
  setCovered(px: number): void;
  drawMeasured(line: Line | null): void;
}>;

/** The canvas as Measure and Compare need it, or null where it cannot measure (Measure then shows no button). */
const measureOf = (c: FrameMap | null): RunActionsMap | null =>
  c && typeof c.startMeasure === "function" ? c as RunActionsMap : null;

const TOAST_MS = 3200;  // how long a message of the map stays

/** The map of the view: base layers (with the run's orthophoto), zoom in quarter steps (half a step for one notch
 *  of the wheel: measured in Edge on Windows, where Leaflet reads a notch as 50 px, 90 px per level give 0.5; 150
 *  gave a quarter, Leaflet's own 60 three quarters), the layers button (the kit's icon, as the place map's:
 *  layersControl.ts) with the shore's and the coarser terrain's overlays, the scale, and the canvas (SpotMap) fitted
 *  to the run's lines. */
function useSpotMap(view: SpotView, data: RunData, ortho: ResultColumnsProps["ortho"], frame: {
  padding(): Padding; free(): Padding; obstacles(): DOMRect[]; onChoose(choice: ChoiceAt): void; onToast(text: string): void;
  phone?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const [canvas, setCanvas] = useState<FrameMap | null>(null);
  const latest = useRef(frame);
  latest.current = frame;
  useEffect(() => {
    const model = view.model, start = performance.now();
    const leaflet = L.map(ref.current!, {center: data.center, zoom: 15, maxZoom: data.max_zoom, zoomSnap: 0.25,
                                         zoomDelta: 0.5, wheelPxPerZoomLevel: 90, zoomControl: false});
    (window as any).FINDALINE_MAP = leaflet;  // for tests and the browser console
    // the zoom buttons with the kit's icons, not the characters "+" and "−" (R9); first in the top left corner, as
    // Leaflet's own (static markup: the CSP allows it)
    const icon = (name: "plus" | "minus") => `<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
    L.control.zoom({zoomInText: icon("plus"), zoomOutText: icon("minus")}).addTo(leaflet);
    const layers = baseLayers(ortho ? ortho(data) : data.ortho, data.max_zoom);
    Object.values(layers)[0].addTo(leaflet);
    const overlays: Record<string, L.Layer> = {};
    addShore(leaflet, data.shore, overlays);  // the uncertain shore: its overlay, its metres in view
    model.setCoarserFit(addCoarser(leaflet, data.terrain_sources, overlays)?.fit ?? null);
    new Layers(layers, overlays, {position: "topright"}).addTo(leaflet);
    // on a phone at the right, above the credits: the bar's foot stands beside it at the left (MapBar)
    L.control.scale({position: frame.phone ? "bottomright" : "bottomleft"}).addTo(leaflet);
    let made: SpotMap | null = null, drawn = false;
    const spotMap = new SpotMap(leaflet, view, {
      onChoose: (choices, at) => {
        const box = leaflet.getContainer().getBoundingClientRect();
        latest.current.onChoose({choices, at: {x: box.left + at.x, y: box.top + at.y}});
      },
      onToast: (text) => latest.current.onToast(text),
      obstacles: () => latest.current.obstacles(),
      free: () => latest.current.free(),
      padding: () => latest.current.padding(),
      phone: frame.phone,
      onDrawn: () => {
        if (drawn || !made) return;
        drawn = true;
        (window as any).FINDALINE_VIEW = {view, map: made};  // the view is drawn: tests and tools wait for it
        measure("fal:view:first", start);
      },
    });
    made = spotMap;
    spotMap.fitArea(latest.current.padding());
    spotMap.refresh();  // also when the fit did not move the map
    setMap(leaflet);
    setCanvas(spotMap);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => leaflet.invalidateSize()) : null;
    observer?.observe(ref.current!);
    return () => {
      observer?.disconnect();
      model.setCoarserFit(null);
      spotMap.destroy();
      if ((window as any).FINDALINE_VIEW?.map === spotMap) delete (window as any).FINDALINE_VIEW;
      leaflet.remove();
    };
  }, [view]);
  return {ref, map, canvas};
}

/** The table of spots is closed (`close`) by the map moving and by any change of the view (a selection, a filter). */
function useChoiceCloses(view: SpotView, map: L.Map | null, close: () => void) {
  useEffect(() => {
    map?.on("movestart zoomstart", close);
    const stop = view.subscribe(close);
    return () => { map?.off("movestart zoomstart", close); stop(); };
  }, [view, map]);
}

/** Esc, in the page's one order: the table of spots, then (not while typing or in a dialog) "Lines from here",
 *  then the selection (SpotView.escape). */
function useEscape(view: SpotView, choice: ChoiceAt | null, close: () => void) {
  const open = useRef(choice);
  open.current = choice;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (open.current) { close(); return; }
      const at = document.activeElement;
      if (at && at.closest("input, select, textarea, [role=dialog], [role=alertdialog]")) return;
      view.escape();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [view]);
}

/** A message of the map, shown for a while. */
function useToast(): [string, (text: string) => void] {
  const [toast, setToast] = useState("");
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  return [toast, (text) => {
    setToast(text);
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(""), TOAST_MS);
  }];
}

/** The run's name and date: no line count (the user's W8: the list's headline counts the spots and lines). */
function Title({data}: {data: RunData}) {
  return <div class="c-run-title">
    <b class="c-run-name">{data.run.name}</b>
    <span class="u-small">{when(data.run.created)}</span>
  </div>;
}

function Back({back}: {back?: BackAction}) {
  if (!back) return null;
  return <Button kind="ghost" icon="back" class="c-back" onClick={back.onClick}>{back.label}</Button>;
}

type Side = "list" | "details";

interface FramePanelProps {
  side: Side;
  label: string;
  column: Column;
  max: number;
  layout: LayoutState;
  onOpen(side: Side, open: boolean): void;
  rail: {icon: IconName; text: string};
  class: string;
  children: ComponentChildren;
}

/** A side panel of the columns (ui/SidePanel.tsx) on the result's kept layout, as today's page has them. */
function FramePanel({side, label, column, max, layout, onOpen, rail, class: cls, children}: FramePanelProps) {
  const width = (part: Partial<Layout[Side]>): Layout =>
    ({...layout.latest.current, [side]: {...layout.latest.current[side], ...part}});
  return <SidePanel side={side === "list" ? "left" : "right"} name={side} label={label} column={column}
                    min={LIMITS[side][0]} max={max} railWidth={LIMITS.rail}
                    onWidth={(w) => layout.change(width({w}), false)} onCommit={layout.commit}
                    onReset={() => layout.change(width({w: DEFAULT_LAYOUT[side].w}), true)}
                    onOpen={(open) => onOpen(side, open)} rail={rail} class={cls}>{children}</SidePanel>;
}

/** The boxes of what stands in the hint's slot (the hint, its "?"). */
function slotBoxes(slot: HTMLElement | null): DOMRect[] {
  return slot ? Array.from(slot.children, (child) => child.getBoundingClientRect()) : [];
}

// What the bar covers of the map's top and bottom, px, before it is laid out: a move of the map keeps it free
// (with SpotMap's margins)
const BAR_TOP = 40, BAR_BOTTOM = 60;

/** What the bar covers of the map's column now: from its top to the switch's bottom, from the foot's top (the
 *  status line, the legend; on a phone above the sheet) to its bottom. */
function barPadding(col: HTMLElement | null, top: number, bottom: number): Padding {
  const box = col?.getBoundingClientRect(), bar = col?.querySelector(".v-switch")?.getBoundingClientRect();
  const foot = col?.querySelector(".v-foot")?.getBoundingClientRect();
  return {top: box && bar && bar.height ? Math.round(bar.bottom - box.top) + 4 : top, right: 0, left: 0,
          bottom: box && foot && foot.height ? Math.max(bottom, Math.round(box.bottom - foot.top) + 4) : bottom};
}

/** Keeps the bar's foot clear of what lies at the map's bottom: `covered` px of a phone's sheet (--v-covered) and,
 *  above that, Leaflet's own bottom corners where they reach under the foot (the scale; the credits when they run
 *  across the map: --v-corner). When one of them changed its size the canvas takes the view's rectangle again
 *  (the spots in view and their numbers follow). `watch`: more elements whose size matters (the sheet). */
function useFootClear(col: {current: HTMLElement | null}, canvas: SpotMap | null, covered: () => number,
                      watch: () => (Element | null | undefined)[], deps: unknown[], onPlace?: (place: string) => void) {
  useEffect(() => {
    const el = col.current;
    if (!el) return;
    let timer = 0;
    const place = () => {
      const box = el.getBoundingClientRect(), under = covered(), floor = box.bottom - under;
      let top = floor;
      el.querySelectorAll<HTMLElement>(".leaflet-bottom > *").forEach((corner) => {
        const r = corner.getBoundingClientRect();
        if (r.width && r.height && r.left < box.left + box.width * 0.6 && r.bottom > floor - 200) top = Math.min(top, r.top);
      });
      el.style.setProperty("--v-covered", `${under}px`);
      el.style.setProperty("--v-corner", `${Math.max(8, Math.round(floor - top) + 8)}px`);
      onPlace?.(`${under},${Math.round(floor - top)}`);
    };
    const update = () => {
      place();
      clearTimeout(timer);
      // once more when things rest (the corners are moved above a phone's sheet by their own observer)
      timer = window.setTimeout(() => { place(); canvas?.refresh(); }, 120);
    };
    update();  // also where no frame is drawn, so no ResizeObserver reports
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(update) : null;
    [el, ...watch(), ...Array.from(el.querySelectorAll(".leaflet-bottom > *"))].forEach((e) => { if (e) observer?.observe(e); });
    return () => { observer?.disconnect(); clearTimeout(timer); };
  }, deps);
}

const CARD_GAP = 8;  // px between the profile's card and the run's credits under it (the mock-up's 4 a)

/** The px of the map's column a desktop's profile card covers, from the column's bottom up to the card's top; 0:
 *  none. */
function cardCovers(col: HTMLElement | null): number {
  const card = col?.querySelector(":scope > .r-card")?.getBoundingClientRect();
  return col && card && card.height ? Math.max(0, Math.round(col.getBoundingClientRect().bottom - card.top)) : 0;
}

/** The profile's card over a desktop's map: it stands on the run's credits' line (--v-card-bottom: their height and
 *  CARD_GAP), and what it covers of the map's bottom (returned, for the foot) is not "in view" (the canvas's covered
 *  term), followed as the card comes, goes, is dragged or folded and as the credits fold or unfold. */
function useCardCover(col: {current: HTMLElement | null}, canvas: FrameMap | null): number {
  const [cover, setCover] = useState(0);
  useEffect(() => {
    const el = col.current;
    if (!el) return;
    let card: HTMLElement | null = null, credits: HTMLElement | null = null;
    const update = () => {
      const now = el.querySelector<HTMLElement>(":scope > .r-card");
      if (now !== card) {
        if (card) sizes.unobserve(card);
        card = now;
        if (card) sizes.observe(card);
      }
      const shown = el.querySelector<HTMLElement>(".leaflet-bottom.leaflet-right .leaflet-control-attribution");
      if (shown !== credits) {
        if (credits) sizes.unobserve(credits);
        credits = shown;
        if (credits) sizes.observe(credits);
      }
      el.style.setProperty("--v-card-bottom", `${(credits?.offsetHeight ?? 0) + CARD_GAP}px`);
      const px = cardCovers(el);
      setCover(px);
      canvas?.setCovered?.(px);
    };
    const sizes = new ResizeObserver(update), children = new MutationObserver(update);
    sizes.observe(el);
    children.observe(el, {childList: true});
    update();
    return () => { sizes.disconnect(); children.disconnect(); };
  }, [canvas]);
  return cover;
}

/** A line's anchors both in the part of the map `padding` leaves free (with `slack` px to spare): today's page's. */
function lineFree(map: L.Map, l: Line, padding: Padding, slack = 16): boolean {
  const size = map.getSize();
  return [[l.lat1, l.lon1], [l.lat2, l.lon2]].every(([lat, lon]) => {
    const q = map.latLngToContainerPoint([lat, lon]);
    return q.x >= padding.left - slack && q.x <= size.x - padding.right + slack &&
      q.y >= padding.top - slack && q.y <= size.y - padding.bottom + slack;
  });
}

/** The map moves now (a pan's or a zoom's animation). */
const moving = (map: L.Map) => !!((map as any)._panAnim?._inProgress || (map as any)._animatingZoom);

/** A measured line fitted into the map once the frame was drawn with it (its card or its sheet's stop): a link's
 *  always (`always`: the person has not seen it), Measure's only where it is not in the part `padding` leaves free
 *  (the person pressed its points there). `padding`: of the frame as it will be (a phone's sheet at half). */
function useMeasuredFit(canvas: FrameMap | null, map: L.Map | null, padding: () => Padding) {
  const [wanted, setWanted] = useState<{line: Line; always: boolean} | null>(null);
  useLayoutEffect(() => {
    if (!wanted || !canvas || !map) return;
    setWanted(null);
    const p = padding();
    if (wanted.always || !lineFree(map, wanted.line, p)) canvas.zoomToLine?.(wanted.line, p);
  }, [wanted]);
  return {fit: (line: Line, always: boolean) => setWanted({line, always})};
}

/** The frame's measured line drawn on the canvas (a link's; Measure's own again on a canvas made anew when the window
 *  crossed the phone's width), nothing when there is none. */
function useMeasuredDrawn(canvas: FrameMap | null, measured: Line | null) {
  useEffect(() => { canvas?.drawMeasured?.(measured); }, [canvas, measured]);
}

function Desktop({view, data, line, nav, back, hashOf, linkOf, view3dOf, actions, ortho, base, folder, show,
                  panels, measured, onMeasured}: FrameProps) {
  useSpotView(view);
  const layout = useLayout();
  const colsRef = useRef<HTMLDivElement>(null), colRef = useRef<HTMLDivElement>(null), hintRef = useRef<HTMLSpanElement>(null);
  const width = useWidthOf(colsRef);
  const [prefer, setPrefer] = useState<Side | null>(null);
  const fit = width ? fitColumns(layout.layout, width, prefer)
    : {list: {open: layout.layout.list.open, width: layout.layout.list.w, forced: false},
       details: {open: layout.layout.details.open, width: layout.layout.details.w, forced: false}};
  /** The bar's room, and the profile's card under the foot (its top; also before the foot was moved above it). */
  const padding = (): Padding => {
    const p = barPadding(colRef.current, BAR_TOP, BAR_BOTTOM), card = cardCovers(colRef.current);
    return card ? {...p, bottom: Math.max(p.bottom, card + 4)} : p;
  };
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const [toast, say] = useToast();
  const {ref, map, canvas} = useSpotMap(view, data, ortho, {
    padding, free: () => ({top: 0, right: 0, bottom: 0, left: 0}), obstacles: () => slotBoxes(hintRef.current),
    onChoose: setChoice, onToast: say});
  useChoiceCloses(view, map, closeChoice);
  useEscape(view, choice, closeChoice);
  // a measured line (Measure's, a link's): its profile in the card, fitted into the map (Measure's where it is hidden)
  const fitting = useMeasuredFit(canvas, map, padding);
  const onLinkMeasured = (l: Line | null) => { onMeasured(l); if (l) fitting.fit(l, true); };
  const onMeasure = (l: Line | null) => { onMeasured(l); if (l) fitting.fit(l, false); };
  useViewLink(view, canvas, line, nav, hashOf, padding, onLinkMeasured);
  useMeasuredDrawn(canvas, measured);
  useRunCredits(map, data, base, folder);
  // the profile's card: the selected line's (until it is closed: model.profileClosed) or a measured line's
  const sel = view.selected, profileLine = sel && !view.model.profileClosed ? sel.line : null;
  const cardOn = !!(measured || profileLine);
  const cover = useCardCover(colRef, canvas);
  // the scale above the credits where they run under it, and above the card where the card covers it; the credits
  // stay at the map's bottom, the card stands on them (the user's 4 a; corners.ts)
  useCornersAboveCard(ref, colRef, !!map, true);
  useFootClear(colRef, canvas, () => cover, () => [], [canvas, map, cover]);
  // The map's size follows the panels at once (also where no frame is drawn, so no ResizeObserver reports)
  useLayoutEffect(() => { map?.invalidateSize(); },
                  [map, fit.list.open, fit.list.width, fit.details.open, fit.details.width]);
  /** The card appeared or was resized: the selected line is brought out from under it (today's page's keepFree). */
  const keepFree = () => {
    const now = view.selected;
    if (!now || measured || !map || !canvas) return;
    const check = () => { if (view.selected?.row === now.row && !lineFree(map, now.line, padding())) canvas.zoomTo(now.row, padding()); };
    if (moving(map)) map.once("moveend", check);
    else check();
  };
  const closeMeasured = () => { view.model.measuredLink = null; onMeasured(null); canvas?.clearMeasure?.(); };

  // The panels: collapsed to a rail and expanded (kept); the focus to the rail, or to the edge
  const focus = useRef<string | null>(null);
  const setOpen = (side: Side, open: boolean) => {
    const now = layout.latest.current;
    layout.change({...now, [side]: {...now[side], open}}, true);
    if (open) setPrefer(side);  // in a narrow window the other panel collapses
    focus.current = `.c-col-${side} > ${open ? ".c-split" : ".c-rail"}`;
  };
  useLayoutEffect(() => {
    if (!focus.current) return;
    colsRef.current?.querySelector<HTMLElement>(focus.current)?.focus();
    focus.current = null;
  });

  /** The part of the viewport the map shows free of the profile's card. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    return {left: box.left, top: box.top, right: box.right, bottom: box.bottom - cover};
  };
  const p: PanelProps = {view, map: canvas, wide: true, padding, linkOf, view3dOf, measured};
  return <div class="c-result v-result">
    <header class="c-subtop c-result-top">
      <Back back={back} />
      <Title data={data} />
      <span class="u-grow" />
      {actions?.(false)}
      {/* the run's actions after the caller's, as on today's page (Measure's tip beside its button) */}
      <RunActions model={view.model} view={measureOf(canvas)} onMeasured={onMeasure} show={show} base={base} tip="beside" />
    </header>
    <div class="c-cols" ref={colsRef}>
      <FramePanel side="list" class="c-col-list" label={t("ui.view.map.panel_list")} column={fit.list}
                  max={maxColumnWidth("list", width, fit)} layout={layout} onOpen={setOpen}
                  rail={{icon: "list", text: t("ui.view.map.rail_list", {n: count(view.counts.lines)})}}>
        {panels.list(p)}
      </FramePanel>
      {/* c-card-on: while the card is shown the run's data credits fold behind their button (columns.css) */}
      <div class={cx("c-col-map v-map", cardOn && "c-card-on")} ref={colRef} data-choosing={choice ? choice.choices.length : undefined}>
        <div class="c-leaflet" ref={ref} />
        <MapBar view={view} map={canvas} wide short={cardOn}
                hint={<span class="v-hint-slot" ref={hintRef}>{panels.hint({...p, place: "map"})}</span>} />
        {toast && <div class="v-toast" role="status">{toast}</div>}
        <ProfileCard model={view.model} view={canvas} line={profileLine} measured={measured} onCloseMeasured={closeMeasured}
                     onClose={() => view.model.closeProfile()} layout={layout.layout} onLayout={layout.change}
                     onSettle={keepFree} />
      </div>
      <FramePanel side="details" class="c-col-details" label={t("ui.view.map.panel_details")} column={fit.details}
                  max={maxColumnWidth("details", width, fit)} layout={layout} onOpen={setOpen}
                  rail={{icon: "info", text: sel ? t("ui.view.map.rail_spot", {label: view.label(sel.spot)}) : t("ui.view.map.rail_details")}}>
        <div class="c-col-dbody">{panels.details(p)}{panels.lineActions?.(p)}</div>
      </FramePanel>
    </div>
    {choice && canvas && panels.chooser?.({...p, choices: choice.choices, at: choice.at, area: freeArea(), onClose: closeChoice})}
  </div>;
}

const PHONE_TOP = 116;  // px of a phone's map under its top bar and the switch (8 + 44 + 8 + 52, and 4)
const SHEET_PEEK = 132, SHEET_TOP = 64;  // the phone's sheet: its lowest height, and what it leaves free at the top
// A line brought back into sight keeps SHEET_MARGIN px from the edges of the part it is brought into (its anchors'
// circles A1, A2 whole: SpotMap markSize, 10.5 px), fewer where that part is too small for them. The map zooms (the
// least change that fits) only for a line longer than that part, and only where the part is at least SHEET_ROOM px
// high with its margins; in a smaller part the line goes as far in as it can at the same zoom. The pan or zoom is
// Leaflet's own animation of SHEET_PAN_S. The sheet is taken to rest when its height is its stop's and the data
// credits stand above it, or after SHEET_REST_MS (it moves in .22 s: ui.css .u-sheet)
const SHEET_MARGIN = 16, SHEET_ROOM = 48, SHEET_PAN_S = 0.25, SHEET_REST_MS = 1500;

/** The least shift of the span [a0, a1] into [r0, r1], `m` px from its ends where the room allows (fewer where it
 *  does not); a span longer than the room: the least shift that makes it cover the room (as far in as it goes). */
function shiftInto(a0: number, a1: number, r0: number, r1: number, m: number): number {
  if (a1 - a0 > r1 - r0) return a0 > r0 ? r0 - a0 : a1 < r1 ? r1 - a1 : 0;
  const g = Math.min(m, (r1 - r0 - (a1 - a0)) / 2);
  return a0 < r0 + g ? r0 + g - a0 : a1 > r1 - g ? r1 - g - a1 : 0;
}

/** On a phone, when the sheet's stop changed and the sheet rests there: a selected line that was in the part of the
 *  map a person sees (SpotMap's free part: above the sheet) at the last move of the map, selection or rest, and now
 *  has an anchor under the sheet or under the data credits band (a press there opens a credit's link) is brought into
 *  the room under the switch and above the credits: by the least pan at the same zoom, clear of the whole bar
 *  (`padding`) where it fits there; by the least zoom out that fits only when it is longer than the room
 *  (shiftInto, the SHEET_* constants). A line out of sight before, or a map moved while the sheet moved (a drag, its
 *  glide, a zoom), is left as the person left it: a move of theirs is never undone. Where the map shows nothing under
 *  the switch (full) nothing moves and what was in sight is kept for the next stop; a line selected there counts as in
 *  sight. The map column's `data-sheet-checks` counts the checks made, each once its move ended (tests wait for it). */
function useSheetKeeps(view: SpotView, map: L.Map | null, snap: Snap, col: {current: HTMLElement | null},
                       sheet: () => HTMLElement | null | undefined, covered: () => number, padding: () => Padding) {
  const latest = useRef({sheet, covered, padding});
  latest.current = {sheet, covered, padding};
  const seen = useRef(false);  // the selected line in sight at the last move of the map, selection or rest
  const stop = useRef(snap);   // the stop the last check was made for
  const own = useRef(false);   // a move of this hook is under way (not the person's)
  /** The selected line's anchors in the map's container px, or null. */
  const ends = (): L.Point[] | null => {
    const l = view.selected?.line;
    if (!l || !map) return null;
    return [map.latLngToContainerPoint([l.lat1, l.lon1]), map.latLngToContainerPoint([l.lat2, l.lon2])];
  };
  /** The map's height above the sheet, px. */
  const above = (): number => map ? map.getSize().y - latest.current.covered() : 0;
  /** The room a line is brought into, px of the map's container: under the switch, above the sheet and above the
   *  data credits band (the scale may lie over the line). */
  const room = (): {top: number; bottom: number; width: number} => {
    const top = latest.current.padding().top, el = map?.getContainer();
    let bottom = above();
    const credits = el?.querySelector(".leaflet-control-attribution")?.getBoundingClientRect();
    if (el && credits && credits.width && credits.height) {
      const at = credits.top - el.getBoundingClientRect().top;
      if (at > top && at < bottom) bottom = at;
    }
    return {top, bottom, width: map ? map.getSize().x : 0};
  };
  /** Both anchors in the part of the map a person sees (above the sheet). */
  const inSight = (): boolean => {
    const e = ends(), bottom = above(), width = map ? map.getSize().x : 0;
    return !!e && e.every((q) => q.x >= 0 && q.x <= width && q.y >= 0 && q.y <= bottom);
  };
  /** The map shows a part under the switch and above the sheet. */
  const roomy = (): boolean => { const r = room(); return r.bottom - r.top > 0; };
  useEffect(() => {
    if (!map) return;
    const note = () => { if (roomy()) seen.current = inSight(); };
    let row = view.selected?.row;
    const selected = () => {
      if (view.selected?.row === row) return;
      row = view.selected?.row;
      seen.current = roomy() ? inSight() : !!view.selected;
    };
    map.on("moveend", note);
    const unsubscribe = view.subscribe(selected);
    note();
    return () => { map.off("moveend", note); unsubscribe(); };
  }, [view, map]);
  useEffect(() => {
    if (!map || stop.current === snap) return;
    const leaflet = map as any;
    const was = seen.current, started = performance.now();
    // a drag under way, or its glide (Leaflet's panBy without movestart), or a zoom: the person moves the map
    const busy = leaflet._panAnim?._inProgress || leaflet._animatingZoom || leaflet.dragging?._draggable?._moving;
    let moved = !own.current && !!busy, frame = 0, ended: (() => void) | null = null;
    const onMove = () => { if (!own.current) moved = true; };
    map.on("movestart move zoomstart", onMove);
    const count = () => {
      if (col.current) col.current.dataset.sheetChecks = String(Number(col.current.dataset.sheetChecks || 0) + 1);
    };
    /** A move of this hook begins: its moves are not the person's until it ends. */
    const mine = () => {
      own.current = true;
      map.once("moveend", () => { own.current = false; });
    };
    /** Bring the selected line into the room; false: nothing to move. */
    const bringBack = (): boolean => {
      const e = ends(), l = view.selected?.line;
      if (!e || !l) return false;
      const size = map.getSize(), p = latest.current.padding(), r = room(), m = SHEET_MARGIN;
      const x0 = Math.min(e[0].x, e[1].x), x1 = Math.max(e[0].x, e[1].x);
      const y0 = Math.min(e[0].y, e[1].y), y1 = Math.max(e[0].y, e[1].y);
      // clear of the whole bar (the switch, the foot) and of the credits, where it fits there with its margins
      const clear = [p.left + m, p.top + m, size.x - p.right - m, Math.min(size.y - p.bottom, r.bottom) - m];
      let by: number[];
      if (x1 - x0 <= clear[2] - clear[0] && y1 - y0 <= clear[3] - clear[1]) {
        by = [shiftInto(x0, x1, clear[0], clear[2], 0), shiftInto(y0, y1, clear[1], clear[3], 0)];
      } else if ((x1 - x0 <= r.width && y1 - y0 <= r.bottom - r.top) || r.bottom - r.top - 2 * m < SHEET_ROOM) {
        // it fits the room (its margins as far as they go), or the room is too small to zoom for: as far in as it goes
        by = [shiftInto(x0, x1, 0, r.width, m), shiftInto(y0, y1, r.top, r.bottom, m)];
      } else {  // longer than the room: the least zoom out that fits it there
        mine();
        map.fitBounds(L.latLngBounds([l.lat1, l.lon1], [l.lat2, l.lon2]),
                      {paddingTopLeft: [m, r.top + m], paddingBottomRight: [m, size.y - r.bottom + m],
                       maxZoom: map.getZoom(), animate: true, duration: SHEET_PAN_S});
        return true;
      }
      if (!by[0] && !by[1]) return false;
      mine();
      map.panBy([-by[0], -by[1]], {animate: true, duration: SHEET_PAN_S});
      return true;
    };
    /** The data credits' corner placed for the sheet as it is (corners.ts: right above it, or in Leaflet's own place
     *  at the map's bottom); its observer may come a frame after the sheet's last move (WebKit). */
    const placed = (el: HTMLElement): boolean => {
      const box = map.getContainer(), corner = box.querySelector(".leaflet-bottom.leaflet-right");
      if (!corner) return true;
      const bottom = corner.getBoundingClientRect().bottom, top = el.getBoundingClientRect().top;
      return Math.abs(bottom - top) < 1.5 || Math.abs(bottom - box.getBoundingClientRect().bottom) < 1.5;
    };
    const check = () => {
      // the frame was left (the window crossed the phone's width, another run opened) before this frame's cleanup:
      // its map is not touched any more (the second code review of A1's work)
      if (!col.current || !latest.current.sheet()) return;
      const el = latest.current.sheet(), target = el ? parseFloat(el.style.height) : NaN;
      const resting = !el || !(target > 0) || (Math.abs(el.getBoundingClientRect().height - target) < 1 && placed(el));
      if (!resting && performance.now() - started < SHEET_REST_MS) { frame = requestAnimationFrame(check); return; }
      map.off("movestart move zoomstart", onMove);
      stop.current = snap;
      const r = room(), below = ends()?.some((q) => q.y > r.bottom) ?? false;
      if (roomy() && was && !moved && below) {
        // counted once the move ended (its moveend sets what is in sight: the effect above)
        const done = () => { ended = null; count(); };
        ended = done;
        map.once("moveend", done);  // before the move: Leaflet may end it at once
        if (bringBack()) return;
        map.off("moveend", done);
        ended = null;
      }
      if (roomy()) seen.current = inSight();
      count();
    };
    frame = requestAnimationFrame(check);
    return () => {
      cancelAnimationFrame(frame);
      map.off("movestart move zoomstart", onMove);
      if (ended) map.off("moveend", ended);
    };
  }, [snap, map]);
}

/** A phone's sheet: the px of a frame `height` px high it covers at a stop (ui/components.tsx Sheet: peek, half of
 *  the frame, or all but the top bar). */
function sheetAt(snap: Snap, height: number): number {
  return Math.round(snap === "peek" ? Math.min(SHEET_PEEK, height) : snap === "half" ? Math.max(SHEET_PEEK, height * 0.5)
    : height - SHEET_TOP);
}

/** A link's line measured outside the run while this phone's frame was made (the window crossed the phone's width
 *  meanwhile: viewlink.ts waits for the outcome in the frame that opened the link only): a failure is a note too, and
 *  `onNote` is told (the sheet rises to show it). A line measured already (`measured`) waits for nothing. */
function useNoteAfterCrossing(view: SpotView, measured: Line | null, onNote: () => void) {
  const latest = useRef(onNote);
  latest.current = onNote;
  useEffect(() => {
    const model = view.model, measuring = model.measuredLink;
    if (!measuring || measured) return;
    const stop = view.subscribe(() => {
      if (model.measuredLink === measuring) return;
      stop();
      if (model.note) latest.current();
    });
    return stop;
  }, [view]);  // once, when the frame is made
}

function Phone({view, data, line, nav, back, hashOf, linkOf, view3dOf, actions, ortho, base, folder, show,
                panels, measured, onMeasured}: FrameProps) {
  useSpotView(view);
  // the view opens with the sheet low (the user's decision of 2026-11-17: the map first)
  const [snap, setSnap] = useState<Snap>("peek");
  const [, setPlaced] = useState("");  // the bar measures its room again when its foot was moved
  const phoneRef = useRef<HTMLDivElement>(null), colRef = useRef<HTMLDivElement>(null), hintRef = useRef<HTMLSpanElement>(null);
  /** The px of the map's bottom under the sheet (before the sheet has a height: its stop's height). */
  const covered = (): number => {
    const box = colRef.current?.getBoundingClientRect(), sheet = phoneRef.current?.querySelector<HTMLElement>(".u-sheet");
    if (!box) return 0;
    // the sheet as drawn once it has taken its height; before that (the first fit of the map) the height its state
    // will give it
    if (sheet && sheet.style.height) return Math.max(0, Math.round(box.bottom - sheet.getBoundingClientRect().top));
    return sheetAt(snap, box.height);
  };
  const padding = (): Padding => barPadding(colRef.current, PHONE_TOP, covered() + BAR_BOTTOM);
  /** The padding the frame will have with the sheet at a stop (the foot rides on the sheet). */
  const paddingAt = (at: Snap): Padding => {
    const p = padding(), box = colRef.current?.getBoundingClientRect();
    return box ? {...p, bottom: p.bottom - covered() + sheetAt(at, box.height)} : p;
  };
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const [toast, say] = useToast();
  // On a phone a spot is in view when its shown line crosses the part of the map a person sees: not under the sheet
  const {ref, map, canvas} = useSpotMap(view, data, ortho, {
    padding, free: () => ({top: 0, right: 0, bottom: covered(), left: 0}), phone: true,
    // the top bar lies over the map: no number under it
    obstacles: () => [...Array.from(phoneRef.current?.querySelectorAll(".c-phone-top > *") ?? [], (e) => e.getBoundingClientRect()),
                      ...slotBoxes(hintRef.current)],
    onChoose: setChoice, onToast: say});
  useChoiceCloses(view, map, closeChoice);
  useEscape(view, choice, closeChoice);
  // Measuring: the sheet goes low (today's page; the canvas holds the map still), the tip is the status line's first
  // line; a measured line's profile first in the sheet's body at half (today's measuredNow), the line fitted into the
  // map above the sheet at half (a link's always, Measure's where it is not in sight)
  const [measuring, setMeasuring] = useState(false);
  useEffect(() => canvas?.onMeasuring?.((on) => { setMeasuring(on); if (on) setSnap("peek"); }), [canvas]);
  const tip = useMeasureTip();
  const fitting = useMeasuredFit(canvas, map, () => paddingAt("half"));
  const shown = (l: Line | null, always: boolean) => {
    onMeasured(l);
    if (!l) return;
    setSnap("half");
    fitting.fit(l, always);
  };
  useMeasuredDrawn(canvas, measured);
  const closeMeasured = () => { view.model.measuredLink = null; onMeasured(null); canvas?.clearMeasure?.(); };
  // a link that ends in a note (hidden by the filters, not in the run, not measured): the sheet at half shows it, as
  // today's page opens (the planner, fix round 1); a link that opens its line keeps the view's low start
  const toNote = () => setSnap((s) => s === "peek" ? "half" : s);
  useViewLink(view, canvas, line, nav, hashOf, padding, (l) => shown(l, true), toNote);
  useNoteAfterCrossing(view, measured, toNote);
  useCornersAboveSheet(phoneRef, ref, true);  // the attribution and the scale above the sheet
  useRunCredits(map, data, base, folder);
  // The sheet moved: the bar's foot stays above it, and once it rests the view's rectangle is taken again (the
  // spots in view and their numbers follow)
  useFootClear(colRef, canvas, covered, () => [phoneRef.current?.querySelector(".u-sheet")], [canvas, map, snap], setPlaced);
  // The sheet rose over the selected line: the line back in sight
  useSheetKeeps(view, map, snap, colRef, () => phoneRef.current?.querySelector<HTMLElement>(".u-sheet"), covered,
                padding);

  /** The part of the viewport the map shows free of the top bar and the sheet. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    return {left: box.left, top: box.top + 64, right: box.right, bottom: box.bottom - covered()};
  };
  const p: PanelProps = {view, map: canvas, wide: false, padding, sheet: {snap, setSnap}, linkOf, view3dOf, measured};
  // Compare needs room the phone's top bar does not have (as today's page)
  const phoneShow = (["measure", "share", "download"] as const).filter((a) => !show || show.includes(a));
  return <div class="c-result c-result-phone v-result" ref={phoneRef}>
    <div class="c-col-map v-map" ref={colRef} data-choosing={choice ? choice.choices.length : undefined}>
      <div class="c-leaflet" ref={ref} />
      {/* the measuring tip or the map's message: the first line of the status line's box while it lasts (the pilot's
          arrangement; the user's 11 a) */}
      <MapBar view={view} map={canvas} wide={false} sheet={snap} onSheet={setSnap} message={toast} tip={measuring ? tip : undefined}
              hint={<span class="v-hint-slot" ref={hintRef}>{panels.hint({...p, place: "map"})}</span>} />
    </div>
    <div class="c-phone-top">
      <div class={back ? "c-pill" : "c-pill c-pill-alone"}>
        {back && <IconButton icon="back" label={back.label} plain round class="c-back" onClick={back.onClick} />}
        <span class="u-grow c-pill-name">{data.run.name}</span>
        {actions?.(true)}
        {/* the run's actions after the caller's, icons in the pill (today's page draws them beside it) */}
        <RunActions model={view.model} view={measureOf(canvas)} onMeasured={(l) => shown(l, false)} compact plain tip="none"
                    show={phoneShow} base={base} />
      </div>
    </div>
    {/* the sheet from its top: the handle, the hint (its first line, B.2 item 12), the head's row, then the body: a
        measured line's profile first (the mock-up), the details (with the selected line's dock: SpotDetails), the
        line's actions, the list */}
    <Sheet label={t("ui.view.map.sheet")} snap={snap} onSnap={setSnap} peek={SHEET_PEEK} top={SHEET_TOP}
           header={<>{panels.hint({...p, place: "sheet"})}{panels.sheetHead(p)}</>}>
      {measured && <ProfileDock model={view.model} view={canvas} line={null} measured={measured} onCloseMeasured={closeMeasured}
                                class="r-dock-sheet vl-dock" />}
      {panels.details(p)}
      {panels.lineActions?.(p)}
      {panels.list(p)}
    </Sheet>
    {choice && canvas && panels.chooser?.({...p, choices: choice.choices, at: choice.at, area: freeArea(), onClose: closeChoice})}
  </div>;
}

/** A run's result in the result view: its model of spots made once for the run (the selection, the level, Best
 *  and "Top level only" stay when the window crosses the phone's width), drawn in columns or on a phone. */
export function SpotColumns(props: SpotColumnsProps) {
  const view = useMemo(() => createSpotView(props.model), [props.model]);
  useEffect(() => () => view.destroy(), [view]);
  // the measured line (Measure's, or a link's: viewlink.ts), kept here across the phone's width, of this view only
  const [measured, setMeasured] = useState<{view: SpotView; line: Line} | null>(null);
  const measuredLine = measured?.view === view ? measured.line : null;
  const onMeasured = (l: Line | null) => setMeasured(l ? {view, line: l} : null);
  useEffect(() => {  // for tests and the console
    const shown = (window as any).FINDALINE_VIEW;
    if (shown?.view === view) shown.measured = measuredLine;
  });
  const frame = {...props, view, panels: props.panels ?? PANELS, measured: measuredLine, onMeasured};
  return props.wide ? <Desktop key="wide" {...frame} /> : <Phone key="phone" {...frame} />;
}
