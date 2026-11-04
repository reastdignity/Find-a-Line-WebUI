// ?ui=kit-result&run=<id>: the results UI (result/view) on its own, to develop and test its pieces
// without the interface: the run's map (loadRun, ResultMap) beside a panel on the left (summary, filters, the
// list with the selected line's details under its row) whose edge is dragged (Splitter; ‹ collapses
// it to a rail), the profile as a card over the bottom of the map (ProfileCard: its top and side edges
// dragged, folded) and the run's actions on top; the layout kept as C's (layout.ts). Below 768 px the
// panel is a sheet with the profile inside. #line=<lat1,lon1,lat2,lon2> (or #run=…&line=…) opens
// that line. ?theme=light|dark picks a theme.

import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { DESKTOP, Screen, Sheet, Splitter, useMedia, type Snap, type Theme } from "../../ui/components";
import { Icon, Logo } from "../../ui/icons";
import { storedTheme, uiHref } from "../../ui/choice";
import { api, type RunListed } from "../../app/api";
import { baseLayers } from "../../baselayers";
import type { Line, RunData } from "../../types";
import { loadRun, orthoForApp } from "../load";
import { ResultModel } from "../model";
import { ResultMap, type Padding } from "../ResultMap";
import { useCornersAboveCard, useCornersAboveSheet } from "./corners";
import { FilterBar } from "./FilterBar";
import { LineDetails } from "./LineDetails";
import { LinesTable } from "./LinesTable";
import { ProfileDock } from "./ProfileDock";
import { ProfileCard } from "./ProfileCard";
import { DEFAULT_LAYOUT, LIMITS, type Layout } from "./layout";
import { useLayout } from "./useLayout";
import { ResultSummary } from "./ResultSummary";
import { RunActions } from "./RunActions";
import { useModel } from "./common";
import { day, when } from "../../time";

/** The panel's greatest width in a window `width` px wide (the map keeps LIMITS.map). */
const panelMax = (width: number) => Math.min(LIMITS.list[1], width - LIMITS.map);

/** The panel's width in a window `width` px wide; 0: no room for it (collapsed by the window). */
function panelWidth(layout: Layout, width: number): number {
  const most = panelMax(width);
  return most < LIMITS.list[0] ? 0 : Math.max(LIMITS.list[0], Math.min(most, layout.list.w));
}

/** The window's width, followed. */
function useWidth(): number {
  const [width, setWidth] = useState(innerWidth);
  useEffect(() => {
    const changed = () => setWidth(innerWidth);
    addEventListener("resize", changed);
    return () => removeEventListener("resize", changed);
  }, []);
  return width;
}

/** The `line` of a link: "#line=…" or "#run=…&line=…". */
function linkedLine(hash: string): string | null {
  if (!hash || hash === "#") return null;
  return new URLSearchParams(hash.slice(1)).get("line");
}

function RunPicker() {
  const [runs, setRuns] = useState<RunListed[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.runs().then((r) => setRuns(r.runs), (e) => setError(e.message)); }, []);
  const href = (id: string) => `${uiHref("kit-result")}&run=${encodeURIComponent(id)}`;
  return <div class="u-stub">
    <Logo />
    <h1 class="u-h u-xl">Results UI: pick a run</h1>
    {error && <p class="r-error">{error}</p>}
    {runs === null ? <p class="u-small">Loading…</p> : runs.length === 0 ? <p>No saved runs yet.</p>
      : <ul class="r-runs">{runs.filter((r) => r.has_map).map((r) => <li key={r.id}>
          <a href={href(r.id)}>{r.name}</a> <span class="u-small">{when(r.created)} ·
            {" "}{r.summary.spots} spots, {r.summary.lines} lines</span></li>)}</ul>}
    <a href={uiHref("kit")}>Component gallery</a>
  </div>;
}

