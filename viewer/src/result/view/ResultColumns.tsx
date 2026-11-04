// C's result (c3), shared by the app (app/c/ResultPage) and a run's map.html (map/main.tsx): a header
// (the caller's way back, the run's name and date, the caller's actions such as Edit & run again, the
// run's actions) and three columns: the summary, filters and list | the map with the selected line's
// profile in a card floating over its bottom (ProfileCard) | the selected line's details. The side panels'
// edges are dragged (Splitter), a tab beside each collapses its panel to a rail of 36 px; their widths come
// from the layout kept in localStorage (layout.ts, useLayout: shared with the card), fitted to the window
// (fitColumns: a window too narrow collapses a panel, never kept). While the card is shown, the run's data
// credits fold behind their button as on a phone (columns.css .c-card-on). On phones (< 768 px) the map with a
// sheet holding the list, the details and the profile. Taken from D (ResultWorkspace): the run's data
// credits in the map's attribution (credits.ts), the choice of spots a click reached about as near
// (LineChooser), the line's 3D view, no Compare on phones. The selected line goes into the hash
// (the caller's `hashOf`, replaced, so Back leaves the result); a hash with another line (Back,
// Forward, a copied link) opens that line, and the link of a line hidden by the filters stays while
// nothing is selected. Styles in columns.css (the class names are C's: c-*).

import L from "leaflet";
import type { ComponentChildren, RefObject } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, IconButton, Sheet, Splitter, type Snap } from "../../ui/components";
import { Icon, type IconName } from "../../ui/icons";
import { baseLayers } from "../../baselayers";
import type { Line, Ortho, RunData } from "../../types";
import { when } from "../../time";
import { loadRun } from "../load";
import { ResultModel } from "../model";
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
import { RunActions } from "./RunActions";
import type { BackAction, ResultWorkspaceProps } from "./ResultWorkspace";
import { useLayout, type LayoutState } from "./useLayout";
import "./columns.css";

export type ResultColumnsProps = Omit<ResultWorkspaceProps, "map"> & {
  /** The run's orthophoto for this page (its cache folder is relative to the page; default as it is). */
  ortho?(data: RunData): Ortho | null;
};

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
    L.control.layers(layers, undefined, {position: "topright"}).addTo(leaflet);
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

/** The selection follows the route's line, and the hash follows the selection. */
function useLinkedLine(model: ResultModel, line: string | null, view: ResultMap | null, padding: () => Padding,
                       nav: number, hashOf: ResultColumnsProps["hashOf"]) {
  useEffect(() => {
    if (!view || !line) return;
    const sel = model.selected?.line;
    if (sel && model.runOf(sel) === model.runId && model.lineLink(sel) === linkOf(line)) return;
    const found = model.openLinked(line);
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

/** The width of the element `ref` holds: measured after every render (where no frame is drawn too), on a window
 *  resize and by a ResizeObserver. */
function useWidthOf(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => { if (ref.current) setWidth(ref.current.clientWidth); });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(element.clientWidth);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(element);
    addEventListener("resize", measure);
    return () => { observer?.disconnect(); removeEventListener("resize", measure); };
  }, []);
  return width;
}

