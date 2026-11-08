// C's result (c3), shared by the app (app/c/ResultPage) and a run's map.html (map/main.tsx): a header
// (the caller's way back, the run's name and date, the caller's actions such as Edit & run again, the
// run's actions) and three columns: the summary, filters and list | the map with the selected line's
// profile in a card floating over its bottom (ProfileCard) | the selected line's details. The side panels'
// edges are dragged (Splitter), a tab beside each collapses its panel to a rail of 36 px; their widths come
// from the layout kept in localStorage (layout.ts, useLayout: shared with the card), fitted to the window
// (fitColumns: a window too narrow collapses a panel, never kept). While the card is shown, the run's data
// credits fold behind their button as on a phone (columns.css .c-card-on). On phones (< 768 px) the map with a
// sheet holding the list, the details and the profile. Both show the run's data credits in the map's
// attribution (credits.ts), the choice of spots a click reached about as near (LineChooser) and the
// line's 3D view; phones have no Compare. The selected line goes into the hash
// (the caller's `hashOf`, replaced, so Back leaves the result); a hash with another line (Back,
// Forward, a copied link) opens that line, and the link of a line hidden by the filters stays while
// nothing is selected. Styles in columns.css (the class names are C's: c-*).

import L from "leaflet";
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, IconButton, Sheet, type Snap } from "../../ui/components";
import { SidePanel, useWidthOf } from "../../ui/SidePanel";
import { Icon, type IconName } from "../../ui/icons";
import { baseLayers } from "../../baselayers";
import { addShore } from "../../shoreLayer";
import type { Line, Ortho, RunData } from "../../types";
import { when } from "../../time";
import { loadRun, type LoadProgress } from "../load";
import { buildModel, type ResultModel } from "../model";
import { ResultMap, type Choice, type Padding } from "../ResultMap";
import { cx, num, useModel } from "./common";
import { useCornersAboveCard, useCornersAboveSheet } from "./corners";
import { useRunCredits } from "./credits";
import { FilterBar, MoreFilters } from "./FilterBar";
import { LineChooser, type Area } from "./LineChooser";
import { LineDetails } from "./LineDetails";
import { LinesTable } from "./LinesTable";
import { DEFAULT_LAYOUT, LIMITS, fitColumns, maxColumnWidth, type Column, type Layout } from "./layout";
import { ProfileCard, cardHeightAhead } from "./ProfileCard";
import { ProfileDock, profileShown } from "./ProfileDock";
import { ResultSummary } from "./ResultSummary";
import { RunActions, type RunActionsProps } from "./RunActions";
import { RunLoading } from "./RunLoading";
import { useLayout, type LayoutState } from "./useLayout";
import "./columns.css";

/** The header's way back: its label. */
export interface BackAction { label: string; onClick(): void }

export interface ResultColumnsProps {
  runId: string;
  /** The line of the route (#…&line=), opened in its group; `nav` changes with every navigation. */
  line: string | null;
  nav: number;
  wide: boolean;
  /** None: the header has no way back (a shared map). */
  back?: BackAction;
  /** The route's hash of the run with a selected line (its ResultModel.lineLink) or none. */
  hashOf(runId: string, line: string | null): string;
  /** The link "Copy link" gives (default: this page's address with the hash, LineDetails' appLink). */
  linkOf?(model: ResultModel, line: Line): string;
  /** The address of a line's 3D view (LineDetails' button; none without it: map.html). */
  view3dOf?(model: ResultModel, line: Line): string;
  /** Buttons before the run's actions (e.g. "Edit & run again"); `compact` on phones (icons only). */
  actions?(compact: boolean): ComponentChildren;
  /** The run's data when the caller has it (a run's map.html: its data.js); else loaded from `base`. */
  data?: RunData;
  /** The folder of the runs' folders (default "/runs/") and of this run's files (RunActionsProps). */
  base?: string;
  folder?: string;
  /** The run's actions that can work here (default all). */
  show?: RunActionsProps["show"];
  /** The run's orthophoto for this page (its cache folder is relative to the page; default as it is). */
  ortho?(data: RunData): Ortho | null;
}

const CARD_GAP = 12;  // px between the profile's card and the map's bottom (ProfileCard)

interface ViewProps extends ResultColumnsProps {
  model: ResultModel;
  data: RunData;
}

/** The line a route names: a link as it is, or the `line` of a hash (#line=… of a map, #run=…&line=… of the app). */
function linkOf(route: string | null): string | null {
  if (!route) return null;
  if (!route.startsWith("#")) return route;
  return new URLSearchParams(route.slice(1)).get("line");
}

