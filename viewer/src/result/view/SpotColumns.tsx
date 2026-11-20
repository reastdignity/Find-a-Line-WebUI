// The result view's frame (docs/line-volume/spec-view.md B.2: "Today's page stays as the frame"), beside today's
// page (ResultColumns.tsx, which opens it only behind the flag: viewWanted, opensView): a header (the caller's way
// back, the run's name and date, the caller's actions) and three columns: the list | the map with its bar
// (MapBar) | the details; the side panels' edges, rails and kept widths are today's (ui/SidePanel, layout.ts). On
// phones (< 768 px) the map with a sheet holding the hint, the details and the list. The columns' contents are
// slots (SpotPanels.tsx: PANELS), filled by the view's panels; the frame owns the Leaflet map (base layers with
// the run's orthophoto, the shore's and the coarser terrain's overlays, the layer control, the scale, the run's
// data credits), the canvas (SpotMap), the toast, where the table of spots stands, and Esc.
//
// The route's line (`line`, `nav`) opens in the view and the selection goes into the hash (`hashOf`): viewlink.ts.
// A line outside the run that a link names is measured and kept here (SpotColumns' `measured`, across the phone's
// width); nothing draws it yet. On a phone a selected line that the sheet covers when it moves (it rose) is brought
// back into sight (useSheetKeeps).
//
// Not here yet (they join with today's other features, step 3c): the run's actions (Download, Measure, Share,
// Compare), the profile card and a line's links. Their places are empty slots, each marked in the JSX below: the
// run's actions (the header; a phone's pill), the profile card over the map (the columns), the profile's dock (a
// phone's sheet) and the selected line's actions (SpotPanels `lineActions`, after the details). The props they need
// reach Desktop and Phone (`show`, the measured line; not read yet), and the caller's `linkOf` and `view3dOf` go on
// to the panels (PanelProps).
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
import { count } from "./common";
import { keepScaleAboveAttribution, useCornersAboveSheet } from "./corners";
import { useRunCredits } from "./credits";
import type { Area } from "./LineChooser";
import { DEFAULT_LAYOUT, LIMITS, fitColumns, maxColumnWidth, type Column, type Layout } from "./layout";
import { MapBar } from "./MapBar";
import type { BackAction, ResultColumnsProps } from "./ResultColumns";
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
  /** A line outside the run that a link named, measured (viewlink.ts); null: none. Nothing draws it yet. */
  measured: Line | null;
  onMeasured(l: Line | null): void;
}

/** A press's choice of the spots it reached about as near, at its point in the viewport. */
type ChoiceAt = {choices: SpotChoice[]; at: {x: number; y: number}};

const TOAST_MS = 3200;  // how long a message of the map stays

/** The map of the view: base layers (with the run's orthophoto), zoom in quarter steps (half a step for one notch
 *  of the wheel: measured in Edge on Windows, where Leaflet reads a notch as 50 px, 90 px per level give 0.5; 150
 *  gave a quarter, Leaflet's own 60 three quarters), the layer control with the shore's and the coarser terrain's overlays, the scale, and the
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
    L.control.layers(layers, Object.keys(overlays).length ? overlays : undefined, {position: "topright"}).addTo(leaflet);
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

function Desktop({view, data, line, nav, back, hashOf, linkOf, view3dOf, actions, ortho, base, folder, show,
                  panels, onMeasured}: FrameProps) {
  useSpotView(view);
  const layout = useLayout();
  const colsRef = useRef<HTMLDivElement>(null), colRef = useRef<HTMLDivElement>(null), hintRef = useRef<HTMLSpanElement>(null);
  const width = useWidthOf(colsRef);
  const [prefer, setPrefer] = useState<Side | null>(null);
  const fit = width ? fitColumns(layout.layout, width, prefer)
    : {list: {open: layout.layout.list.open, width: layout.layout.list.w, forced: false},
       details: {open: layout.layout.details.open, width: layout.layout.details.w, forced: false}};
  const padding = (): Padding => barPadding(colRef.current, BAR_TOP, BAR_BOTTOM);
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const [toast, say] = useToast();
  const {ref, map, canvas} = useSpotMap(view, data, ortho, {
    padding, free: () => ({top: 0, right: 0, bottom: 0, left: 0}), obstacles: () => slotBoxes(hintRef.current),
    onChoose: setChoice, onToast: say});
  useChoiceCloses(view, map, closeChoice);
  useEscape(view, choice, closeChoice);
  useViewLink(view, canvas, line, nav, hashOf, padding, onMeasured);
  useRunCredits(map, data, base, folder);
  // the scale above the credits where they run under it (no sheet or card raises this map's corners: corners.ts)
  useEffect(() => { if (map) keepScaleAboveAttribution(map.getContainer()); }, [map]);
  useFootClear(colRef, canvas, () => 0, () => [], [canvas, map]);
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
  const p: PanelProps = {view, map: canvas, wide: true, padding, linkOf, view3dOf};
  const sel = view.selected;
  return <div class="c-result v-result">
    <header class="c-subtop c-result-top">
      <Back back={back} />
      <Title data={data} />
      <span class="u-grow" />
      {actions?.(false)}
      {/* slot, empty: the run's actions (Download, Measure, Share, Compare; `show`), after the caller's as on today's
          page; step 3c's frame fills it */}
    </header>
    <div class="c-cols" ref={colsRef}>
      <FramePanel side="list" class="c-col-list" label={t("ui.view.map.panel_list")} column={fit.list}
                  max={maxColumnWidth("list", width, fit)} layout={layout} onOpen={setOpen}
                  rail={{icon: "list", text: t("ui.view.map.rail_list", {n: count(view.counts.lines)})}}>
        {panels.list(p)}
      </FramePanel>
      <div class="c-col-map v-map" ref={colRef} data-choosing={choice ? choice.choices.length : undefined}>
        <div class="c-leaflet" ref={ref} />
        <MapBar view={view} map={canvas} wide
                hint={<span class="v-hint-slot" ref={hintRef}>{panels.hint({...p, place: "map"})}</span>} />
        {toast && <div class="v-toast" role="status">{toast}</div>}
        {/* slot, empty: the selected line's profile as a card over the map's bottom (today's ProfileCard); how it
            shares the room with the bar's foot is open; step 3c's frame fills it */}
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
// A line brought back into sight keeps this many px from the edges of the part it is brought into (its anchors'
// circles A1, A2 whole: SpotMap markSize, 10.5 px); with less room than SHEET_ROOM px under the switch and above the
// sheet (the sheet at full) the map shows too little and does not move. The sheet is taken to rest when its height is
// its stop's, or after SHEET_REST_MS (it moves in .22 s: ui.css .u-sheet)
const SHEET_MARGIN = 16, SHEET_ROOM = 48, SHEET_REST_MS = 1500;