interface SidePanelProps {
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

/** A side panel of the columns: its content, its edge to the map (a Splitter for the width: a double click the
 *  default, Enter collapses) with the round collapse tab beside it (a sibling: a separator's children are
 *  presentational); collapsed a rail of LIMITS.rail px, one button expanding it, marked "auto" when the
 *  window collapsed it. The content stays drawn while collapsed (hidden: its scroll and state are kept). */
function SidePanel({side, label, column, max, layout, onOpen, rail, class: cls, children}: SidePanelProps) {
  const list = side === "list";
  const width = (part: Partial<Layout[Side]>): Layout =>
    ({...layout.latest.current, [side]: {...layout.latest.current[side], ...part}});
  const style = {"--c-w": `${column.open ? column.width : LIMITS.rail}px`} as Record<string, string>;
  return <aside class={cx(cls, "c-col-side", !column.open && "c-collapsed", !column.open && column.forced && "c-forced")}
                style={style} aria-label={label}>
    {children}
    {column.open ? <>
      <Splitter orientation="vertical" class="c-split" label={`Width of the ${side}`} grow={list ? 1 : -1}
                value={column.width} min={LIMITS[side][0]} max={max}
                onChange={(w) => layout.change(width({w}), false)} onCommit={layout.commit}
                onReset={() => layout.change(width({w: DEFAULT_LAYOUT[side].w}), true)}
                onToggle={() => onOpen(side, false)} />
      <button type="button" class="u-split-tab c-col-tab" aria-label={`Collapse the ${side}`}
              title={`Collapse the ${side}`} onClick={() => onOpen(side, false)}>
        <Icon name={list ? "back" : "next"} /></button>
    </> : <button type="button" class="c-rail" aria-label={`Expand the ${side}`} title={`Expand the ${side}`}
                  onClick={() => onOpen(side, true)}>
      <Icon name={rail.icon} />
      <span class="c-rail-text">{rail.text}</span>
      <span class="u-split-tab c-rail-tab" aria-hidden="true"><Icon name={list ? "next" : "back"} /></span>
      {column.forced && <span class="c-rail-auto">auto</span>}
    </button>}
  </aside>;
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
  useLinkedLine(model, line, view, padding, nav, hashOf);
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
      <SidePanel side="list" class="c-col-list" label="Lines" column={fit.list} max={maxColumnWidth("list", width, fit)}
                 layout={layout} onOpen={setOpen} rail={{icon: "list", text: `Lines · ${model.shown.lines}`}}>
        <div class="c-col-head"><ResultSummary model={model} />
          <FilterBar model={model} onMore={() => setMore((m) => !m)} moreOpen={more} /></div>
        {/* More filters scroll with the list: under the chips they took the whole column */}
        <div class="c-col-body">{more && <MoreFilters model={model} onClose={() => setMore(false)} />}
          <LinesTable model={model} view={view} onSelect={reveal} /></div>
      </SidePanel>
      <div class={cx("c-col-map", profileShown(model, measured) && "c-card-on")} ref={colRef}>
        <div class="c-leaflet" ref={ref} />
        <ProfileCard model={model} view={view} measured={measured} onCloseMeasured={closeMeasured}
                     layout={layout.layout} onLayout={layout.change} onSettle={keepFree} />
      </div>
      <SidePanel side="details" class="c-col-details" label="The selected line" column={fit.details}
                 max={maxColumnWidth("details", width, fit)} layout={layout} onOpen={setOpen}
                 rail={{icon: "info", text: detailsRail}}>
        <div class="c-col-dbody">
          {sel ? <LineDetails model={model} onZoom={zoom} onStep={reveal} linkOf={link && ((l) => link(model, l))}
                              view3dOf={view3dOf && ((l) => view3dOf(model, l))} />
            : <p class="c-pick"><Icon name="info" />Select a line on the map or in the list.</p>}
        </div>
      </SidePanel>
    </div>
    {choice && view && <LineChooser key={`${choice.at.x},${choice.at.y}`} model={model} view={view} choices={choice.choices}
                                    at={choice.at} area={freeArea()} onClose={closeChoice} />}
  </div>;
}

function Phone({model, data, line, nav, back, hashOf, linkOf: link, view3dOf, actions, menu, ortho, base, folder, show}: ViewProps) {
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
  useLinkedLine(model, line, view, padding, nav, hashOf);
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
  // Compare needs room the phone's top bar does not have (as D)
  const phoneShow = (["measure", "share", "download"] as const).filter((a) => !show || show.includes(a));

  return <div class="c-result c-result-phone" ref={phoneRef}>
    <div class="c-col-map"><div class="c-leaflet" ref={ref} /></div>
    <div class="c-phone-top">
      {menu}
      <div class={back ? "c-pill" : "c-pill c-pill-alone"}>
        {back && <IconButton icon="back" label={back.label} plain round class="c-back" onClick={back.onClick} />}
        <span class="u-grow c-pill-name">{data.run.name}</span>
        {actions?.(true)}
      </div>
      <RunActions model={model} view={view} onMeasured={measuredNow} compact show={phoneShow} base={base} folder={folder} />
    </div>
    <Sheet label="Results" desktop="sheet" snap={snap} onSnap={setSnap} peek={132} top={64}
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

/** A run's result in columns (on a phone a map with a sheet): loaded first unless the caller has its data. */
export function ResultColumns(props: ResultColumnsProps) {
  const [data, setData] = useState<RunData | null>(props.data || null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (props.data) { props.onData?.(props.data); return; }
    let live = true;
    setData(null);
    setError("");
    loadRun(props.runId, props.base).then((d) => { if (!live) return; props.onData?.(d); setData(d); },
                                          (e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [props.runId]);
  const model = useMemo(() => data && new ResultModel(data, {list: {sort: "clr", desc: true}}), [data]);
  if (!data || !model || data.run.id !== props.runId) {
    return <div class="c-result-wait"><Back back={props.back} />
      {error ? <p class="c-error">{error}</p> : <p class="u-small">Loading the run…</p>}</div>;
  }
  const view = {...props, model, data};
  return props.wide ? <Desktop key="wide" {...view} /> : <Phone key="phone" {...view} />;
}
