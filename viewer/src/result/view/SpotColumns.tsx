// The result view's frame (docs/line-volume/spec-view.md B.2: "Today's page stays as the frame"), beside today's
// page (ResultColumns.tsx, which opens it only behind the flag: viewWanted, opensView): a header (the caller's way
// back, the run's name and date, the caller's actions) and three columns: the list | the map with its bar
// (MapBar) | the details; the side panels' edges, rails and kept widths are today's (ui/SidePanel, layout.ts). On
// phones (< 768 px) the map with a sheet holding the hint, the details and the list. The columns' contents are
// slots (SpotPanels.tsx: PANELS), filled by the view's panels; the frame owns the Leaflet map (base layers with
// the run's orthophoto, the shore's and the coarser terrain's overlays, the layer control, the scale, the run's
// data credits), the canvas (SpotMap), the toast, where the table of spots stands, and Esc.
//
// Not here yet (they join with today's other features, step 3c): the run's actions (Download, Measure, Share,
// Compare: their place in the header stays free), the profile card, a line's links and the `#line=` route.
//
// For tests and the console: window.FINDALINE_MAP is the Leaflet map (as on today's page) and
// window.FINDALINE_VIEW = {view, map} (the SpotView and the SpotMap) is set once the view was drawn for the first
// time; window.FINDALINE_RESULT is not set in this view (its `view` is a ResultMap).

import L from "leaflet";
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, IconButton, Sheet, type Snap } from "../../ui/components";
import { SidePanel, useWidthOf } from "../../ui/SidePanel";
import type { IconName } from "../../ui/icons";
import { baseLayers } from "../../baselayers";
import { addShore } from "../../shoreLayer";
import { addCoarser } from "../../coarserLayer";
import { t } from "../../i18n";
import { measure } from "../../perf";
import { when } from "../../time";
import type { RunData } from "../../types";
import type { ResultModel } from "../model";
import type { Padding } from "../ResultMap";
import { SpotMap } from "../SpotMap";
import { createSpotView, viewOf, type SpotChoice, type SpotView } from "../spots";
import { count } from "./common";
import { useCornersAboveSheet } from "./corners";
import { useRunCredits } from "./credits";
import type { Area } from "./LineChooser";
import { DEFAULT_LAYOUT, LIMITS, fitColumns, maxColumnWidth, type Column, type Layout } from "./layout";
import { MapBar } from "./MapBar";
import type { BackAction, ResultColumnsProps } from "./ResultColumns";
import { PANELS, useSpotView, type PanelProps, type SpotPanels } from "./SpotPanels";
import { useLayout, type LayoutState } from "./useLayout";
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

interface FrameProps extends SpotColumnsProps { view: SpotView; panels: SpotPanels }

/** A press's choice of the spots it reached about as near, at its point in the viewport. */
type ChoiceAt = {choices: SpotChoice[]; at: {x: number; y: number}};

const TOAST_MS = 3200;  // how long a message of the map stays

/** The map of the view: base layers (with the run's orthophoto), zoom in quarter steps (half a step for one notch
 *  of the wheel), the layer control with the shore's and the coarser terrain's overlays, the scale, and the
 *  canvas (SpotMap) fitted to the run's lines. */