/** On a phone, when the sheet's stop changed and the sheet rests there: a selected line that was in the part of the
 *  map a person sees (SpotMap's free part: above the sheet) at the last move of the map, selection or rest, and is not
 *  now (the sheet rose over it) is brought back by the least pan at the same zoom: clear of the bar (`padding`) where
 *  it fits there, else of the top bar and the switch only, else the frame's zoomTo. A line out of sight before, or a
 *  map moved while the sheet moved, is left as the person left it (a move of theirs is never undone). Where the map
 *  has no room (full) nothing moves and what was in sight is kept for the next stop; a line selected there counts as
 *  in sight. The map column's `data-sheet-checks` counts the checks made (tests wait for it). */
function useSheetKeeps(view: SpotView, map: L.Map | null, canvas: SpotMap | null, snap: Snap,
                       col: {current: HTMLElement | null}, sheet: () => HTMLElement | null | undefined,
                       covered: () => number, padding: () => Padding) {
  const latest = useRef({sheet, covered, padding});
  latest.current = {sheet, covered, padding};
  const seen = useRef(false);  // the selected line in sight at the last move of the map, selection or rest
  const stop = useRef(snap);   // the stop the last check was made for
  /** The selected line's anchors in the map's container px, or null. */
  const ends = (): L.Point[] | null => {
    const l = view.selected?.line;
    if (!l || !map) return null;
    return [map.latLngToContainerPoint([l.lat1, l.lon1]), map.latLngToContainerPoint([l.lat2, l.lon2])];
  };
  /** The map's height above the sheet, px, and the selected line's anchors both there. */
  const above = (): number => map ? map.getSize().y - latest.current.covered() : 0;
  const inSight = (): boolean => {
    const e = ends(), bottom = above(), width = map ? map.getSize().x : 0;
    return !!e && e.every((q) => q.x >= 0 && q.x <= width && q.y >= 0 && q.y <= bottom);
  };
  /** Room for a line under the switch and above the sheet. */
  const roomy = (): boolean => above() - latest.current.padding().top >= SHEET_ROOM;
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
    if (!map || !canvas || stop.current === snap) return;
    const was = seen.current, started = performance.now();
    let moved = false, frame = 0;
    const onMove = () => { moved = true; };
    map.on("movestart", onMove);
    /** The least pan that brings the anchors' box into `area` (null: it does not fit there). */
    const panInto = (e: L.Point[], [left, top, right, bottom]: number[]): [number, number] | null => {
      const x0 = Math.min(e[0].x, e[1].x), x1 = Math.max(e[0].x, e[1].x);
      const y0 = Math.min(e[0].y, e[1].y), y1 = Math.max(e[0].y, e[1].y);
      if (right - left < SHEET_ROOM || bottom - top < SHEET_ROOM) return null;
      if (x1 - x0 > right - left || y1 - y0 > bottom - top) return null;
      return [x0 < left ? left - x0 : x1 > right ? right - x1 : 0, y0 < top ? top - y0 : y1 > bottom ? bottom - y1 : 0];
    };
    const bringBack = () => {
      const e = ends(), sel = view.selected;
      if (!e || !sel) return;
      const size = map.getSize(), p = latest.current.padding(), m = SHEET_MARGIN;
      const by = panInto(e, [p.left + m, p.top + m, size.x - p.right - m, size.y - p.bottom - m])
        ?? panInto(e, [m, p.top + m, size.x - m, above() - m]);
      if (!by) canvas.zoomTo(sel.row, p);
      else if (by[0] || by[1]) map.panBy([-by[0], -by[1]], {animate: false});
    };
    const check = () => {
      const el = latest.current.sheet(), target = el ? parseFloat(el.style.height) : NaN;
      const resting = !el || !(target > 0) || Math.abs(el.getBoundingClientRect().height - target) < 1;
      if (!resting && performance.now() - started < SHEET_REST_MS) { frame = requestAnimationFrame(check); return; }
      map.off("movestart", onMove);
      stop.current = snap;
      if (roomy()) {
        if (was && !moved && !inSight()) bringBack();
        seen.current = inSight();
      }
      if (col.current) col.current.dataset.sheetChecks = String(Number(col.current.dataset.sheetChecks || 0) + 1);
    };
    frame = requestAnimationFrame(check);
    return () => { cancelAnimationFrame(frame); map.off("movestart", onMove); };
  }, [snap, map, canvas]);
}