function Result({data}: {data: RunData}) {
  const wide = useMedia(DESKTOP);
  const model = useMemo(() => new ResultModel(data), [data]);
  useModel(model);
  const mapRef = useRef<HTMLDivElement>(null);
  const kitRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<ResultMap | null>(null);
  const [measured, setMeasured] = useState<Line | null>(null);
  const [snap, setSnap] = useState<Snap>("half");
  const wideRef = useRef(wide);
  wideRef.current = wide;

  const {layout, latest, change: changeLayout, commit} = useLayout();
  const width = useWidth();

  /** The parts of the map the top pill and the profile card cover. */
  const padding = (): Padding => {
    if (!wideRef.current) return {top: 60, right: 0, bottom: Math.round(innerHeight * 0.5), left: 0};
    const card = kitRef.current?.querySelector<HTMLElement>(".r-card")?.offsetHeight ?? 0;
    return {top: 64, right: 16, bottom: card ? card + 24 : 16, left: 16};
  };

  useEffect(() => {
    const map = L.map(mapRef.current!, {center: data.center, zoom: 15, maxZoom: data.max_zoom});
    (window as any).FINDALINE_MAP = map;  // for tests and the browser console
    const layers = baseLayers(orthoForApp(data.ortho, data.run.id), data.max_zoom);
    Object.values(layers)[0].addTo(map);
    L.control.layers(layers, undefined, {position: "topleft"}).addTo(map);
    L.control.scale({position: "bottomleft"}).addTo(map);
    const resultMap = new ResultMap(map, model);
    (window as any).FINDALINE_RESULT = {model, view: resultMap};
    resultMap.fitArea(padding(), false);
    setView(resultMap);
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(mapRef.current!);
    const open = () => {
      const wanted = linkedLine(location.hash);
      if (!wanted) return;
      const line = model.openLinked(wanted);
      if (line) resultMap.zoomTo(line, padding(), false);
    };
    open();
    window.addEventListener("hashchange", open);
    return () => {
      window.removeEventListener("hashchange", open);
      observer.disconnect();
      resultMap.destroy();
      map.remove();
    };
  }, [model]);

  // A new selection ends a measurement and shows the line on a phone's sheet
  useEffect(() => {
    let last = model.selected?.line;
    return model.subscribe(() => {
      const now = model.selected?.line;
      if (now === last) return;
      last = now;
      if (!now) return;
      setMeasured(null);
      view?.clearMeasure();
      if (!wideRef.current) setSnap((s) => s === "full" ? "half" : s);
    });
  }, [model, view]);

  /** Bring a line into the map's view (a row or ‹ › chose it). */
  const reveal = (l: Line) => { if (view && !view.inView(l)) view.zoomTo(l, padding()); };
  const zoom = (l: Line) => view?.zoomTo(l, padding());
  const measuredNow = (l: Line | null) => { setMeasured(l); if (l && !wide) setSnap("half"); };
  const closeMeasured = () => { setMeasured(null); view?.clearMeasure(); };
  useCornersAboveSheet(kitRef, mapRef, !wide);  // the attribution and the scale above the sheet
  useCornersAboveCard(mapRef, kitRef, wide);  // ... and above the profile card where it covers them
  const details = <LineDetails model={model} onZoom={zoom} onStep={reveal} />;
  const title = <div class="r-pill">
    <a class="u-ib u-plain u-round" href={uiHref("kit-result")} aria-label="All runs" title="All runs">‹</a>
    <span class="u-grow r-pill-name">{data.run.name}</span>
    <span class="u-small">{day(data.run.created)}</span>
  </div>;

  const panel = panelWidth(layout, width), open = layout.list.open && panel > 0;
  const toggle = (on: boolean) => changeLayout({...latest.current, list: {...latest.current.list, open: on}}, true);
  const list = (part: Partial<Layout["list"]>): Layout => ({...latest.current, list: {...latest.current.list, ...part}});
  const columns = wide && (open ? <aside class="r-panel" aria-label="Results" style={{width: `${panel}px`}}>
    <div class="r-panel-head"><ResultSummary model={model} /><FilterBar model={model} /></div>
    <div class="r-panel-body"><LinesTable model={model} view={view} details={details} onSelect={reveal} /></div>
    <Splitter orientation="vertical" class="r-kit-split" label="Width of the list" grow={1}
              value={panel} min={LIMITS.list[0]} max={Math.max(LIMITS.list[0], panelMax(width))}
              onChange={(w) => changeLayout(list({w}), false)} onCommit={commit}
              onReset={() => changeLayout(list({w: DEFAULT_LAYOUT.list.w}), true)} onToggle={() => toggle(false)} />
    {/* beside the edge, not in it: a separator's children are presentational */}
    <button type="button" class="u-split-tab r-kit-tab" aria-label="Collapse the list" title="Collapse the list"
            onClick={() => toggle(false)}><Icon name="back" /></button>
  </aside> : <button type="button" class="r-kit-rail" aria-label="Expand the list" disabled={panel === 0}
                     onClick={() => toggle(true)}>
    <Icon name="list" /><span>Lines · {model.shown.lines}</span>
  </button>);

  return <div class="r-kit-main">
    {columns}
    <div class="r-kit-map" ref={kitRef}>
      <div class="r-kit-leaflet" ref={mapRef} />
      <div class="r-kit-top">{title}
        {!wide && <RunActions model={model} view={view} onMeasured={measuredNow} compact />}</div>
      {wide && <div class="r-kit-actions"><RunActions model={model} view={view} onMeasured={measuredNow} /></div>}
      {wide ? <ProfileCard model={model} view={view} measured={measured} onCloseMeasured={closeMeasured}
                           layout={layout} onLayout={changeLayout} /> : <Sheet label="Results" snap={snap} onSnap={setSnap} peek={132}
                        header={model.selected ? <LineDetails model={model} part="head" onStep={reveal} />
                          : <ResultSummary model={model} legend={false} />}>
        {model.selected && <LineDetails model={model} part="body" onZoom={zoom} />}
        <ProfileDock model={model} view={view} measured={measured} onCloseMeasured={closeMeasured} class="r-dock-sheet" />
        {model.selected && <ResultSummary model={model} />}
        <FilterBar model={model} />
        <LinesTable model={model} view={view} onSelect={reveal} follow={false} />
      </Sheet>}
    </div>
  </div>;
}

export function KitResult() {
  const params = new URLSearchParams(location.search);
  const runId = params.get("run");
  const asked = params.get("theme");
  const theme: Theme = asked === "light" || asked === "dark" ? asked : storedTheme();
  const [data, setData] = useState<RunData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (runId) loadRun(runId).then(setData, (e) => setError(e.message)); }, [runId]);
  return <Screen theme={theme} class="r-kit">
    {!runId ? <RunPicker /> : error ? <div class="u-stub"><p class="r-error">{error}</p>
      <a href={uiHref("kit-result")}>All runs</a></div>
      : !data ? <div class="u-stub"><p class="u-small">Loading the run…</p></div> : <Result data={data} />}
  </Screen>;
}