/** The map of the result: base layers (with the run's orthophoto), zoom and scale, the run's lines (ResultMap,
 *  its choices of near spots to `onChoose`); the selected line or the area in view. */
function useResultMap(model: ResultModel, data: RunData, ortho: ResultColumnsProps["ortho"], padding: () => Padding,
                      onChoose: (choices: Choice[], at: {x: number; y: number}) => void) {
  const ref = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const [view, setView] = useState<ResultMap | null>(null);
  useEffect(() => {
    const leaflet = L.map(ref.current!, {center: data.center, zoom: 15, maxZoom: data.max_zoom});
    (window as any).FINDALINE_MAP = leaflet;  // for tests and the browser console
    const layers = baseLayers(ortho ? ortho(data) : data.ortho, data.max_zoom);
    Object.values(layers)[0].addTo(leaflet);
    const overlays: Record<string, L.Layer> = {};
    addShore(leaflet, data.shore, overlays);  // the uncertain shore: its overlay, its metres in view
    L.control.layers(layers, Object.keys(overlays).length ? overlays : undefined, {position: "topright"}).addTo(leaflet);
    L.control.scale({position: "bottomleft"}).addTo(leaflet);
    const resultMap = new ResultMap(leaflet, model, {onChoose: (choices, at) => {
      const box = leaflet.getContainer().getBoundingClientRect();
      onChoose(choices, {x: box.left + at.x, y: box.top + at.y});
    }});
    (window as any).FINDALINE_RESULT = {model, view: resultMap};
    if (model.selected) resultMap.zoomTo(model.selected.line, padding(), false);
    else resultMap.fitArea(padding(), false);
    setMap(leaflet);
    setView(resultMap);
    const observer = new ResizeObserver(() => leaflet.invalidateSize());
    observer.observe(ref.current!);
    return () => {
      observer.disconnect();
      resultMap.destroy();
      if ((window as any).FINDALINE_RESULT?.model === model) delete (window as any).FINDALINE_RESULT;
      leaflet.remove();
    };
  }, [model]);
  return {ref, map, view};
}

/** The selection follows the route's line, and the hash follows the selection. A line of the route that is not
 *  among the run's is measured where profiles can be asked and handed to `setMeasured` (the 3D view's moved
 *  anchors, or a favourite saved there). */
function useLinkedLine(model: ResultModel, line: string | null, view: ResultMap | null, padding: () => Padding,
                       nav: number, hashOf: ResultColumnsProps["hashOf"], setMeasured: (l: Line) => void) {
  useEffect(() => {
    if (!view || !line) return;
    const sel = model.selected?.line;
    if (sel && model.runOf(sel) === model.runId && model.lineLink(sel) === linkOf(line)) return;
    const found = model.openLinked(line, (measured) => { setMeasured(measured); view.zoomTo(measured, padding(), false); });
    if (found) view.zoomTo(found, padding(), false);
  }, [line, view, nav]);  // nav: Back or Forward to the same link opens it again
  useEffect(() => model.subscribe(() => {
    const sel = model.selected?.line;
    const want = sel && model.runOf(sel) === model.runId ? model.lineLink(sel) : null;
    const base = hashOf(model.runId, null), now = location.hash;
    // the hash is still this run's page (the app: #run=<id>…; a map has no other page)
    if (base && now !== base && !now.startsWith(base + "&")) return;
    const hash = hashOf(model.runId, want);
    if (now === hash) return;
    if (!want) {  // nothing selected: the link stays for a line hidden by the filters only
      const link = linkOf(now), linked = link && model.lines.find((l) => model.lineLink(l) === link);
      if (linked && !model.groupOf(linked)) return;
      if (link && (link === model.measuredLink || (!linked && model.measurableLink(link)))) return;  // outside the run: measured
    }
    history.replaceState(history.state, "", hash);
  }), [model]);
}

/** A click's choice of the spots it reached about as near, at its point in the viewport. */
type ChoiceAt = {choices: Choice[]; at: {x: number; y: number}};

/** The choice of spots is closed (`close`) by the map moving and by any change of the model (a selection, a filter). */
function useChoiceCloses(model: ResultModel, map: L.Map | null, close: () => void) {
  useEffect(() => {
    map?.on("movestart zoomstart", close);
    const stop = model.subscribe(close);
    return () => { map?.off("movestart zoomstart", close); stop(); };
  }, [model, map]);
}