function useSpotMap(view: SpotView, data: RunData, ortho: ResultColumnsProps["ortho"], frame: {
  padding(): Padding; free(): Padding; obstacles(): DOMRect[]; onChoose(choice: ChoiceAt): void; onToast(text: string): void;
  phone?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const [canvas, setCanvas] = useState<SpotMap | null>(null);
  const latest = useRef(frame);
  latest.current = frame;
  useEffect(() => {
    const model = view.model, start = performance.now();
    const leaflet = L.map(ref.current!, {center: data.center, zoom: 15, maxZoom: data.max_zoom, zoomSnap: 0.25,
                                         zoomDelta: 0.5, wheelPxPerZoomLevel: 150});
    (window as any).FINDALINE_MAP = leaflet;  // for tests and the browser console
    const layers = baseLayers(ortho ? ortho(data) : data.ortho, data.max_zoom);
    Object.values(layers)[0].addTo(leaflet);
    const overlays: Record<string, L.Layer> = {};
    addShore(leaflet, data.shore, overlays);  // the uncertain shore: its overlay, its metres in view
    model.setCoarserFit(addCoarser(leaflet, data.terrain_sources, overlays)?.fit ?? null);
    L.control.layers(layers, Object.keys(overlays).length ? overlays : undefined, {position: "topright"}).addTo(leaflet);
    L.control.scale({position: "bottomleft"}).addTo(leaflet);
    let made: SpotMap | null = null, drawn = false;
    const spotMap = new SpotMap(leaflet, view, {
      onChoose: (choices, at) => {
        const box = leaflet.getContainer().getBoundingClientRect();
        latest.current.onChoose({choices, at: {x: box.left + at.x, y: box.top + at.y}});
      },
      onToast: (text) => latest.current.onToast(text),
      obstacles: () => latest.current.obstacles(),
      free: () => latest.current.free(),
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

function Title({data}: {data: RunData}) {
  const n = data.columns.length;
  return <div class="c-run-title">
    <b class="c-run-name">{data.run.name}</b>
    <span class="u-small">{when(data.run.created)} · {t("ui.view.map.title_lines", {count: n, n: count(n)})}</span>
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

// What the bar covers of the map's top and bottom, px: a move of the map keeps it free (with SpotMap's margins)
const BAR_TOP = 40, BAR_BOTTOM = 60;

function Desktop({view, data, back, actions, ortho, base, folder, panels}: FrameProps) {
  useSpotView(view);
  const layout = useLayout();
  const colsRef = useRef<HTMLDivElement>(null), hintRef = useRef<HTMLSpanElement>(null);
  const width = useWidthOf(colsRef);
  const [prefer, setPrefer] = useState<Side | null>(null);
  const fit = width ? fitColumns(layout.layout, width, prefer)
    : {list: {open: layout.layout.list.open, width: layout.layout.list.w, forced: false},
       details: {open: layout.layout.details.open, width: layout.layout.details.w, forced: false}};
  const padding = (): Padding => ({top: BAR_TOP, right: 0, bottom: BAR_BOTTOM, left: 0});
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const [toast, say] = useToast();
  const {ref, map, canvas} = useSpotMap(view, data, ortho, {
    padding, free: () => ({top: 0, right: 0, bottom: 0, left: 0}), obstacles: () => slotBoxes(hintRef.current),
    onChoose: setChoice, onToast: say});
  useChoiceCloses(view, map, closeChoice);
  useEscape(view, choice, closeChoice);
  useRunCredits(map, data, base, folder);
  // The map's size follows the panels at once (also where no frame is drawn, so no ResizeObserver reports)
  useLayoutEffect(() => { map?.invalidateSize(); },
                  [map, fit.list.open, fit.list.width, fit.details.open, fit.details.width]);

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

  /** The part of the viewport the map shows. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    return {left: box.left, top: box.top, right: box.right, bottom: box.bottom};
  };
  const p: PanelProps = {view, map: canvas, wide: true, padding};
  const sel = view.selected;
  return <div class="c-result v-result">
    <header class="c-subtop c-result-top">
      <Back back={back} />
      <Title data={data} />
      <span class="u-grow" />
      {actions?.(false)}
    </header>
    <div class="c-cols" ref={colsRef}>
      <FramePanel side="list" class="c-col-list" label={t("ui.view.map.panel_list")} column={fit.list}
                  max={maxColumnWidth("list", width, fit)} layout={layout} onOpen={setOpen}
                  rail={{icon: "list", text: t("ui.view.map.rail_list", {n: count(view.counts.lines)})}}>
        {panels.list(p)}
      </FramePanel>
      <div class="c-col-map v-map">
        <div class="c-leaflet" ref={ref} />
        <MapBar view={view} map={canvas} wide hint={<span class="v-hint-slot" ref={hintRef}>{panels.hint(p)}</span>} />
        {toast && <div class="v-toast" role="status">{toast}</div>}
      </div>
      <FramePanel side="details" class="c-col-details" label={t("ui.view.map.panel_details")} column={fit.details}
                  max={maxColumnWidth("details", width, fit)} layout={layout} onOpen={setOpen}
                  rail={{icon: "info", text: sel ? t("ui.view.map.rail_spot", {label: view.label(sel.spot)}) : t("ui.view.map.rail_details")}}>
        <div class="c-col-dbody">{panels.details(p)}</div>
      </FramePanel>
    </div>
    {choice && canvas && panels.chooser?.({...p, choices: choice.choices, at: choice.at, area: freeArea(), onClose: closeChoice})}
  </div>;
}

const PHONE_TOP = 104;  // px of a phone's map under its top bar and the switch

function Phone({view, data, back, actions, ortho, base, folder, panels}: FrameProps) {
  useSpotView(view);
  const [snap, setSnap] = useState<Snap>("half");
  const phoneRef = useRef<HTMLDivElement>(null), colRef = useRef<HTMLDivElement>(null);
  /** The px of the map's bottom under the sheet (before the sheet has a height: half the map, its first state). */
  const covered = (): number => {
    const box = colRef.current?.getBoundingClientRect();
    const sheet = phoneRef.current?.querySelector(".u-sheet")?.getBoundingClientRect();
    if (!box) return 0;
    return sheet && sheet.height > 0 ? Math.max(0, Math.round(box.bottom - sheet.top)) : Math.round(box.height * 0.5);
  };
  const padding = (): Padding => ({top: PHONE_TOP, right: 0, bottom: covered() + BAR_BOTTOM, left: 0});
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const [toast, say] = useToast();
  // On a phone a spot is in view when its shown line crosses the part of the map a person sees: not under the sheet
  const {ref, map, canvas} = useSpotMap(view, data, ortho, {
    padding, free: () => ({top: 0, right: 0, bottom: covered(), left: 0}), phone: true,
    // the top bar lies over the map: no number under it
    obstacles: () => Array.from(phoneRef.current?.querySelectorAll(".c-phone-top > *") ?? [], (e) => e.getBoundingClientRect()),
    onChoose: setChoice, onToast: say});
  useChoiceCloses(view, map, closeChoice);
  useEscape(view, choice, closeChoice);
  useCornersAboveSheet(phoneRef, ref, true);  // the attribution and the scale above the sheet
  useRunCredits(map, data, base, folder);
  // The sheet moved: the bar's foot stays above it, and once it rests the view's rectangle is taken again (the
  // spots in view and their numbers follow)
  useEffect(() => {
    const sheet = phoneRef.current?.querySelector<HTMLElement>(".u-sheet"), col = colRef.current;
    if (!sheet || !col) return;
    let timer = 0;
    const update = () => {
      col.style.setProperty("--v-covered", `${covered()}px`);
      clearTimeout(timer);
      timer = window.setTimeout(() => canvas?.refresh(), 120);
    };
    update();  // also where no frame is drawn, so no ResizeObserver reports
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(update) : null;
    observer?.observe(sheet);
    observer?.observe(col);
    return () => { observer?.disconnect(); clearTimeout(timer); };
  }, [canvas, snap]);

  /** The part of the viewport the map shows free of the top bar and the sheet. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    return {left: box.left, top: box.top + 64, right: box.right, bottom: box.bottom - covered()};
  };
  const p: PanelProps = {view, map: canvas, wide: false, padding, sheet: {snap, setSnap}};
  return <div class="c-result c-result-phone v-result" ref={phoneRef}>
    <div class="c-col-map v-map" ref={colRef}>
      <div class="c-leaflet" ref={ref} />
      <MapBar view={view} map={canvas} wide={false} />
      {toast && <div class="v-toast" role="status">{toast}</div>}
    </div>
    <div class="c-phone-top">
      <div class={back ? "c-pill" : "c-pill c-pill-alone"}>
        {back && <IconButton icon="back" label={back.label} plain round class="c-back" onClick={back.onClick} />}
        <span class="u-grow c-pill-name">{data.run.name}</span>
        {actions?.(true)}
      </div>
    </div>
    <Sheet label={t("ui.view.map.sheet")} snap={snap} onSnap={setSnap} peek={132} top={64} header={panels.sheetHead(p)}>
      {panels.hint(p)}
      {panels.details(p)}
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
  const frame = {...props, view, panels: props.panels ?? PANELS};
  return props.wide ? <Desktop key="wide" {...frame} /> : <Phone key="phone" {...frame} />;
}
