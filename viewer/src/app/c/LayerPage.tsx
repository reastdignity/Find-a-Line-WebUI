// The highline layer (#layer; the local app and administrators): the countries searched offline in fixed tiles
// (country.py) keep only counts, in counter cubes on one global lattice of 30″ cells and its levels 1′, 2′, 4′
// (countcube.py, cube v2). The page browses every country's cube at once (a study area, a box of a country, and a
// country of another layer profile only alone: layerState.ts activeCubes): the rows of the cubes in view
// (/api/countries/<id>/cells) on the map, coloured by their density per km² over their part of their cell
// (cellsLayer.ts: a country's own lines over its part inside the outline, its partner lines across the border
// hatched over the part beyond it; the fixed classes, or classes fitted to the view), the histograms of the
// counts in view per bin of each of the cube's sixteen dimensions (/histogram, LayerHistograms.tsx) on the right,
// the filters (today's seven open, the others in a fold), the border switch, the legend, the level and the
// selected cell with one "Search here" per layer band (#new&cell=…, NewSearch) on the left; at low zoom the
// countries' outlines (/outline) instead of cells. Both side panels collapse and resize (MapPage of Account.tsx,
// ui/SidePanel.tsx); on phones one scrolling column. Every filter and the view are in the hash (layerState.ts),
// written in place on every change, read back on Back or a pasted link.
// The source of the cubes, cells, histograms and outlines is a prop: the server (SERVER), or canned data
// (?ui=kit-layer, Gallery).

import { render } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import L from "leaflet";
import { Button, DESKTOP, Field, Segmented, useMedia } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { ApiError, api, user, type CountryCells, type CountryCube, type CountryHistogram, type CountryOutline } from "../api";
import type { PlaceMap } from "../PlaceMap";
import { creditsHtml } from "../../layers";
import { t } from "../../i18n";
import { day } from "../../time";
import { copy, LinkField } from "../../result/view/LineDetails";
import { MapPage, type MapPageExtras } from "./Account";
import { cellHash, go, layerHash } from "./route";
import { CLASS_BREAKS, CellsLayer, cellKm2, cellShape, rowBounds, rowSide, short, wholeKm2, type DrawnCells, type LayerMode,
         type OutlineShape, type PickedCell } from "./cellsLayer";
import { LayerHistograms, addHistogram, dimensionContext, dimensionLabel, dimensionShort, emptyHistogram, limitText,
         unitOf, type DimensionContext, type SummedHistogram } from "./LayerHistograms";