/** A new selection ends a measurement (and `then`, e.g. shows the line in a phone's sheet). */
function useMeasureEnds(model: ResultModel, view: ResultMap | null, setMeasured: (l: Line | null) => void, then?: () => void) {
  useEffect(() => {
    let last = model.selected?.line;
    return model.subscribe(() => {
      const now = model.selected?.line;
      if (now === last) return;
      last = now;
      if (!now) return;
      setMeasured(null);
      model.measuredLink = null;
      view?.clearMeasure();
      then?.();
    });
  }, [model, view]);
}

function Title({data}: {data: RunData}) {
  return <div class="c-run-title">
    <b class="c-run-name">{data.run.name}</b>
    <span class="u-small">{when(data.run.created)} · {data.lines.length} {data.lines.length === 1 ? "line" : "lines"}</span>
  </div>;
}

function Back({back}: {back?: BackAction}) {
  if (!back) return null;
  return <Button kind="ghost" icon="back" class="c-back" onClick={back.onClick}>{back.label}</Button>;
}

type Side = "list" | "details";

interface ResultPanelProps {
  side: Side;
  /** The panel's accessible name. */
  label: string;
  /** The panel as the window allows it (fitColumns), and the widest it may be dragged. */
  column: Column;
  max: number;
  layout: LayoutState;
  onOpen(side: Side, open: boolean): void;
  /** A collapsed panel's rail: its icon and its vertical label. */
  rail: {icon: IconName; text: string};
  class: string;
  children: ComponentChildren;
}

/** A side panel of the columns (ui/SidePanel.tsx) on the result's kept layout: the list on the left, the details on
 *  the right, LIMITS' widths and rail. */
function ResultPanel({side, label, column, max, layout, onOpen, rail, class: cls, children}: ResultPanelProps) {
  const width = (part: Partial<Layout[Side]>): Layout =>
    ({...layout.latest.current, [side]: {...layout.latest.current[side], ...part}});
  return <SidePanel side={side === "list" ? "left" : "right"} name={side} label={label} column={column}
                    min={LIMITS[side][0]} max={max} railWidth={LIMITS.rail}
                    onWidth={(w) => layout.change(width({w}), false)} onCommit={layout.commit}
                    onReset={() => layout.change(width({w: DEFAULT_LAYOUT[side].w}), true)}
                    onOpen={(open) => onOpen(side, open)} rail={rail} class={cls}>{children}</SidePanel>;
}

/** A line's anchors both in the part of the map `padding` leaves free (with `slack` px to spare). */
function lineFree(map: L.Map, l: Line, padding: Padding, slack = 16): boolean {
  const size = map.getSize();
  return [[l.lat1, l.lon1], [l.lat2, l.lon2]].every(([lat, lon]) => {
    const p = map.latLngToContainerPoint([lat, lon]);
    return p.x >= padding.left - slack && p.x <= size.x - padding.right + slack &&
      p.y >= padding.top - slack && p.y <= size.y - padding.bottom + slack;
  });
}

