// The highline layer (#layer; the local app and administrators): the countries searched offline in fixed tiles
// (country.py) keep only counts, in counter cubes of 1, 2, 4 and 8 km cells (countcube.py). The page browses
// every cube at once: the cells of the cubes in view (/api/countries/<id>/cells) on the map, coloured by their
// density per km² (cellsLayer.ts: the fixed classes, or classes fitted to the view), the histograms of the
// counts in view per bin of each dimension (/histogram, LayerHistograms.tsx) on the right, the filters, the
// legend, the level and the selected cell with one "Search here" per layer band (#new&cell=…, NewSearch) on the
// left; at low zoom the countries' outlines (/outline) instead of cells. Every filter and the view are in the
// hash (layerState.ts), written in place on every change, read back on Back or a pasted link.
// The source of the cubes, cells, histograms and outlines is a prop: the server (SERVER), or canned data
// (?ui=kit-layer, Gallery).

import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import L from "leaflet";
import { Button, Field, Segmented } from "../../ui/components";
import { ApiError, api, user, type CountryCells, type CountryCube, type CountryHistogram, type CountryOutline } from "../api";
import type { PlaceMap } from "../PlaceMap";
import { creditsHtml } from "../../layers";
import { t } from "../../i18n";
import { day } from "../../time";
import { copy, LinkField } from "../../result/view/LineDetails";
import { MapPage } from "./Account";
import { cellHash, go, layerHash } from "./route";
import { CLASS_BREAKS, CellsLayer, rowBounds, short, type DrawnCells, type LayerMode, type OutlineShape,
         type PickedCell } from "./cellsLayer";
import { LayerHistograms, addHistogram, emptyHistogram, type Dimension, type SummedHistogram } from "./LayerHistograms";
import { OUTLINE_MPP, REQUEST_CELLS_MAX, autoLevel, cellsAt, cubesIn, largestRequest, easedBreaks, filtersQuery, filtersSet, metresPerPixel, parseState,
         quantileBreaks, stateParams, type Box, type LayerLevel, type LayerState } from "./layerState";
import "./c.css";

export type { LayerMode } from "./cellsLayer";
export { CLASS_BREAKS, densityClass, short } from "./cellsLayer";
export type { PickedCell } from "./cellsLayer";
export { filtersQuery as cellsQuery } from "./layerState";

/** Where the page gets its cubes, cells, histograms and outlines: the server, or the demo's canned data. */
export interface LayerSource {
  countries(): Promise<{countries: CountryCube[]}>;
  cells(id: string, query: Record<string, string>, signal: AbortSignal): Promise<CountryCells>;
  histogram(id: string, query: Record<string, string>, signal: AbortSignal): Promise<CountryHistogram>;
  outline(id: string, signal?: AbortSignal): Promise<CountryOutline>;
}
export const SERVER: LayerSource = {countries: api.countries, cells: api.countryCells, histogram: api.countryHistogram,
                                    outline: api.countryOutline};

export const DEBOUNCE_MS = 300;
export const EASE_MS = 500;           // a refit of the colour scale eases over this

type Status = "waiting" | "loading" | "ready" | "too-many" | "error";

/** The legend's label of each class, compact ("10k–300k": five fit the panel's width on one line each). */
function classLabels(b: number[]): string[] {
  const s = (n: number) => short(n).replace(" ", "");
  return [`< ${s(b[0])}`, ...b.slice(1).map((x, k) => `${s(b[k])}–${s(x)}`), `≥ ${s(b[b.length - 1])}`];
}