function Phone({view, data, line, nav, back, hashOf, linkOf, view3dOf, actions, ortho, base, folder, show,
                panels, onMeasured}: FrameProps) {
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
    // will give it (ui/components.tsx Sheet: peek, half of the frame, or all but the top bar)
    if (sheet && sheet.style.height) return Math.max(0, Math.round(box.bottom - sheet.getBoundingClientRect().top));
    return Math.round(snap === "peek" ? Math.min(SHEET_PEEK, box.height) : snap === "half" ? Math.max(SHEET_PEEK, box.height * 0.5)
      : box.height - SHEET_TOP);
  };
  const padding = (): Padding => barPadding(colRef.current, PHONE_TOP, covered() + BAR_BOTTOM);
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
  useViewLink(view, canvas, line, nav, hashOf, padding, onMeasured);
  useCornersAboveSheet(phoneRef, ref, true);  // the attribution and the scale above the sheet
  useRunCredits(map, data, base, folder);
  // The sheet moved: the bar's foot stays above it, and once it rests the view's rectangle is taken again (the
  // spots in view and their numbers follow)
  useFootClear(colRef, canvas, covered, () => [phoneRef.current?.querySelector(".u-sheet")], [canvas, map, snap], setPlaced);
  // The sheet rose over the selected line: the line back in sight
  useSheetKeeps(view, map, canvas, snap, colRef, () => phoneRef.current?.querySelector<HTMLElement>(".u-sheet"),
                covered, padding);

  /** The part of the viewport the map shows free of the top bar and the sheet. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    return {left: box.left, top: box.top + 64, right: box.right, bottom: box.bottom - covered()};
  };
  const p: PanelProps = {view, map: canvas, wide: false, padding, sheet: {snap, setSnap}, linkOf, view3dOf};
  return <div class="c-result c-result-phone v-result" ref={phoneRef}>
    <div class="c-col-map v-map" ref={colRef} data-choosing={choice ? choice.choices.length : undefined}>
      <div class="c-leaflet" ref={ref} />
      {/* the map's message: the first line of the status line's box while it lasts (the pilot's arrangement) */}
      <MapBar view={view} map={canvas} wide={false} sheet={snap} onSheet={setSnap} message={toast}
              hint={<span class="v-hint-slot" ref={hintRef}>{panels.hint({...p, place: "map"})}</span>} />
    </div>
    <div class="c-phone-top">
      <div class={back ? "c-pill" : "c-pill c-pill-alone"}>
        {back && <IconButton icon="back" label={back.label} plain round class="c-back" onClick={back.onClick} />}
        <span class="u-grow c-pill-name">{data.run.name}</span>
        {actions?.(true)}
        {/* slot, empty: the run's actions with icons only (`show`; a phone has no Compare), after the caller's;
            today's page draws them beside the pill, in .c-phone-top; step 3c's frame fills it */}
      </div>
    </div>
    {/* the sheet from its top: the handle, the hint (its first line, B.2 item 12), the head's row, then the body */}
    <Sheet label={t("ui.view.map.sheet")} snap={snap} onSnap={setSnap} peek={SHEET_PEEK} top={SHEET_TOP}
           header={<>{panels.hint({...p, place: "sheet"})}{panels.sheetHead(p)}</>}>
      {panels.details(p)}
      {panels.lineActions?.(p)}
      {/* slot, empty: the profile's dock (today's ProfileDock in the sheet, under the line's actions as there);
          step 3c's frame fills it */}
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
  // a measured line of a link (viewlink.ts), kept here across the phone's width, of this view only
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