function Desktop({model, data, line, nav, back, hashOf, linkOf: link, view3dOf, actions, ortho, base, folder, show}: ViewProps) {
  useModel(model);
  const [measured, setMeasured] = useState<Line | null>(null);
  const measuredNow = useRef(measured);
  measuredNow.current = measured;
  const layout = useLayout();
  const colsRef = useRef<HTMLDivElement>(null), colRef = useRef<HTMLDivElement>(null);
  const width = useWidthOf(colsRef);
  const [prefer, setPrefer] = useState<Side | null>(null);
  const fit = width ? fitColumns(layout.layout, width, prefer)
    : {list: {open: layout.layout.list.open, width: layout.layout.list.w, forced: false},
       details: {open: layout.layout.details.open, width: layout.layout.details.w, forced: false}};
  /** The profile card's height: as drawn, or as it will be when it is about to appear (a selection zooms to its
   *  line before the card is drawn). */
  const cardNow = (): number => {
    const card = colRef.current?.querySelector<HTMLElement>(":scope > .r-card");
    if (card) return card.offsetHeight;
    if (!profileShown(model, measuredNow.current)) return 0;
    return cardHeightAhead(layout.latest.current, colRef.current?.clientHeight ?? 0);
  };
  /** The map's free part: the profile's card covers its bottom. */
  const padding = (): Padding => {
    const card = cardNow();
    return {top: 24, right: 24, bottom: card ? card + CARD_GAP + 24 : 24, left: 24};
  };
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const [more, setMore] = useState(false);  // More filters shown in the list's column
  const closeChoice = () => setChoice(null);
  const {ref, map, view} = useResultMap(model, data, ortho, padding, (choices, at) => setChoice({choices, at}));
  useChoiceCloses(model, map, closeChoice);
  useLinkedLine(model, line, view, padding, nav, hashOf, setMeasured);
  useMeasureEnds(model, view, setMeasured);
  useRunCredits(map, data, base, folder);
  // The attribution and the scale stay in sight above the profile's card where it covers them
  useCornersAboveCard(ref, colRef, true);
  // The map's size follows the panels at once (also where no frame is drawn, so no ResizeObserver reports)
  useLayoutEffect(() => { map?.invalidateSize(); },
                  [map, fit.list.open, fit.list.width, fit.details.open, fit.details.width]);

  // Whether the map moves now: the selected line is checked once it stopped
  const moving = useRef(false);
  useEffect(() => {
    if (!map) return;
    const start = () => { moving.current = true; }, end = () => { moving.current = false; };
    map.on("movestart", start);
    map.on("moveend", end);
    return () => { map.off("movestart", start); map.off("moveend", end); };
  }, [map]);
  /** The card appeared or was resized: the selected line is brought out from under it. */
  const keepFree = () => {
    const l = model.selected?.line;
    if (!l || !map || !view) return;
    const check = () => { if (model.selected?.line === l && !lineFree(map, l, padding())) view.zoomTo(l, padding()); };
    if (moving.current) map.once("moveend", check);
    else check();
  };

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
    const box = ref.current!.getBoundingClientRect(), card = cardNow();
    return {left: box.left, top: box.top, right: box.right, bottom: card ? box.bottom - card - CARD_GAP : box.bottom};
  };
  const reveal = (l: Line) => { if (view && !view.inView(l)) view.zoomTo(l, padding()); };
  const zoom = (l: Line) => view?.zoomTo(l, padding());
  const closeMeasured = () => { setMeasured(null); view?.clearMeasure(); };
  const sel = model.selected, k = model.position;
  const detailsRail = !sel ? "Line details"
    : `${k >= 0 ? `Spot ${k + 1} of ${model.rows.length}` : "Spot"} · ${num(sel.line.len)} m`;

  return <div class="c-result">
    <header class="c-subtop c-result-top">
      <Back back={back} />
      <Title data={data} />
      <span class="u-grow" />
      {actions?.(false)}
      <RunActions model={model} view={view} onMeasured={setMeasured} show={show} base={base} folder={folder} />
    </header>
    <div class="c-cols" ref={colsRef}>
      <ResultPanel side="list" class="c-col-list" label="Lines" column={fit.list} max={maxColumnWidth("list", width, fit)}
                 layout={layout} onOpen={setOpen} rail={{icon: "list", text: `Lines · ${model.shown.lines}`}}>
        <div class="c-col-head"><ResultSummary model={model} />
          <FilterBar model={model} onMore={() => setMore((m) => !m)} moreOpen={more} /></div>
        {/* More filters scroll with the list: under the chips they took the whole column */}
        <div class="c-col-body">{more && <MoreFilters model={model} onClose={() => setMore(false)} />}
          <LinesTable model={model} view={view} onSelect={reveal} /></div>
      </ResultPanel>
      <div class={cx("c-col-map", profileShown(model, measured) && "c-card-on")} ref={colRef}>
        <div class="c-leaflet" ref={ref} />
        <ProfileCard model={model} view={view} measured={measured} onCloseMeasured={closeMeasured}
                     layout={layout.layout} onLayout={layout.change} onSettle={keepFree} />
      </div>
      <ResultPanel side="details" class="c-col-details" label="The selected line" column={fit.details}
                 max={maxColumnWidth("details", width, fit)} layout={layout} onOpen={setOpen}
                 rail={{icon: "info", text: detailsRail}}>
        <div class="c-col-dbody">
          {sel ? <LineDetails model={model} onZoom={zoom} onStep={reveal} linkOf={link && ((l) => link(model, l))}
                              view3dOf={view3dOf && ((l) => view3dOf(model, l))} />
            : <p class="c-pick"><Icon name="info" />Select a line on the map or in the list.</p>}
        </div>
      </ResultPanel>
    </div>
    {choice && view && <LineChooser key={`${choice.at.x},${choice.at.y}`} model={model} view={view} choices={choice.choices}
                                    at={choice.at} area={freeArea()} onClose={closeChoice} />}
  </div>;
}