import { OUTLINE_MPP, REQUEST_CELLS_MAX, SEVEN, activeCubes, autoLevel, cellDeg, cellsAt, countriesFirst, cubesIn,
         easedBreaks, filtersQuery, filtersSet, largestRequest, levelName, limitEdges, limitOn, metresPerDegree, metresPerPixel,
         offLimit, parseState, quantileBreaks, replacedPartners, sizeText, stateParams, summedWith, topicsOf,
         type Box, type LayerBorder, type LayerLevel, type LayerState } from "./layerState";
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
function NumberSelect({id, value, options, label, disabled, onChange}:
                      {id: string; value: string; options: [string, string][]; label?: string; disabled?: boolean;
                       onChange(v: string): void}) {
  return <select id={id} class="u-input" value={value} aria-label={label} disabled={disabled}
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

/** The count of the rows reaching the view. */
function totalIn(cells: DrawnCells[], view: L.LatLngBounds): number {
  let total = 0;
  for (const {data} of cells) for (const row of data.cells) if (view.intersects(rowBounds(row))) total += row[2];
  return total;
}

/** The densities per km² of every row but the partner rows (they hold only the lines across the border: left out of
 *  the fitted scale). */
function densities(cells: DrawnCells[]): number[] {
  const out: number[] = [];
  for (const {data} of cells) for (const row of data.cells) if (!rowSide(row)) out.push(row[2] / cellKm2(data, row));
  return out;
}

/** A neighbour's name (cube.json's neighbours are cube ids): the listed cube's, else the id in words. */
function neighbourName(id: string, cubes: CountryCube[]): string {
  const found = cubes.find((c) => c.id === id);
  if (found) return found.name;
  const words = id.replace(/[-_]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : id;
}

/** The name of a row's partner (side 1-6 of its cube's neighbours), null for none or unknown (7). */
function partnerName(cube: CountryCube, side: number, cubes: CountryCube[]): string | null {
  const id = side >= 1 && side <= 6 ? cube.neighbours?.[side - 1] : undefined;
  return id ? neighbourName(id, cubes) : null;
}

/** Whether a cube was counted with the no-fall zone or the A-frames (its layer bands' params): only then are the
 *  A-frame dimensions known. */
const liftCounted = (cube: CountryCube) =>
  cube.bands.some((b) => b.layer && (Number(b.params?.end_zone) > 0 || Number(b.params?.anchor_lift) > 0));

interface Cache { box: L.LatLngBounds; level: number; key: string; cells: DrawnCells[] }
/** The picked row's cell as a cell of level 1 (its base), so the card follows it to another level. */
interface Base { country: string; i: number; j: number; side: number }
/** One /histogram of the picked cell alone: both modes' totals and the lines' border split. */
interface CellSummary { key: string; totals: {lines: number; spots: number} | null; border: {interior: number; owned: number; partner: number} | null }

/** The panel of the highline layer, on `place`'s map; `aside`: the element of the right panel (the histograms);
 *  `extras`: MapPage's (the panels' widths, the rails' labels). `params`: the hash's parameters the page opened with;
 *  `pick`: the demo's way to select a row of the first answer. */
export function LayerPanel({place, aside, source, params, pick, extras}:
                           {place: PlaceMap; aside: HTMLElement | null; source: LayerSource; params: URLSearchParams;
                            pick?: (data: CountryCells) => number[] | null; extras?: MapPageExtras}) {
  const [cubes, setCubes] = useState<CountryCube[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    source.countries().then((r) => setCubes(countriesFirst(r.countries)), (e) => setError(e.message));
  }, [source]);
  if (error) return <p class="c-error" role="alert">{error}</p>;
  if (!cubes) return <p class="u-small">{t("ui.layer.loading")}</p>;
  if (!cubes.length) {
    return <p class="u-small">{t("ui.layer.none")}
      <span class="u-mono"> findaline.py country run &lt;id&gt;</span>, {t("ui.layer.then")}
      <span class="u-mono"> country build &lt;id&gt;</span>.</p>;
  }
  return <Explorer place={place} aside={aside} source={source} cubes={cubes} params={params} pick={pick} extras={extras} />;
}

function Explorer({place, aside, source, cubes, params, pick, extras}:
                  {place: PlaceMap; aside: HTMLElement | null; source: LayerSource; cubes: CountryCube[];
                   params: URLSearchParams; pick?: (data: CountryCells) => number[] | null; extras?: MapPageExtras}) {
  const cube0 = cubes[0];
  const wide = useMedia(DESKTOP);
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
  const [summary, setSummary] = useState<CellSummary | null>(null);
  const [level, setLevel] = useState(cube0.levels[0]);
  const [inView, setInView] = useState<CountryCube[]>([cube0]);
  const [outlineMode, setOutlineMode] = useState(false);
  const [total, setTotal] = useState(0);
  const [fitBreaks, setFitBreaks] = useState<number[] | null>(null);
  const [legend, setLegend] = useState<number[]>(CLASS_BREAKS[state.mode]);
  const [copied, setCopied] = useState<"" | "ok" | "fail">("");
  const [open, setOpen] = useState<string | null>(null);  // the dimension changed last: its chart ringed (enlarged on phones)
  const [more, setMore] = useState(false);                // the fold of the other filters open
  const layer = useRef<CellsLayer | null>(null);
  const picking = useRef(pick);
  const written = useRef("");                   // the hash this page wrote last
  const stateRef = useRef(state);
  stateRef.current = state;
  const autoL = useRef<number | null>(null);    // the automatic level in force (hysteresis)
  const cache = useRef<Cache | null>(null);     // the cells of the padded box they were asked for
  const cellsRef = useRef<DrawnCells[]>([]);
  cellsRef.current = cells;
  const base = useRef<Base | null>(null);       // the picked row's base cell
  const shown = useRef<number[] | null>(null);  // the breaks the cells are coloured by now (eased)
  const anim = useRef(0);
  const outlineCache = useRef(new Map<string, Promise<CountryOutline>>());
  const set = (change: Partial<LayerState>) => setState((s) => ({...s, ...change}));
  const mode: LayerMode = state.mode;

  /** A row of an answer as the picked cell. */
  const pickedOf = (country: string, data: CountryCells, row: number[]): PickedCell =>
    ({country, level: data.level, deg: data.cell_deg, i: row[0], j: row[1], side: rowSide(row), count: row[2],
      corners: row.slice(3, 11), km2: cellKm2(data, row), whole: wholeKm2(row), shape: cellShape(data, row)});
  const choose = (country: string, row: number[]) => {
    const answer = cellsRef.current.find((c) => c.country === country)?.data;
    if (!answer) return;
    base.current = {country, i: row[0] * answer.level, j: row[1] * answer.level, side: rowSide(row)};
    setPicked(pickedOf(country, answer, row));
  };
  const unpick = () => { base.current = null; setPicked(null); };
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
    layer.current = new CellsLayer(map, choose, fitCountry, (count, density, side) =>
      `${count.toLocaleString("en")} ${noun()} · ${short(density)} ${t("ui.layer.per_km2")}${side ? ` · ${t("ui.layer.beyond_short")}` : ""}`);
    const moved = () => {
      const c = map.getCenter();
      set({view: {lat: c.lat, lon: c.lng, zoom: map.getZoom()}});
      setMoves((v) => v + 1);
    };
    map.on("moveend", moved);
    map.on("click", unpick);
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
      unpick();
      if (next.view) map.setView([next.view.lat, next.view.lon], next.view.zoom, {animate: false});
      else fitCountry(next.country && cubes.some((c) => c.id === next.country) ? next.country : cube0.id);
    };
    window.addEventListener("hashchange", changed);
    return () => {
      map.off("moveend", moved);
      map.off("click", unpick);
      observer.disconnect();
      media?.removeEventListener("change", system);
      window.removeEventListener("hashchange", changed);
      cancelAnimationFrame(anim.current);
      layer.current?.remove();
      layer.current = null;
    };
  }, [place, cubes]);

  // A side panel resized or collapsed (MapPage): the automatic level starts again as at a first view
  useLayoutEffect(() => { autoL.current = null; }, [extras?.panels]);

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
  const filters = filtersQuery(state, cube0);
  const active = activeCubes(cubes, state.country);
  const key = JSON.stringify({...filters, cubes: active.map((c) => c.id)});
  useEffect(() => {
    const map = place.map;
    const bounds = map.getBounds();
    const view = boxOf(bounds);
    const visible = cubesIn(active, view);
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
        const p = [1, 0.75, 0.5, 0.25].find((q) => largestRequest(active, padded(view, q), chosen) <= REQUEST_CELLS_MAX) ?? 0;
        const box = padded(view, p);
        const asked = cubesIn(active, box);
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
        setHist(emptyHistogram(cube0));
        setHistStatus("ready");
        setOutlines([]);
        return;
      }
      const histQuery = low ? {...filters, level: String(Math.max(...levels))} : {...query, bbox: bounds.toBBoxString()};
      Promise.all(visible.map((c) => source.histogram(c.id, histQuery, signal)))
        .then((answers) => {
          if (signal.aborted) return;
          const sum = emptyHistogram(cube0);
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

  // The picked row follows the answers: the row of its base cell and side at the level in force (its count again),
  // or gone when the answers of its cube hold none at another level
  useEffect(() => {
    const at = base.current;
    if (!at) return;
    const answer = cells.find((c) => c.country === at.country)?.data;
    if (!answer) return;
    const L0 = answer.level;
    const row = answer.cells.find((r) => r[0] === Math.floor(at.i / L0) && r[1] === Math.floor(at.j / L0) && rowSide(r) === at.side);
    if (row) {
      const next = pickedOf(at.country, answer, row);
      if (!picked || next.count !== picked.count || next.level !== picked.level || next.i !== picked.i || next.j !== picked.j) setPicked(next);
    } else if (picked && picked.level === L0) {
      if (picked.count !== 0) setPicked({...picked, count: 0});
    } else {
      unpick();
    }
  }, [cells]);

  // The picked cell's own counts (both modes, the lines across the border): one /histogram of a box inside it
  const pickedKey = picked ? JSON.stringify([picked.country, picked.level, picked.i, picked.j, filters]) : "";
  useEffect(() => {
    if (!picked) { setSummary(null); return; }
    const c = picked.corners, inset = (c[6] - c[0]) * 0.02;
    const inner = [c[1] + inset, c[0] + inset, c[2 + 1] - inset, c[4] - inset].map((v) => v.toFixed(7)).join(",");
    const controller = new AbortController();
    source.histogram(picked.country, {...filters, level: String(picked.level), bbox: inner}, controller.signal)
      .then((h) => { if (!controller.signal.aborted) setSummary({key: pickedKey, totals: h.totals || null, border: h.border || null}); },
            () => { if (!controller.signal.aborted) setSummary(null); });
    return () => controller.abort();
  }, [pickedKey]);

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
  const shownCubes = inView.length ? inView : [current];  // the cubes in view (the selected one when none is)
  const ctx: DimensionContext = dimensionContext(shownCubes);
  const edges = cube0.edges;
  const noun = mode === "lines" ? t("ui.layer.lines") : t("ui.layer.spots");
  const Noun = mode === "lines" ? t("ui.layer.Lines") : t("ui.layer.Spots");
  const setCount = filtersSet(state, cube0);
  const several = setCount > 1;
  const dsm = shownCubes.some((c) => c.dsm);
  const lifts = shownCubes.some(liftCounted);
  const centreLat = place.map.getCenter().lat;
  // the outlines are coloured by the fixed classes (a country's total over its area), whatever the scale
  const labels = classLabels(outlineMode ? CLASS_BREAKS[mode] : legend);
  const pickedCube = picked ? cubes.find((c) => c.id === picked.country) : null;
  const pickedBands = pickedCube ? pickedCube.bands.filter((b) => b.layer) : [];
  const centre = picked && [0, 2, 4, 6].reduce((s, k) => [s[0] + picked.corners[k] / 4, s[1] + picked.corners[k + 1] / 4], [0, 0]);
  const levelValues = [...new Set(shownCubes.flatMap((c) => c.levels))].sort((a, b) => a - b);
  const levels: {value: LayerLevel; label: string}[] = [{value: "auto", label: t("ui.layer.auto")},
    ...levelValues.map((l) => ({value: String(l) as LayerLevel, label: levelName(cellDeg(cube0, l))}))];
  const range = (lo: number, hi: number) => `${short(lo)}–${short(hi)} m`;
  const credits = shownCubes.flatMap((c) => c.credits);
  const builtOf = (c: CountryCube) => {
    const bands = c.bands.filter((b) => b.layer);
    const done = bands.reduce((s, b) => s + b.done, 0), tiles = bands.reduce((s, b) => s + b.tiles, 0);
    return t("ui.layer.built", {day: day(c.built, "?")}) + (c.partial ? ` · ${t("ui.layer.partial", {done, tiles})}` : "");
  };
  const copyLink = () => copy(location.href).then((ok) => setCopied(ok ? "ok" : "fail"));
  const openKey = (d: string) => d.startsWith("elevation_") ? "elevation" : d;
  const onLength = (lo: number, hi: number, extend: boolean) => {
    unpick();
    setOpen("length");
    set({length: extend ? [Math.min(lo, state.length[0]), Math.max(hi, state.length[1])] : [lo, hi]});
  };
  const onLimit = (dimension: string, value: number | null) => {
    unpick();
    setOpen(openKey(dimension));
    set({limits: {...state.limits, [dimension]: value ?? offLimit(cube0, dimension)}});
  };
  const limit = (d: string) => state.limits[d] ?? null;

  // The cubes' borders: whose partner lines are drawn (border=all, no neighbour layer in their place), which
  // neighbours' own layers are shown
  const border: LayerBorder = state.border;
  const partnerRows = cells.some(({data}) => data.cells.some((r) => rowSide(r) > 0));
  const hatchFrom = cells.find(({data}) => data.cells.some((r) => rowSide(r) > 0))?.country;
  const hatchName = cubes.find((c) => c.id === hatchFrom)?.name || current.name;
  const replacedAny = shownCubes.some((c) => replacedPartners(c, cubes).size > 0);
  const borderHint = border === "own" ? t("ui.layer.border.hint_own", {name: current.name})
    : replacedAny ? t("ui.layer.border.hint_layers") : t("ui.layer.border.hint_all", {name: current.name});

  // The rails' labels (MapPage): the filters set, the count in view
  const rails: [string, string] = [t("ui.layer.rail_filters", {count: setCount}),
                                   t("ui.layer.rail_counts", {total: short(outlineMode ? hist?.total ?? 0 : total), noun})];
  useEffect(() => { extras?.setRails(rails[0], rails[1]); }, [rails[0], rails[1]]);

  // The totals line: the mode's count (the rows in view), the other mode's and the lines across the border (the
  // histograms of the view)
  const otherTotal = hist?.totals ? (mode === "lines" ? hist.totals.spots : hist.totals.lines) : null;
  const split = histStatus === "ready" && hist?.border ? hist.border : null;

  const right = <LayerHistograms cube={cube0} state={state} hist={hist} status={histStatus} error={histError}
                                 countries={inView.length} ctx={ctx} open={open} wide={wide} border={border === "all"}
                                 onLength={onLength} onLimit={onLimit} onOpen={setOpen} />;
  // The right panel: its own tree rendered into MapPage's right panel after each render (no portal: preact/compat
  // would turn every onChange of the app's inputs into onInput), emptied when the page goes
  useEffect(() => { if (aside) render(right, aside); });
  useEffect(() => () => { if (aside) render(null, aside); }, [aside]);

  /** A dimension's control: its select by its kind (the first edge of a floor "Any"), disabled where the cubes in view
   *  do not know its values. */
  const control = (d: string, label?: string, any?: string) => {
    const kind = cube0.kinds[d], e = edges[d], value = limit(d), u = unitOf(d);
    const withUnit = (v: number) => u === "m" ? `${v} m` : `${v}${u}`;
    const options: [string, string][] = kind === "floor" ? e.map((v, k) => [String(v), k === 0 ? any || t("ui.layer.any") : `≥ ${withUnit(v)}`])
      : kind === "below" ? [["", any || t("ui.layer.any")], ...limitEdges(cube0, d).map((v) => [String(v), `< ${withUnit(v)}`] as [string, string])]
      : [["", any || t("ui.layer.any")], ...e.map((v) => [String(v), v === 0 ? t("ui.layer.none_needed") : `≤ ${withUnit(v)}`] as [string, string])];
    const shownValue = kind === "floor" ? String(value ?? e[0]) : value === null || !limitOn(cube0, d, value) ? "" : String(value);
    const disabled = (d === "clearance_trees" && !dsm) || ((d === "lift_needed" || d === "lift_no_zone") && !lifts);
    return <NumberSelect id={`layer-${d}`} label={label} value={shownValue} options={options} disabled={disabled}
                         onChange={(v) => onLimit(d, v === "" ? null : +v)} />;
  };
  const WIDE = new Set(["lift_needed", "lift_no_zone", "clearance_trees", "high_pct", "height_diff", "elevation"]);
  /** A filter of the fold: a dimension's field, or the elevation pair (both anchors' heights) as one. */
  const foldField = (d: string) => d === "elevation"
    ? <Field key={d} label={t("ui.layer.dim.elevation.label")} htmlFor="layer-elevation_low">
        <div class="c-layer-pair">{control("elevation_low", dimensionLabel("elevation_low", ctx), t("ui.layer.elevation_low_any"))}
          {control("elevation_high", dimensionLabel("elevation_high", ctx), t("ui.layer.elevation_high_any"))}</div>
      </Field>
    : <Field key={d} label={WIDE.has(d) ? dimensionLabel(d, ctx) : dimensionShort(d, ctx)} htmlFor={`layer-${d}`}>{control(d)}</Field>;
  // The fold's filters by topic (the charts' order): every dimension but the open seven, the elevation pair as one
  const fold = topicsOf(cube0).map((topic) => {
    const dims: string[] = [];
    for (const d of topic.charts) {
      if (SEVEN.includes(d)) continue;
      const k = openKey(d);
      if (!dims.includes(k)) dims.push(k);
    }
    return {id: topic.id, dims};
  }).filter((topic) => topic.dims.length);
  const foldOn = (d: string) => d === "elevation" ? limitOn(cube0, "elevation_low", limit("elevation_low")) || limitOn(cube0, "elevation_high", limit("elevation_high"))
    : limitOn(cube0, d, limit(d));
  const foldText = (d: string) => {
    if (d !== "elevation") return limitText(cube0.kinds[d], d, limit(d), true);
    const lo = foldOn("elevation") && limitOn(cube0, "elevation_low", limit("elevation_low")) ? limit("elevation_low") : null;
    const hi = limitOn(cube0, "elevation_high", limit("elevation_high")) ? limit("elevation_high") : null;
    return lo !== null && hi !== null ? `${lo}–${hi} m` : lo !== null ? `≥ ${lo} m` : `< ${hi} m`;
  };
  const foldSet = fold.flatMap((topic) => topic.dims).filter(foldOn);
  const foldCount = fold.reduce((s, topic) => s + topic.dims.length, 0);
  const neighbourNotes = border === "all" ? shownCubes.flatMap((c) => {
    const replaced = replacedPartners(c, cubes);
    return (c.neighbours || []).slice(0, 6).map((id, k) => {
      const name = neighbourName(id, cubes);
      return replaced.has(k + 1) ? t("ui.layer.border.note_layer", {name})
        : t("ui.layer.border.note_data", {name, country: c.name});
    });
  }) : [];
  const clusterM = (() => {
    const [east, north] = metresPerDegree(centreLat), deg = cube0.cell_deg / (cube0.clusters_per_cell || 20);
    return `${Math.round(east * deg)} × ${Math.round(north * deg)} m`;
  })();
  // a picked cell the border cuts: its neighbour named from another row of the cell, a partner row
  const cutNeighbour = (() => {
    if (!picked || !pickedCube || picked.side || picked.km2 >= picked.whole * 0.999) return null;
    const answer = cells.find((c) => c.country === picked.country)?.data;
    const other = answer?.cells.find((r) => r[0] === picked.i && r[1] === picked.j && rowSide(r) > 0);
    return other ? partnerName(pickedCube, rowSide(other), cubes) : null;
  })();
  const cardHint = (() => {
    if (!picked || !pickedCube) return null;
    if (picked.side) {
      const name = partnerName(pickedCube, picked.side, cubes);
      return name ? t("ui.layer.search_partner", {country: pickedCube.name, name}) : t("ui.layer.search_partner_any", {country: pickedCube.name});
    }
    if (picked.km2 >= picked.whole * 0.999) return null;
    return cutNeighbour ? t("ui.layer.search_border", {name: cutNeighbour}) : t("ui.layer.search_border_any");
  })();
  const otherInCell = summary && summary.key === pickedKey && summary.totals && picked
    && (cells.find((c) => c.country === picked.country)?.data.cells.filter((r) => r[0] === picked.i && r[1] === picked.j).length ?? 0) === 1
    ? (mode === "lines" ? summary.totals.spots : summary.totals.lines) : null;
  const acrossInCell = summary && summary.key === pickedKey && summary.border && picked && border === "all"
    ? (picked.side ? null : summary.border.owned) : null;

  return <div class="c-layer">
    <div class="c-layer-head">
      {cubes.length > 1
        ? <Field label={t("ui.layer.country")} htmlFor="layer-country">
            <NumberSelect id="layer-country" value={current.id}
                          options={cubes.map((c) => [c.id, c.study ? t("ui.layer.study_name", {name: c.name})
                            : !summedWith(cubes.find((x) => !x.study), c) ? t("ui.layer.profile_name", {name: c.name}) : c.name])}
                          onChange={(id) => { set({country: id}); fitCountry(id); }} />
          </Field>
        : <b class="c-layer-name">{current.name}</b>}
      <span class="u-small">{builtOf(current)}</span>
      {current.study && <p class="u-small c-layer-note">{t("ui.layer.study_note")}</p>}
      {!current.study && !summedWith(cubes.find((x) => !x.study), current) &&
        <p class="u-small c-layer-note">{t("ui.layer.profile_note", {name: cubes.find((x) => !x.study)?.name || ""})}</p>}
    </div>

    <Segmented label={t("ui.layer.count")} value={mode} onChange={(m) => { set({mode: m}); unpick(); }}
               options={[{value: "lines", label: t("ui.layer.Lines")}, {value: "spots", label: t("ui.layer.Spots")}]} />

    <div class="c-layer-filters">
      <Field label={t("ui.layer.length")} htmlFor="layer-length-lo">
        <div class="c-layer-pair">
          <NumberSelect id="layer-length-lo" label={t("ui.layer.shortest")} value={String(state.length[0])}
                        options={edges.length.slice(0, -1).map((v) => [String(v), t("ui.layer.from_m", {value: v})])}
                        onChange={(v) => onLength(+v, Math.max(state.length[1], edges.length[edges.length.indexOf(+v) + 1]), false)} />
          <NumberSelect id="layer-length-hi" label={t("ui.layer.longest")} value={String(state.length[1])}
                        options={edges.length.slice(1).map((v) => [String(v), t("ui.layer.to_m", {value: v})])}
                        onChange={(v) => onLength(Math.min(state.length[0], edges.length[edges.length.indexOf(+v) - 1]), +v, false)} />
        </div>
      </Field>
      {["prominence", "wall", "clearance", "height"].filter((d) => cube0.kinds[d]).map((d) =>
        <Field key={d} label={dimensionLabel(d, ctx)} htmlFor={`layer-${d}`}>{control(d)}</Field>)}
      <Field label={t("ui.layer.trees")} htmlFor="layer-trees">
        <select id="layer-trees" class="u-input" value={state.trees} disabled={!dsm}
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
      {!dsm && <p class="u-small c-layer-note">{t("ui.layer.no_dsm")}</p>}
    </div>

    {fold.length > 0 && <details class="c-layer-more" open={more}
                                 onToggle={(e) => setMore((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>{t("ui.layer.more")} <span class="u-badge u-n">{foldCount}</span>
        {foldSet.length > 0 && <span class="c-layer-more-set">{t("ui.layer.more_set", {count: foldSet.length})}</span>}
        <Icon name="down" /></summary>
      <div class="c-layer-more-body">
        {fold.map((topic) => <div key={topic.id} class="c-layer-fold-topic">
          <h3 class="c-layer-topic-name">{t(`ui.layer.topic.${topic.id}`)}</h3>
          <div class="c-layer-filters c-layer-fold">{topic.dims.map((d) =>
            <div key={d} class={WIDE.has(d) ? "c-layer-wide" : undefined}>{foldField(d)}</div>)}</div>
        </div>)}
        {!lifts && fold.some((topic) => topic.dims.includes("lift_needed")) && <p class="u-small c-layer-note">{t("ui.layer.no_lift", {name: current.name})}</p>}
        {!dsm && fold.some((topic) => topic.dims.includes("clearance_trees")) && <p class="u-small c-layer-note">{t("ui.layer.no_dsm_trees")}</p>}
      </div>
    </details>}
    {!more && foldSet.length > 0 && <div class="u-chips c-layer-more-chips">
      {foldSet.map((d) => <button key={d} type="button" class="u-chip u-on" title={t("ui.layer.more_open")}
                                  onClick={() => setMore(true)}>
        {d === "elevation" ? t("ui.layer.dim.elevation.label") : dimensionShort(d, ctx)}: {foldText(d)}</button>)}
    </div>}

    <section class="c-layer-legend" aria-label={t("ui.layer.per_km2_of", {noun: Noun})}>
      <h2 class="u-h4">{t("ui.layer.per_km2_of", {noun: Noun})}</h2>
      <ul class="c-layer-classes">
        {labels.map((text, k) => <li key={k}><span class={`c-layer-swatch c-layer-k${k + 1}`} aria-hidden="true" />{text}</li>)}
      </ul>
      {partnerRows && !outlineMode && <div class="c-layer-legend-extra">
        <span class="c-layer-swatch c-layer-hatch" aria-hidden="true" />{t("ui.layer.legend_beyond", {name: hatchName})}</div>}
      <Field label={t("ui.layer.scale")}>
        <Segmented label={t("ui.layer.scale")} value={state.scale} onChange={(scale) => set({scale})}
                   options={[{value: "fit", label: t("ui.layer.scale_fit")}, {value: "fixed", label: t("ui.layer.scale_fixed")}]} />
      </Field>
      <p class="u-small">{outlineMode ? t("ui.layer.scale_outline_note")
        : state.scale === "fit" ? t("ui.layer.scale_fit_note") : t("ui.layer.scale_fixed_note")}
        {partnerRows && !outlineMode && state.scale === "fit" ? ` ${t("ui.layer.scale_hatch_note")}` : ""}</p>
    </section>

    <section class="c-layer-view" aria-live="polite">
      <div class="c-layer-total">
        {status === "ready" && outlineMode ? <span><b>{inView.length}</b> {t("ui.layer.countries_in_view", {count: inView.length})}
            {histStatus === "ready" && hist && <> · <b>{hist.total.toLocaleString("en")}</b> {noun}</>}</span>
          : status === "ready" ? <>
              <span><b>{total.toLocaleString("en")}</b> {noun}, <b>{otherTotal === null ? "…" : otherTotal.toLocaleString("en")}</b>{" "}
                {mode === "lines" ? t("ui.layer.spots_in_view") : t("ui.layer.lines_in_view")}</span>
              {border === "all" && split && split.owned + split.partner > 0 && <div class="c-layer-split">
                {t("ui.layer.split", {across: (split.owned + split.partner).toLocaleString("en")})}
                {split.partner > 0 ? `, ${t("ui.layer.split_beyond", {beyond: split.partner.toLocaleString("en")})}` : ""}</div>}
              <div class="u-small">{t("ui.layer.cells_here", {name: levelName(cellDeg(cube0, level)), size: sizeText(cellDeg(cube0, level), centreLat)})}
                {state.level === "auto" ? ` ${t("ui.layer.auto_note")}` : ""}</div>
            </>
          : status === "too-many" ? <span class="c-error">{t("ui.layer.too_many")}</span>
          : status === "error" ? <span class="c-error" role="alert">{message}</span>
          : <span class="u-small">{t("ui.layer.counting")}</span>}
      </div>
      <Field label={t("ui.layer.border.label")}>
        <Segmented label={t("ui.layer.border.label")} value={border} onChange={(b) => { unpick(); set({border: b}); }}
                   options={[{value: "all", label: t("ui.layer.border.all")},
                             {value: "own", label: t("ui.layer.border.own", {name: current.name})}]} />
      </Field>
      <p class="u-small c-layer-border-hint">{borderHint}</p>
      <Field label={t("ui.layer.cells")}>
        <Segmented label={t("ui.layer.cells")} value={state.level} onChange={(l) => set({level: l})} options={levels} />
      </Field>
      <p class="u-small c-layer-note">{t("ui.layer.sizes", {sizes: levelValues.map((l) =>
        `${levelName(cellDeg(cube0, l))} ≈ ${sizeText(cellDeg(cube0, l), centreLat)}`).join(" · "), lat: Math.round(centreLat)})}</p>
      <div class="c-layer-link">
        <Button icon="link" onClick={copyLink}>{t("ui.layer.copy_link")}</Button>
        {copied === "ok" && <span class="u-small">{t("ui.layer.copied")}</span>}
      </div>
      {copied === "fail" && <LinkField text={location.href} />}
    </section>

    {picked && pickedCube ? <section class="c-layer-cell" aria-label={t("ui.layer.selected")}>
      <h2 class="u-h4">{t("ui.layer.selected")}</h2>
      <div class="u-small">{picked.side
        ? (partnerName(pickedCube, picked.side, cubes) ? t("ui.layer.where_partner", {country: pickedCube.name, name: partnerName(pickedCube, picked.side, cubes)})
          : t("ui.layer.where_beyond", {country: pickedCube.name}))
        : picked.km2 < picked.whole * 0.999
          ? (cutNeighbour ? t("ui.layer.where_border_with", {country: pickedCube.name, name: cutNeighbour})
            : t("ui.layer.where_border", {country: pickedCube.name}))
          : pickedCube.name}</div>
      <div>{t("ui.layer.cell_size", {name: levelName(picked.deg), size: sizeText(picked.deg, centre ? centre[0] : centreLat)})}
        {" · "}{picked.km2 < picked.whole * 0.999
          ? (picked.side ? t("ui.layer.cell_beyond", {km2: picked.km2.toFixed(2)}) : t("ui.layer.cell_inside", {km2: picked.km2.toFixed(2), name: pickedCube.name}))
          : `${picked.km2.toFixed(2)} km²`}</div>
      <div><b>{picked.count.toLocaleString("en")}</b> {noun}
        {otherInCell !== null && <> · <b>{otherInCell.toLocaleString("en")}</b> {mode === "lines" ? t("ui.layer.spots") : t("ui.layer.lines")}</>}
        {" · "}{short(picked.count / picked.km2)} {noun} {t("ui.layer.per_km2")}</div>
      {picked.km2 < picked.whole * 0.999 && !picked.side &&
        <div class="u-small">{t("ui.layer.cell_cut", {km2: short(picked.km2), name: pickedCube.name})}</div>}
      {picked.side ? <div class="c-layer-cell-border">{t("ui.layer.cell_partner")}</div>
        : acrossInCell ? <div class="c-layer-cell-border">{t("ui.layer.cell_across", {n: acrossInCell.toLocaleString("en")})}</div> : null}
      {centre && <div class="u-small u-mono">{centre[0].toFixed(4)}, {centre[1].toFixed(4)}</div>}
      <div class="c-layer-search">
        {pickedBands.map((b) => <Button key={b.name} icon="search" href={cellHash(pickedCube.id, b.name, picked.level, picked.i, picked.j)}>
          {t("ui.layer.search_here")}: {b.name} · {range(b.lengths[0], b.lengths[1])}</Button>)}
      </div>
      {cardHint ? <p class="c-layer-search-hint"><Icon name="info" /><span>{cardHint}</span></p>
        : <p class="u-small">{t("ui.layer.search_note")}</p>}
    </section> : <p class="u-small">{t("ui.layer.click_hint")}</p>}

    <section class="c-layer-notes">
      <h2 class="u-h4">{t("ui.layer.about")}</h2>
      <ul class="u-small">
        <li>{t("ui.layer.note_spot", {size: clusterM})}</li>
        <li>{t("ui.layer.note_cut")}</li>
        <li class={mode === "spots" && several ? "c-layer-warn" : undefined}>{t("ui.layer.note_upper")}</li>
        {shownCubes.map((c) => <li key={c.id}>{t("ui.layer.note_bands", {name: c.name})}{" "}
          {c.bands.filter((b) => b.layer).map((b) => `${b.name} ${b.resolution} m (${range(b.lengths[0], b.lengths[1])})`).join(", ")}.</li>)}
        <li>{t("ui.layer.note_west")}</li>
        {border === "all" && neighbourNotes.length > 0 && <li class="c-layer-notes-sub">{t("ui.layer.border.notes")}</li>}
        {neighbourNotes.map((n, k) => <li key={`n${k}`} class="c-layer-border-note">{n}</li>)}
        {border === "own" && <li>{t("ui.layer.border.note_own", {name: current.name})}</li>}
        {shownCubes.flatMap((c) => c.notes).map((n, k) => <li key={k}>{n}</li>)}
      </ul>
    </section>

    {credits.length > 0 &&
      <p class="u-small c-layer-credits" dangerouslySetInnerHTML={{__html: creditsHtml(credits, user.local ? "" : "/about")}} />}
  </div>;
}

export function LayerPage({params}: {params: URLSearchParams}) {
  if (!user.local && !user.admin) return <div class="c-page"><p>{t("ui.layer.admins_only")}</p></div>;
  return <MapPage title={t("ui.layer.title")} aside={t("ui.layer.histograms")}>{(place, aside, extras) =>
    <LayerPanel place={place} aside={aside} source={SERVER} params={params} extras={extras} />}</MapPage>;
}