/** A select of [value, text] options. */
function NumberSelect({id, value, options, label, onChange}:
                      {id: string; value: string; options: [string, string][]; label?: string; onChange(v: string): void}) {
  return <select id={id} class="u-input" value={value} aria-label={label}
                 onChange={(e) => onChange((e.target as HTMLSelectElement).value)}>
    {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
  </select>;
}

const boxOf = (b: L.LatLngBounds): Box => [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
const boundsOf = (box: Box) => L.latLngBounds([box[1], box[0]], [box[3], box[2]]);
/** A box grown by `p` of its width and height on every side. */
const padded = (box: Box, p: number): Box => {
  const w = (box[2] - box[0]) * p, h = (box[3] - box[1]) * p;
  return [box[0] - w, Math.max(-85, box[1] - h), box[2] + w, Math.min(85, box[3] + h)];
};

/** The count of the cells reaching the view. */
function totalIn(cells: DrawnCells[], view: L.LatLngBounds): number {
  let total = 0;
  for (const {data} of cells) for (const row of data.cells) if (view.intersects(rowBounds(row))) total += row[2];
  return total;
}

/** The densities per km² of every cell. */
function densities(cells: DrawnCells[]): number[] {
  const out: number[] = [];
  for (const {data} of cells) {
    const km2 = (data.cell_m / 1000) ** 2;
    for (const row of data.cells) out.push(row[2] / km2);
  }
  return out;
}

interface Cache { box: L.LatLngBounds; level: number; key: string; cells: DrawnCells[] }

/** The panel of the highline layer, on `place`'s map; `aside`: the element of the right panel (the histograms).
 *  `params`: the hash's parameters the page opened with; `pick`: the demo's way to select a cell of the first answer. */
export function LayerPanel({place, aside, source, params, pick}:
                           {place: PlaceMap; aside: HTMLElement | null; source: LayerSource; params: URLSearchParams;
                            pick?: (data: CountryCells) => number[] | null}) {
  const [cubes, setCubes] = useState<CountryCube[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    source.countries().then((r) => setCubes(r.countries), (e) => setError(e.message));
  }, [source]);
  if (error) return <p class="c-error" role="alert">{error}</p>;
  if (!cubes) return <p class="u-small">{t("ui.layer.loading")}</p>;
  if (!cubes.length) {
    return <p class="u-small">{t("ui.layer.none")}
      <span class="u-mono"> findaline.py country run &lt;id&gt;</span>, {t("ui.layer.then")}
      <span class="u-mono"> country build &lt;id&gt;</span>.</p>;
  }
  return <Explorer place={place} aside={aside} source={source} cubes={cubes} params={params} pick={pick} />;
}

function Explorer({place, aside, source, cubes, params, pick}:
                  {place: PlaceMap; aside: HTMLElement | null; source: LayerSource; cubes: CountryCube[];
                   params: URLSearchParams; pick?: (data: CountryCells) => number[] | null}) {
  const cube0 = cubes[0];
  const [state, setState] = useState<LayerState>(() => parseState(params, cube0));
  const [moves, setMoves] = useState(0);       // map moves seen
  const [theme, setTheme] = useState(0);       // theme changes seen (the canvas reads the tokens)
  const [cells, setCells] = useState<DrawnCells[]>([]);
  const [outlines, setOutlines] = useState<OutlineShape[]>([]);
  const [status, setStatus] = useState<Status>("waiting");
  const [message, setMessage] = useState("");
  const [hist, setHist] = useState<SummedHistogram | null>(null);
  const [histStatus, setHistStatus] = useState<"waiting" | "ready" | "error">("waiting");
  const [histError, setHistError] = useState("");
  const [picked, setPicked] = useState<PickedCell | null>(null);
  const [level, setLevel] = useState(cube0.levels[0]);
  const [inView, setInView] = useState<CountryCube[]>([cube0]);
  const [outlineMode, setOutlineMode] = useState(false);
  const [total, setTotal] = useState(0);
  const [fitBreaks, setFitBreaks] = useState<number[] | null>(null);
  const [legend, setLegend] = useState<number[]>(CLASS_BREAKS[state.mode]);
  const [copied, setCopied] = useState<"" | "ok" | "fail">("");
  const layer = useRef<CellsLayer | null>(null);
  const picking = useRef(pick);
  const written = useRef("");                   // the hash this page wrote last
  const stateRef = useRef(state);
  stateRef.current = state;
  const autoL = useRef<number | null>(null);    // the automatic level in force (hysteresis)
  const cache = useRef<Cache | null>(null);     // the cells of the padded box they were asked for
  const cellsRef = useRef<DrawnCells[]>([]);
  cellsRef.current = cells;
  const shown = useRef<number[] | null>(null);  // the breaks the cells are coloured by now (eased)
  const anim = useRef(0);
  const outlineCache = useRef(new Map<string, Promise<CountryOutline>>());
  const set = (change: Partial<LayerState>) => setState((s) => ({...s, ...change}));
  const mode: LayerMode = state.mode;

  const choose = (country: string, row: number[]) => {
    const answer = cellsRef.current.find((c) => c.country === country)?.data;
    if (answer) setPicked({country, level: answer.level, cell_m: answer.cell_m, i: row[0], j: row[1], count: row[2], corners: row.slice(3)});
  };
  const fitCountry = (id: string) => {
    const cube = cubes.find((c) => c.id === id);
    if (!cube) return;
    const [west, south, east, north] = cube.bounds_wgs84;
    place.map.fitBounds([[south, west], [north, east]], {animate: false});
  };

  // The map: the first view, the cells' layer, the moves, the theme and the hash followed
  useEffect(() => {
    const map = place.map;
    const first = stateRef.current;
    if (first.view) map.setView([first.view.lat, first.view.lon], first.view.zoom, {animate: false});
    else fitCountry(first.country && cubes.some((c) => c.id === first.country) ? first.country : cube0.id);
    const noun = () => stateRef.current.mode === "lines" ? t("ui.layer.lines") : t("ui.layer.spots");
    layer.current = new CellsLayer(map, choose, fitCountry, (count, density) =>
      `${count.toLocaleString("en")} ${noun()} · ${short(density)} ${t("ui.layer.per_km2")}`);
    const moved = () => {
      const c = map.getCenter();
      set({view: {lat: c.lat, lon: c.lng, zoom: map.getZoom()}});
      setMoves((v) => v + 1);
    };
    const clicked = () => setPicked(null);
    map.on("moveend", moved);
    map.on("click", clicked);
    const root = map.getContainer().closest(".ui");
    const observer = new MutationObserver(() => setTheme((v) => v + 1));
    if (root) observer.observe(root, {attributes: true, attributeFilter: ["data-theme"]});
    const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
    const system = () => setTheme((v) => v + 1);
    media?.addEventListener("change", system);
    // Back, Forward or a pasted link: the hash's state applied (our own writes are known by their text)
    const changed = () => {
      if (location.hash === written.current) return;
      const next = parseState(new URLSearchParams(location.hash.replace(/^#/, "")), cube0);
      const current = stateRef.current;
      if (JSON.stringify(stateParams(next, cube0)) === JSON.stringify(stateParams(current, cube0))) return;
      setState(next);
      setPicked(null);
      if (next.view) map.setView([next.view.lat, next.view.lon], next.view.zoom, {animate: false});
      else fitCountry(next.country && cubes.some((c) => c.id === next.country) ? next.country : cube0.id);
    };
    window.addEventListener("hashchange", changed);
    return () => {
      map.off("moveend", moved);
      map.off("click", clicked);
      observer.disconnect();
      media?.removeEventListener("change", system);
      window.removeEventListener("hashchange", changed);
      cancelAnimationFrame(anim.current);
      layer.current?.remove();
      layer.current = null;
    };
  }, [place, cubes]);

  // The state in the hash, in place of the current entry (never a history entry)
  useEffect(() => {
    const hash = layerHash(stateParams(state, cube0));
    if (hash === written.current || hash === location.hash) return;
    written.current = hash;
    go(hash, true);
  }, [state]);

  // A round, DEBOUNCE_MS after the last move or change, the requests before aborted: the cells of the padded box
  // when the view left the one cached (or the level or the filters changed), the histograms of the view, at
  // low zoom the outlines with their totals instead
  const filters = filtersQuery(state);
  const key = JSON.stringify(filters);
  useEffect(() => {
    const map = place.map;
    const bounds = map.getBounds();
    const view = boxOf(bounds);
    const visible = cubesIn(cubes, view);
    setInView(visible);
    const low = metresPerPixel(map.getCenter().lat, map.getZoom()) > OUTLINE_MPP;
    setOutlineMode(low);
    const levels = visible.length ? [...new Set(visible.flatMap((c) => c.levels))] : cube0.levels;
    let chosen: number;
    if (state.level === "auto") {
      chosen = autoLevel(autoL.current, (l) => cellsAt(visible, view, l), levels);
      // coarser while the server would refuse the view (it counts the view within a degree of a cube's bounds)
      const sorted = [...levels].sort((a, b) => a - b);
      let k = sorted.indexOf(chosen);
      while (k < sorted.length - 1 && largestRequest(visible, view, sorted[k]) > REQUEST_CELLS_MAX) k++;
      chosen = sorted[k];
      autoL.current = chosen;
    } else {
      chosen = Number(state.level);
    }
    setLevel(chosen);
    const query = {...filters, level: String(chosen)};
    const cached = cache.current;
    const needCells = !low && visible.length > 0
      && !(cached && cached.level === chosen && cached.key === key && cached.box.contains(bounds));
    if (low) {
      setCells([]);
      setStatus("ready");
      setTotal(0);
    } else if (!needCells) {
      const have = cached?.cells || [];
      setCells(have);
      setOutlines([]);
      setStatus("ready");
      setTotal(totalIn(have, bounds));
    } else {
      setStatus("waiting");
    }
    setHistStatus("waiting");
    const controller = new AbortController();
    const signal = controller.signal;
    const timer = setTimeout(() => {
      if (needCells) {
        setStatus("loading");
        // the view and one view's width and height on every side, less where the server would refuse it
        const p = [1, 0.75, 0.5, 0.25].find((q) => largestRequest(cubes, padded(view, q), chosen) <= REQUEST_CELLS_MAX) ?? 0;
        const box = padded(view, p);
        const asked = cubesIn(cubes, box);
        const bbox = boundsOf(box).toBBoxString();
        Promise.all(asked.map((c) => source.cells(c.id, {...query, bbox}, signal).then((data) => ({country: c.id, data}))))
          .then((answers) => {
            if (signal.aborted) return;
            cache.current = {box: boundsOf(box), level: chosen, key, cells: answers};
            setCells(answers);
            setOutlines([]);
            setStatus("ready");
            setTotal(totalIn(answers, bounds));
            setFitBreaks(quantileBreaks(densities(answers), CLASS_BREAKS[stateRef.current.mode]));
            if (picking.current && answers.length) {
              const row = picking.current(answers[0].data);
              picking.current = undefined;
              if (row) {
                cellsRef.current = answers;
                choose(answers[0].country, row);
              }
            }
          }, (e: Error) => {
            if (signal.aborted) return;
            cache.current = null;
            setCells([]);
            if (e instanceof ApiError && e.status === 400 && /too many cells/i.test(e.message)) setStatus("too-many");
            else { setStatus("error"); setMessage(e.message); }
          });
      }
      if (!visible.length) {
        setHist(emptyHistogram());
        setHistStatus("ready");
        setOutlines([]);
        return;
      }
      const histQuery = low ? {...filters, level: "8"} : {...query, bbox: bounds.toBBoxString()};
      Promise.all(visible.map((c) => source.histogram(c.id, histQuery, signal)))
        .then((answers) => {
          if (signal.aborted) return;
          const sum = emptyHistogram();
          for (const a of answers) addHistogram(sum, a);
          setHist(sum);
          setHistStatus("ready");
          if (low) {
            setTotal(sum.total);
            shapes(visible, answers.map((a) => a.total));
          }
        }, (e: Error) => {
          if (signal.aborted) return;
          setHistStatus("error");
          setHistError(e.message);
          if (low) shapes(visible, visible.map(() => 0));
        });
      const shapes = (of: CountryCube[], totals: number[]) => {
        Promise.all(of.map((c, k) => {
          let promise = outlineCache.current.get(c.id);
          if (!promise) {
            promise = source.outline(c.id);
            outlineCache.current.set(c.id, promise);
            promise.catch(() => outlineCache.current.delete(c.id));
          }
          return promise.then((o): OutlineShape => ({country: c.id, name: c.name, total: totals[k], area_km2: o.area_km2, geometry: o.geometry}));
        })).then((list) => { if (!signal.aborted) setOutlines(list); },
                 (e: Error) => { if (!signal.aborted) { setStatus("error"); setMessage(e.message); } });
      };
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, state.level, moves, cubes, source]);

  // The picked cell follows the answers: its count again, or gone at another level
  useEffect(() => {
    if (!picked) return;
    const answer = cells.find((c) => c.country === picked.country)?.data;
    if (!answer || answer.level !== picked.level) { setPicked(null); return; }
    const row = answer.cells.find((r) => r[0] === picked.i && r[1] === picked.j);
    const count = row ? row[2] : 0;
    if (count !== picked.count) setPicked({...picked, count});
  }, [cells]);

  // The breaks in force: fixed, or fitted to the padded box; a change eased over EASE_MS (none with reduced motion),
  // the cells and the legend redrawn each frame; a timer ends it where frames do not come (a hidden tab)
  const target = state.scale === "fixed" ? CLASS_BREAKS[mode] : fitBreaks || CLASS_BREAKS[mode];
  useEffect(() => {
    const apply = (b: number[]) => {
      shown.current = b;
      setLegend(b);
      layer.current?.recolour(b);
    };
    cancelAnimationFrame(anim.current);
    const from = shown.current;
    const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!from || reduced || from.every((v, k) => v === target[k])) {
      apply(target);
      return;
    }
    const t0 = performance.now();
    const step = (now: number) => {
      const t1 = Math.max(0, Math.min(1, (now - t0) / EASE_MS));
      apply(t1 < 1 ? easedBreaks(from, target, t1) : target);
      if (t1 < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
    const finish = setTimeout(() => { cancelAnimationFrame(anim.current); apply(target); }, EASE_MS + 100);
    return () => { cancelAnimationFrame(anim.current); clearTimeout(finish); };
  }, [target.join()]);

  useEffect(() => {
    layer.current?.draw(cells, outlines, shown.current || target, CLASS_BREAKS[mode]);
  }, [cells, outlines, mode, theme]);
  useEffect(() => { layer.current?.pick(picked); }, [picked, theme]);

  const current = cubes.find((c) => c.id === state.country) || inView[0] || cube0;
  const edges = cube0.edges;
  const noun = mode === "lines" ? t("ui.layer.lines") : t("ui.layer.spots");
  const Noun = mode === "lines" ? t("ui.layer.Lines") : t("ui.layer.Spots");
  const several = filtersSet(state, cube0) > 1;
  const labels = classLabels(legend);
  const pickedCube = picked ? cubes.find((c) => c.id === picked.country) : null;
  const pickedBands = pickedCube ? pickedCube.bands.filter((b) => b.layer) : [];
  const centre = picked && [0, 2, 4, 6].reduce((s, k) => [s[0] + picked.corners[k] / 4, s[1] + picked.corners[k + 1] / 4], [0, 0]);
  const levelValues = [...new Set((inView.length ? inView : [cube0]).flatMap((c) => c.levels))].sort((a, b) => a - b);
  const levels: {value: LayerLevel; label: string}[] = [{value: "auto", label: t("ui.layer.auto")},
    ...levelValues.map((l) => ({value: String(l) as LayerLevel, label: `${l * cube0.cell_m / 1000} km`}))];
  const range = (lo: number, hi: number) => `${short(lo)}–${short(hi)} m`;
  const shownCubes = inView.length ? inView : [current];  // the cubes in view (the selected one when none is)
  const credits = shownCubes.flatMap((c) => c.credits);
  const builtOf = (c: CountryCube) => {
    const bands = c.bands.filter((b) => b.layer);
    const done = bands.reduce((s, b) => s + b.done, 0), tiles = bands.reduce((s, b) => s + b.tiles, 0);
    return t("ui.layer.built", {day: day(c.built, "?")}) + (c.partial ? ` · ${t("ui.layer.partial", {done, tiles})}` : "");
  };
  const copyLink = () => copy(location.href).then((ok) => setCopied(ok ? "ok" : "fail"));
  const onLength = (lo: number, hi: number, extend: boolean) => {
    setPicked(null);
    set({length: extend ? [Math.min(lo, state.length[0]), Math.max(hi, state.length[1])] : [lo, hi]});
  };
  const onThreshold = (dimension: Dimension, value: number | null) => {
    setPicked(null);
    set(dimension === "wall" ? {wall: value} : {[dimension]: value || 0});
  };

  const right = <LayerHistograms cube={cube0} state={state} hist={hist} status={histStatus} error={histError}
                                 countries={inView.length} onLength={onLength} onThreshold={onThreshold} />;
  // The right panel: its own tree rendered into MapPage's third column after each render (no portal: preact/compat
  // would turn every onChange of the app's inputs into onInput), emptied when the page goes
  useEffect(() => { if (aside) render(right, aside); });
  useEffect(() => () => { if (aside) render(null, aside); }, [aside]);

  return <div class="c-layer">
    <div class="c-layer-head">
      {cubes.length > 1
        ? <Field label={t("ui.layer.country")} htmlFor="layer-country">
            <NumberSelect id="layer-country" value={current.id} options={cubes.map((c) => [c.id, c.name])}
                          onChange={(id) => { set({country: id}); fitCountry(id); }} />
          </Field>
        : <b class="c-layer-name">{current.name}</b>}
      <span class="u-small">{builtOf(current)}</span>
    </div>

    <Segmented label={t("ui.layer.count")} value={mode} onChange={(m) => { set({mode: m}); setPicked(null); }}
               options={[{value: "lines", label: t("ui.layer.Lines")}, {value: "spots", label: t("ui.layer.Spots")}]} />

    <div class="c-layer-filters">
      <Field label={t("ui.layer.length")} htmlFor="layer-length-lo">
        <div class="c-layer-pair">
          <NumberSelect id="layer-length-lo" label={t("ui.layer.shortest")} value={String(state.length[0])}
                        options={edges.length.slice(0, -1).map((v) => [String(v), t("ui.layer.from_m", {value: v})])}
                        onChange={(v) => set({length: [+v, Math.max(state.length[1], edges.length[edges.length.indexOf(+v) + 1])]})} />
          <NumberSelect id="layer-length-hi" label={t("ui.layer.longest")} value={String(state.length[1])}
                        options={edges.length.slice(1).map((v) => [String(v), t("ui.layer.to_m", {value: v})])}
                        onChange={(v) => set({length: [Math.min(state.length[0], edges.length[edges.length.indexOf(+v) - 1]), +v]})} />
        </div>
      </Field>
      <Field label={t("ui.layer.prominence")} htmlFor="layer-prominence">
        <NumberSelect id="layer-prominence" value={String(state.prominence)} onChange={(v) => set({prominence: +v})}
                      options={edges.prominence.map((v) => [String(v), v ? `≥ ${v} m` : t("ui.layer.any")])} />
      </Field>
      <Field label={t("ui.layer.wall")} htmlFor="layer-wall">
        <NumberSelect id="layer-wall" value={state.wall === null ? "" : String(state.wall)}
                      onChange={(v) => set({wall: v === "" ? null : +v})}
                      options={[["", t("ui.layer.any")], ...edges.wall.filter((v) => v > 0).map((v) => [String(v), `< ${v}°`] as [string, string])]} />
      </Field>
      <Field label={t("ui.layer.clearance")} htmlFor="layer-clearance">
        <NumberSelect id="layer-clearance" value={String(state.clearance)} onChange={(v) => set({clearance: +v})}
                      options={edges.clearance.map((v) => [String(v), v ? `≥ ${v} m` : t("ui.layer.any")])} />
      </Field>
      <Field label={t("ui.layer.height")} htmlFor="layer-height">
        <NumberSelect id="layer-height" value={String(state.height)} onChange={(v) => set({height: +v})}
                      options={edges.height.map((v) => [String(v), v ? `≥ ${v} m` : t("ui.layer.any")])} />
      </Field>
      <Field label={t("ui.layer.trees")} htmlFor="layer-trees">
        <select id="layer-trees" class="u-input" value={state.trees} disabled={!shownCubes.some((c) => c.dsm)}
                onChange={(e) => set({trees: (e.target as HTMLSelectElement).value as LayerState["trees"]})}>
          <option value="all">{t("ui.layer.any")}</option><option value="no">{t("ui.layer.trees_no")}</option>
          <option value="only">{t("ui.layer.trees_only")}</option>
        </select>
      </Field>
      <Field label={t("ui.layer.water")} htmlFor="layer-water">
        <select id="layer-water" class="u-input" value={state.water}
                onChange={(e) => set({water: (e.target as HTMLSelectElement).value as LayerState["water"]})}>
          <option value="all">{t("ui.layer.any")}</option><option value="land">{t("ui.layer.water_land")}</option>
          <option value="water">{t("ui.layer.water_only")}</option>
        </select>
      </Field>
      {!shownCubes.some((c) => c.dsm) && <p class="u-small c-layer-note">{t("ui.layer.no_dsm")}</p>}
    </div>

    <section class="c-layer-legend" aria-label={t("ui.layer.per_km2_of", {noun: Noun})}>
      <h2 class="u-h4">{t("ui.layer.per_km2_of", {noun: Noun})}</h2>
      <ul class="c-layer-classes">
        {labels.map((text, k) => <li key={k}><span class={`c-layer-swatch c-layer-k${k + 1}`} aria-hidden="true" />{text}</li>)}
      </ul>
      <Field label={t("ui.layer.scale")}>
        <Segmented label={t("ui.layer.scale")} value={state.scale} onChange={(scale) => set({scale})}
                   options={[{value: "fit", label: t("ui.layer.scale_fit")}, {value: "fixed", label: t("ui.layer.scale_fixed")}]} />
      </Field>
      <p class="u-small">{state.scale === "fit" ? t("ui.layer.scale_fit_note") : t("ui.layer.scale_fixed_note")}</p>
    </section>

    <section class="c-layer-view" aria-live="polite">
      <div class="c-layer-total">
        {status === "ready" && outlineMode ? <span><b>{inView.length}</b> {t("ui.layer.countries_in_view", {count: inView.length})}
            {histStatus === "ready" && hist && <> · <b>{hist.total.toLocaleString("en")}</b> {noun}</>}</span>
          : status === "ready" ? <span><b>{total.toLocaleString("en")}</b> {mode === "lines" ? t("ui.layer.lines_in_view") : t("ui.layer.spots_in_view")} ·{" "}
            {t("ui.layer.cells_of", {km: level * cube0.cell_m / 1000, level})}</span>
          : status === "too-many" ? <span class="c-error">{t("ui.layer.too_many")}</span>
          : status === "error" ? <span class="c-error" role="alert">{message}</span>
          : <span class="u-small">{t("ui.layer.counting")}</span>}
      </div>
      <Field label={t("ui.layer.cells")}>
        <Segmented label={t("ui.layer.cells")} value={state.level} onChange={(l) => set({level: l})} options={levels} />
      </Field>
      <div class="c-layer-link">
        <Button icon="link" onClick={copyLink}>{t("ui.layer.copy_link")}</Button>
        {copied === "ok" && <span class="u-small">{t("ui.layer.copied")}</span>}
      </div>
      {copied === "fail" && <LinkField text={location.href} />}
    </section>

    {picked && pickedCube ? <section class="c-layer-cell" aria-label={t("ui.layer.selected")}>
      <h2 class="u-h4">{t("ui.layer.selected")}</h2>
      <div class="u-small">{pickedCube.name}</div>
      <div><b>{picked.count.toLocaleString("en")}</b> {noun} · {short(picked.count / (picked.cell_m / 1000) ** 2)} {t("ui.layer.per_km2")} ·{" "}
        {t("ui.layer.cell_km", {km: picked.cell_m / 1000})}</div>
      {centre && <div class="u-small u-mono">{centre[0].toFixed(4)}, {centre[1].toFixed(4)}</div>}
      <div class="c-layer-search">
        {pickedBands.map((b) => <Button key={b.name} icon="search" href={cellHash(pickedCube.id, b.name, picked.level, picked.i, picked.j)}>
          {t("ui.layer.search_here")}: {b.name} · {range(b.lengths[0], b.lengths[1])}</Button>)}
      </div>
      <p class="u-small">{t("ui.layer.search_note")}</p>
    </section> : <p class="u-small">{t("ui.layer.click_hint")}</p>}

    <section class="c-layer-notes">
      <h2 class="u-h4">{t("ui.layer.about")}</h2>
      <ul class="u-small">
        <li>{t("ui.layer.note_spot")}</li>
        <li class={mode === "spots" && several ? "c-layer-warn" : undefined}>{t("ui.layer.note_upper")}</li>
        <li>{t("ui.layer.note_inside")}</li>
        {(inView.length ? inView : [current]).map((c) => <li key={c.id}>{t("ui.layer.note_bands", {name: c.name})}{" "}
          {c.bands.filter((b) => b.layer).map((b) => `${b.name} ${b.resolution} m (${range(b.lengths[0], b.lengths[1])})`).join(", ")}.</li>)}
        {shownCubes.filter((c) => !c.dsm).map((c) => <li key={`dsm-${c.id}`}>{t("ui.layer.note_no_dsm", {name: c.name})}</li>)}
        {(inView.length ? inView : [current]).flatMap((c) => c.notes).map((n, k) => <li key={k}>{n}</li>)}
      </ul>
    </section>

    {credits.length > 0 &&
      <p class="u-small c-layer-credits" dangerouslySetInnerHTML={{__html: creditsHtml(credits, user.local ? "" : "/about")}} />}
  </div>;
}

export function LayerPage({params}: {params: URLSearchParams}) {
  if (!user.local && !user.admin) return <div class="c-page"><p>{t("ui.layer.admins_only")}</p></div>;
  return <MapPage title={t("ui.layer.title")} aside={t("ui.layer.histograms")}>{(place, aside) =>
    <LayerPanel place={place} aside={aside} source={SERVER} params={params} />}</MapPage>;
}