function Phone({model, data, line, nav, back, hashOf, linkOf: link, view3dOf, actions, ortho, base, folder, show}: ViewProps) {
  useModel(model);
  const [measured, setMeasured] = useState<Line | null>(null);
  const [snap, setSnap] = useState<Snap>("half");
  const padding = (): Padding => ({top: 64, right: 0, bottom: Math.round(innerHeight * 0.5), left: 0});
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const {ref, map, view} = useResultMap(model, data, ortho, padding, (choices, at) => setChoice({choices, at}));
  useChoiceCloses(model, map, closeChoice);
  const phoneRef = useRef<HTMLDivElement>(null);
  useCornersAboveSheet(phoneRef, ref, true);  // the attribution and the scale above the sheet
  useLinkedLine(model, line, view, padding, nav, hashOf, (l) => measuredNow(l));
  useMeasureEnds(model, view, setMeasured, () => setSnap((s) => s === "full" ? "half" : s));
  useRunCredits(map, data, base, folder);
  // Measuring: the sheet goes down, the map is where the points are clicked
  useEffect(() => view?.onMeasuring((on) => { if (on) setSnap("peek"); }), [view]);

  /** The part of the viewport the map shows free of the top bar and the sheet. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect();
    const sheet = phoneRef.current?.querySelector(".u-sheet")?.getBoundingClientRect().top ?? box.bottom;
    return {left: box.left, top: box.top + 64, right: box.right, bottom: Math.min(box.bottom, sheet)};
  };
  const reveal = (l: Line) => { if (view && !view.inView(l)) view.zoomTo(l, padding()); };
  const zoom = (l: Line) => view?.zoomTo(l, padding());
  const measuredNow = (l: Line | null) => { setMeasured(l); if (l) setSnap("half"); };
  const closeMeasured = () => { setMeasured(null); view?.clearMeasure(); };
  // Compare needs room the phone's top bar does not have
  const phoneShow = (["measure", "share", "download"] as const).filter((a) => !show || show.includes(a));

  return <div class="c-result c-result-phone" ref={phoneRef}>
    <div class="c-col-map"><div class="c-leaflet" ref={ref} /></div>
    <div class="c-phone-top">
      <div class={back ? "c-pill" : "c-pill c-pill-alone"}>
        {back && <IconButton icon="back" label={back.label} plain round class="c-back" onClick={back.onClick} />}
        <span class="u-grow c-pill-name">{data.run.name}</span>
        {actions?.(true)}
      </div>
      <RunActions model={model} view={view} onMeasured={measuredNow} compact show={phoneShow} base={base} folder={folder} />
    </div>
    <Sheet label="Results" snap={snap} onSnap={setSnap} peek={132} top={64}
           header={model.selected ? <LineDetails model={model} part="head" onStep={reveal} />
             : <ResultSummary model={model} legend={false} />}>
      {model.selected && <LineDetails model={model} part="body" onZoom={zoom} linkOf={link && ((l) => link(model, l))}
                                      view3dOf={view3dOf && ((l) => view3dOf(model, l))} />}
      <ProfileDock model={model} view={view} measured={measured} onCloseMeasured={closeMeasured} class="r-dock-sheet" />
      {model.selected && <ResultSummary model={model} />}
      <FilterBar model={model} />
      <LinesTable model={model} view={view} onSelect={reveal} follow={false} />
    </Sheet>
    {choice && view && <LineChooser key={`${choice.at.x},${choice.at.y}`} model={model} view={view} choices={choice.choices}
                                    at={choice.at} area={freeArea()} dock onClose={closeChoice} />}
  </div>;
}

/** A run's result in columns (on a phone a map with a sheet): loaded first unless the caller has its data, its
 *  model built after the page painted the phase (RunLoading shows the load's progress). */
export function ResultColumns(props: ResultColumnsProps) {
  const [model, setModel] = useState<ResultModel | null>(null);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    const report = (p: LoadProgress) => { if (live) setProgress(p); };
    setModel(null);
    setProgress(null);
    setError("");
    (props.data ? Promise.resolve(props.data) : loadRun(props.runId, props.base, report))
      .then((d) => live ? buildModel(d, {list: {sort: "clr", desc: true}}, report) : null)
      .then((m) => { if (live && m) setModel(m); }, (e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [props.runId]);
  if (!model || model.runId !== props.runId) {
    return <RunLoading progress={progress} error={error}><Back back={props.back} /></RunLoading>;
  }
  const data = model.data;
  const view = {...props, model, data};
  return props.wide ? <Desktop key="wide" {...view} /> : <Phone key="phone" {...view} />;
}
