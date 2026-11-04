// C's result (c3), shared by the app (app/c/ResultPage) and a run's map.html (map/main.tsx): a header
// (the caller's way back, the run's name and date, the caller's actions such as Edit & run again, the
// run's actions) and three columns: the summary, filters and list | the map with the selected line's
// profile floating over its bottom | the selected line's details. On phones (< 768 px) the map with a
// sheet holding the list, the details and the profile. Taken from D (ResultWorkspace): the run's data
// credits in the map's attribution (credits.ts), the choice of spots a click reached about as near
// (LineChooser), the line's 3D view, no Compare on phones. The selected line goes into the hash
// (the caller's `hashOf`, replaced, so Back leaves the result); a hash with another line (Back,
// Forward, a copied link) opens that line, and the link of a line hidden by the filters stays while
// nothing is selected. Styles in columns.css (the class names are C's: c-*).

import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, IconButton, Sheet, type Snap } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { baseLayers } from "../../baselayers";
import type { Line, Ortho, RunData } from "../../types";
import { when } from "../../time";
import { loadRun } from "../load";
import { ResultModel } from "../model";
import { ResultMap, type Choice, type Padding } from "../ResultMap";
import { useModel } from "./common";
import { useCornersAboveSheet, useCornersBesidePanel } from "./corners";
import { useRunCredits } from "./credits";
import { FilterBar } from "./FilterBar";
import { LineChooser, type Area } from "./LineChooser";
import { LineDetails } from "./LineDetails";
import { LinesTable } from "./LinesTable";
import { ProfileDock } from "./ProfileDock";
import { ResultSummary } from "./ResultSummary";
import { RunActions } from "./RunActions";
import type { BackAction, ResultWorkspaceProps } from "./ResultWorkspace";
import "./columns.css";

export type ResultColumnsProps = Omit<ResultWorkspaceProps, "map"> & {
  /** The run's orthophoto for this page (its cache folder is relative to the page; default as it is). */
  ortho?(data: RunData): Ortho | null;
};

const SLOT_GAP = 12;  // px between the profile's card and the map's edges (columns.css .c-dock-slot)

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

function Desktop({model, data, line, nav, back, hashOf, linkOf: link, view3dOf, actions, ortho, base, folder, show}: ViewProps) {
  useModel(model);
  const [measured, setMeasured] = useState<Line | null>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  /** The map's free part: the profile's card covers its bottom. */
  const padding = (): Padding => {
    const card = slotRef.current?.offsetHeight ?? 0;
    return {top: 24, right: 24, bottom: card ? card + SLOT_GAP + 24 : 24, left: 24};
  };
  const [choice, setChoice] = useState<ChoiceAt | null>(null);
  const closeChoice = () => setChoice(null);
  const {ref, map, view} = useResultMap(model, data, ortho, padding, (choices, at) => setChoice({choices, at}));
  useChoiceCloses(model, map, closeChoice);
  useLinkedLine(model, line, view, padding, nav, hashOf);
  useMeasureEnds(model, view, setMeasured);
  useRunCredits(map, data, base, folder);
  // The attribution and the scale stay in sight above the profile's card
  useCornersBesidePanel(ref, slotRef, 0, SLOT_GAP, true);

  /** The part of the viewport the map shows free of the profile's card. */
  const freeArea = (): Area => {
    const box = ref.current!.getBoundingClientRect(), card = slotRef.current?.offsetHeight ?? 0;
    return {left: box.left, top: box.top, right: box.right, bottom: card ? box.bottom - card - SLOT_GAP : box.bottom};
  };
  const reveal = (l: Line) => { if (view && !view.inView(l)) view.zoomTo(l, padding()); };
  const zoom = (l: Line) => view?.zoomTo(l, padding());
  const closeMeasured = () => { setMeasured(null); view?.clearMeasure(); };

  return <div class="c-result">
    <header class="c-subtop c-result-top">
      <Back back={back} />
      <Title data={data} />
      <span class="u-grow" />
      {actions?.(false)}
      <RunActions model={model} view={view} onMeasured={setMeasured} show={show} base={base} folder={folder} />
    </header>
    <div class="c-cols">
      <aside class="c-col-list" aria-label="Lines">
        <div class="c-col-head"><ResultSummary model={model} /><FilterBar model={model} /></div>
        <div class="c-col-body"><LinesTable model={model} view={view} onSelect={reveal} /></div>
      </aside>
      <div class="c-col-map">
        <div class="c-leaflet" ref={ref} />
        <div class="c-dock-slot" ref={slotRef}>
          <ProfileDock model={model} view={view} measured={measured} onCloseMeasured={closeMeasured} />
        </div>
      </div>
      <aside class="c-col-details" aria-label="The selected line">
        {model.selected ? <LineDetails model={model} onZoom={zoom} onStep={reveal} linkOf={link && ((l) => link(model, l))}
                                       view3dOf={view3dOf && ((l) => view3dOf(model, l))} />
          : !measured && <p class="c-pick"><Icon name="info" />Select a line on the map or in the list.</p>}
      </aside>
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
