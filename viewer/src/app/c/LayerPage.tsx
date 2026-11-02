// The highline layer (#layer, #layer&country=<id>; the local app and administrators, shells C and D): a
// country searched offline in fixed tiles (country.py) keeps only counts, in a counter cube of 1, 2, 4 and
// 8 km cells (countcube.py); /api/countries/<id>/cells sums the cells in view that pass the filters. The
// panel holds the filters, the legend, the level and the selected cell with one "Search here" per layer
// band (#new&cell=…, NewSearch); the cells are polygons on a canvas, coloured by their density per km² in
// log classes fixed per mode (CLASS_BREAKS), so a colour means the same while panning and zooming.
// The source of the cubes and cells is a prop: the server (SERVER), or canned data (?ui=kit-layer, Gallery).

import { useEffect, useRef, useState } from "preact/hooks";
import L from "leaflet";
import { Button, Field, Segmented } from "../../ui/components";
import { ApiError, api, user, type CountryCells, type CountryCube } from "../api";
import type { PlaceMap } from "../PlaceMap";
import { SafeCanvas } from "../../result/ResultMap";
import { creditsHtml } from "../../layers";
import { day } from "../../time";
import { MapPage } from "./Account";
import { cellHash, go, layerHash } from "./route";
import "./c.css";

export type LayerMode = "lines" | "spots";
export type LayerLevel = "auto" | "1" | "2" | "4" | "8";

/** Where the page gets its cubes and cells: the server, or the demo's canned data. */
export interface LayerSource {
  countries(): Promise<{countries: CountryCube[]}>;
  cells(id: string, query: Record<string, string>, signal: AbortSignal): Promise<CountryCells>;
}
export const SERVER: LayerSource = {countries: api.countries, cells: api.countryCells};

export const DEBOUNCE_MS = 300;
/** The density classes per km² (lines; spots), on a log scale: a cell of density d is in class k when
 *  d >= breaks[k-1] (k = 0 below the first). Five classes: the tokens --layer-1 … --layer-5 (ui/tokens.css,
 *  checked with the dataviz skill's validator: one hue, light to dark, in both themes). Fixed, never fitted
 *  to the view, so a colour keeps its meaning (the report: 1 to 23 million lines and 0.1 to 40 000 spots
 *  per km²). */
export const CLASS_BREAKS: Record<LayerMode, number[]> = {lines: [10, 300, 1e4, 3e5], spots: [1, 10, 100, 1000]};
const CLASSES = 5;
const TOO_MANY = "Too many cells at this level: zoom in, or choose a coarser level or Auto.";

/** The class (0 … 4) of a density per km². */
export function densityClass(density: number, mode: LayerMode): number {
  let k = 0;
  for (const b of CLASS_BREAKS[mode]) if (density >= b) k++;
  return k;
}

/** 300000 → "300 k", 12 → "12", 0.5 → "0.5". */
export function short(n: number): string {
  if (n >= 1e6) return `${+(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M`;
  if (n >= 1e4) return `${+(n / 1e3).toFixed(0)} k`;
  if (n >= 100) return String(Math.round(n));
  return String(+n.toFixed(n >= 10 ? 0 : n >= 1 ? 1 : 2));
}

/** The legend's label of each class. */
function classLabels(mode: LayerMode): string[] {
  const b = CLASS_BREAKS[mode];
  return [`< ${short(b[0])}`, ...b.slice(1).map((x, k) => `${short(b[k])} – ${short(x)}`), `≥ ${short(b[b.length - 1])}`];
}

/** The class colours of the theme in force, from the tokens on `element`'s .ui root. */
function classColours(element: HTMLElement): string[] {
  const style = getComputedStyle(element);
  return Array.from({length: CLASSES}, (_, k) => style.getPropertyValue(`--layer-${k + 1}`).trim() || "#2a78d6");
}

export interface PickedCell { level: number; cell_m: number; i: number; j: number; count: number; corners: number[] }

/** The cells on the map: polygons on their own canvas (safe on removal), the picked one outlined. */
class CellsLayer {
  private readonly renderer = new SafeCanvas({padding: 0.5});
  private readonly group = L.layerGroup();
  private readonly top = L.layerGroup();

  constructor(private readonly map: L.Map, private readonly onPick: (row: number[]) => void) {
    this.group.addTo(map);
    this.top.addTo(map);
  }

  draw(data: CountryCells | null, mode: LayerMode, picked: PickedCell | null) {
    this.group.clearLayers();
    this.top.clearLayers();
    const container = this.map.getContainer();
    const colours = classColours(container);
    const style = getComputedStyle(container);
    const km2 = data ? (data.cell_m / 1000) ** 2 : 1;
    const noun = mode === "lines" ? "lines" : "spots";
    for (const row of data?.cells || []) {
      const density = row[2] / km2;
      const colour = colours[densityClass(density, mode)];
      const polygon = L.polygon(corners(row.slice(3)), {renderer: this.renderer, color: colour, weight: 0.6, opacity: 0.9,
                                                         fillColor: colour, fillOpacity: 0.62});
      polygon.bindTooltip(`${row[2].toLocaleString("en")} ${noun} · ${short(density)} per km²`, {sticky: true});
      polygon.on("click", (e: L.LeafletMouseEvent) => { L.DomEvent.stopPropagation(e as any); this.onPick(row); });
      this.group.addLayer(polygon);
    }
    if (picked) {
      const ring = corners(picked.corners);
      const halo = style.getPropertyValue("--halo").trim() || "#ffffff";
      const ink = style.getPropertyValue("--ink").trim() || "#17201c";
      this.top.addLayer(L.polygon(ring, {renderer: this.renderer, interactive: false, color: halo, weight: 5, fill: false}));
      this.top.addLayer(L.polygon(ring, {renderer: this.renderer, interactive: false, color: ink, weight: 2.5, fill: false}));
    }
  }

  remove() {
    this.group.remove();
    this.top.remove();
    this.renderer.remove();
  }
}

/** [lat, lon] × 4 of a row's corners (SW, SE, NE, NW). */
function corners(flat: number[]): L.LatLngTuple[] {
  return [0, 2, 4, 6].map((k) => [flat[k], flat[k + 1]] as L.LatLngTuple);
}

interface Filters {
  mode: LayerMode;
  length: [number, number];
  prominence: number;
  wall: number | null;
  clearance: number;
  height: number;
  trees: "all" | "no" | "only";
  water: "all" | "land" | "water";
  level: LayerLevel;
}

function defaults(cube: CountryCube): Filters {
  const length = cube.edges.length;
  return {mode: "lines", length: [length[0], length[length.length - 1]], prominence: 0, wall: null, clearance: 0, height: 0,
          trees: "all", water: "all", level: "auto"};
}

/** The query of /api/countries/<id>/cells (without bbox). */
export function cellsQuery(f: Filters): Record<string, string> {
  const query: Record<string, string> = {mode: f.mode, level: f.level, length: `${f.length[0]}-${f.length[1]}`,
                                         prominence: String(f.prominence), clearance: String(f.clearance),
                                         height: String(f.height), trees: f.trees, water: f.water};
  if (f.wall !== null) query.wall = String(f.wall);
  return query;
}

/** A select of [value, text] options. */
function NumberSelect({id, value, options, label, onChange}:
                      {id: string; value: string; options: [string, string][]; label?: string; onChange(v: string): void}) {
  return <select id={id} class="u-input" value={value} aria-label={label}
                 onChange={(e) => onChange((e.target as HTMLSelectElement).value)}>
    {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
  </select>;
}

/** The panel of the highline layer, on `place`'s map. `country`: the one asked for (null: the first);
 *  `onCountry`: another chosen; `pick`: the demo's way to select a cell of the first answer. */
export function LayerPanel({place, source, country, onCountry, pick}:
                           {place: PlaceMap; source: LayerSource; country: string | null; onCountry(id: string): void;
                            pick?: (data: CountryCells) => number[] | null}) {
  const [cubes, setCubes] = useState<CountryCube[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    source.countries().then((r) => setCubes(r.countries), (e) => setError(e.message));
  }, [source]);
  if (error) return <p class="c-error" role="alert">{error}</p>;
  if (!cubes) return <p class="u-small">Loading the layers…</p>;
  if (!cubes.length) {
    return <p class="u-small">No country has a highline layer yet. A layer is computed offline:
      <span class="u-mono"> findaline.py country run &lt;id&gt;</span>, then
      <span class="u-mono"> country build &lt;id&gt;</span>.</p>;
  }
  const cube = cubes.find((c) => c.id === country) || cubes[0];
  return <CountryLayer key={cube.id} place={place} source={source} cube={cube} cubes={cubes} onCountry={onCountry} pick={pick} />;
}

function CountryLayer({place, source, cube, cubes, onCountry, pick}:
                      {place: PlaceMap; source: LayerSource; cube: CountryCube; cubes: CountryCube[];
                       onCountry(id: string): void; pick?: (data: CountryCells) => number[] | null}) {
  const [filters, setFilters] = useState<Filters>(() => defaults(cube));
  const [view, setView] = useState(0);         // map moves seen
  const [theme, setTheme] = useState(0);       // theme changes seen (the canvas reads the tokens)
  const [data, setData] = useState<CountryCells | null>(null);
  const [status, setStatus] = useState<"waiting" | "loading" | "ready" | "too-many" | "error">("waiting");
  const [message, setMessage] = useState("");
  const [picked, setPicked] = useState<PickedCell | null>(null);
  const layer = useRef<CellsLayer | null>(null);
  const picking = useRef(pick);
  const set = (change: Partial<Filters>) => setFilters((f) => ({...f, ...change}));

  const choose = (row: number[], answer: CountryCells) =>
    setPicked({level: answer.level, cell_m: answer.cell_m, i: row[0], j: row[1], count: row[2], corners: row.slice(3)});
  const answer = useRef<CountryCells | null>(null);
  answer.current = data;

  // The map: the country in view, the cells' layer, the moves and the theme followed
  useEffect(() => {
    const map = place.map;
    const [west, south, east, north] = cube.bounds_wgs84;
    map.fitBounds([[south, west], [north, east]]);
    layer.current = new CellsLayer(map, (row) => answer.current && choose(row, answer.current));
    const moved = () => setView((v) => v + 1);
    const clicked = () => setPicked(null);
    map.on("moveend", moved);
    map.on("click", clicked);
    const root = map.getContainer().closest(".ui");
    const observer = new MutationObserver(() => setTheme((t) => t + 1));
    if (root) observer.observe(root, {attributes: true, attributeFilter: ["data-theme"]});
    const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
    const system = () => setTheme((t) => t + 1);
    media?.addEventListener("change", system);
    return () => {
      map.off("moveend", moved);
      map.off("click", clicked);
      observer.disconnect();
      media?.removeEventListener("change", system);
      layer.current?.remove();
      layer.current = null;
    };
  }, [place, cube]);

  // The cells, DEBOUNCE_MS after the last move or change, the request before aborted
  const query = cellsQuery(filters);
  const key = JSON.stringify(query) + "|" + view;
  useEffect(() => {
    const controller = new AbortController();
    setStatus("waiting");
    const timer = setTimeout(() => {
      setStatus("loading");
      source.cells(cube.id, {...query, bbox: place.map.getBounds().toBBoxString()}, controller.signal).then((cells) => {
        if (controller.signal.aborted) return;
        setData(cells);
        setStatus("ready");
        if (picking.current) {
          const row = picking.current(cells);
          picking.current = undefined;
          if (row) choose(row, cells);
        }
      }, (e: Error) => {
        if (controller.signal.aborted) return;
        if (e instanceof ApiError && e.status === 400 && /too many cells/i.test(e.message)) {
          setStatus("too-many");
          setData(null);
        } else {
          setStatus("error");
          setMessage(e.message);
        }
      });
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, cube, source]);

  // The picked cell follows the answers: its count again, or gone at another level
  useEffect(() => {
    if (!data || !picked) return;
    if (data.level !== picked.level) { setPicked(null); return; }
    const row = data.cells.find((r) => r[0] === picked.i && r[1] === picked.j);
    const count = row ? row[2] : 0;
    if (count !== picked.count) setPicked({...picked, count});
  }, [data]);

  useEffect(() => { layer.current?.draw(data, filters.mode, picked); }, [data, filters.mode, picked, theme]);

  const edges = cube.edges;
  const layerBands = cube.bands.filter((b) => b.layer);
  const done = layerBands.reduce((s, b) => s + b.done, 0), tiles = layerBands.reduce((s, b) => s + b.tiles, 0);
  const full = edges.length[0] === filters.length[0] && edges.length[edges.length.length - 1] === filters.length[1];
  const several = [!full, filters.prominence > 0, filters.wall !== null, filters.clearance > 0, filters.height > 0,
                   filters.trees !== "all", filters.water !== "all"].filter(Boolean).length > 1;
  const noun = filters.mode === "lines" ? "Lines" : "Spots";
  const labels = classLabels(filters.mode);
  const centre = picked && [0, 2, 4, 6].reduce((s, k) => [s[0] + picked.corners[k] / 4, s[1] + picked.corners[k + 1] / 4], [0, 0]);
  const levels: {value: LayerLevel; label: string}[] = [{value: "auto", label: "Auto"},
    ...cube.levels.map((l) => ({value: String(l) as LayerLevel, label: `${l * cube.cell_m / 1000} km`}))];
  const range = (lo: number, hi: number) => `${short(lo)}–${short(hi)} m`;

  return <div class="c-layer">
    <div class="c-layer-head">
      {cubes.length > 1
        ? <Field label="Country" htmlFor="layer-country">
            <NumberSelect id="layer-country" value={cube.id} options={cubes.map((c) => [c.id, c.name])} onChange={onCountry} />
          </Field>
        : <b class="c-layer-name">{cube.name}</b>}
      <span class="u-small">Built {day(cube.built, "?")}{cube.partial && ` · partial: ${done} of ${tiles} tiles`}</span>
    </div>

    <Segmented label="Count" value={filters.mode} onChange={(mode) => { set({mode}); setPicked(null); }}
               options={[{value: "lines", label: "Lines"}, {value: "spots", label: "Spots"}]} />

    <div class="c-layer-filters">
      <Field label="Length" htmlFor="layer-length-lo">
        <div class="c-layer-pair">
          <NumberSelect id="layer-length-lo" label="Shortest" value={String(filters.length[0])}
                        options={edges.length.slice(0, -1).map((v) => [String(v), `from ${v} m`])}
                        onChange={(v) => set({length: [+v, Math.max(filters.length[1], edges.length[edges.length.indexOf(+v) + 1])]})} />
          <NumberSelect id="layer-length-hi" label="Longest" value={String(filters.length[1])}
                        options={edges.length.slice(1).map((v) => [String(v), `to ${v} m`])}
                        onChange={(v) => set({length: [Math.min(filters.length[0], edges.length[edges.length.indexOf(+v) - 1]), +v]})} />
        </div>
      </Field>
      <Field label="Prominence (weaker anchor)" htmlFor="layer-prominence">
        <NumberSelect id="layer-prominence" value={String(filters.prominence)} onChange={(v) => set({prominence: +v})}
                      options={edges.prominence.map((v) => [String(v), v ? `≥ ${v} m` : "Any"])} />
      </Field>
      <Field label="Wall angle (steeper anchor)" htmlFor="layer-wall">
        <NumberSelect id="layer-wall" value={filters.wall === null ? "" : String(filters.wall)}
                      onChange={(v) => set({wall: v === "" ? null : +v})}
                      options={[["", "Any"], ...edges.wall.filter((v) => v > 0).map((v) => [String(v), `< ${v}°`] as [string, string])]} />
      </Field>
      <Field label="Clearance" htmlFor="layer-clearance">
        <NumberSelect id="layer-clearance" value={String(filters.clearance)} onChange={(v) => set({clearance: +v})}
                      options={edges.clearance.map((v) => [String(v), v ? `≥ ${v} m` : "Any"])} />
      </Field>
      <Field label="Webbing height" htmlFor="layer-height">
        <NumberSelect id="layer-height" value={String(filters.height)} onChange={(v) => set({height: +v})}
                      options={edges.height.map((v) => [String(v), v ? `≥ ${v} m` : "Any"])} />
      </Field>
      <Field label="Over trees and buildings" htmlFor="layer-trees">
        <select id="layer-trees" class="u-input" value={filters.trees} disabled={!cube.dsm}
                onChange={(e) => set({trees: (e.target as HTMLSelectElement).value as Filters["trees"]})}>
          <option value="all">Any</option><option value="no">Not over them</option><option value="only">Only over them</option>
        </select>
      </Field>
      <Field label="Over water" htmlFor="layer-water">
        <select id="layer-water" class="u-input" value={filters.water}
                onChange={(e) => set({water: (e.target as HTMLSelectElement).value as Filters["water"]})}>
          <option value="all">Any</option><option value="land">Not over water</option><option value="water">Over water</option>
        </select>
      </Field>
      {!cube.dsm && <p class="u-small c-layer-note">No surface model was used for this country: every line counts as not
        over trees or buildings.</p>}
    </div>

    <section class="c-layer-legend" aria-label={`${noun} per km²`}>
      <h2 class="u-h4">{noun} per km²</h2>
      <ul class="c-layer-classes">
        {labels.map((text, k) => <li key={k}><span class={`c-layer-swatch c-layer-k${k + 1}`} aria-hidden="true" />{text}</li>)}
      </ul>
      <p class="u-small">Classes on a log scale, the same everywhere: a cell's count divided by its km².</p>
    </section>

    <section class="c-layer-view" aria-live="polite">
      <div class="c-layer-total">
        {status === "ready" && data ? <span><b>{data.total.toLocaleString("en")}</b> {noun.toLowerCase()} in view ·{" "}
          {data.cell_m / 1000} km cells (level {data.level})</span>
          : status === "too-many" ? <span class="c-error">{TOO_MANY}</span>
          : status === "error" ? <span class="c-error" role="alert">{message}</span>
          : <span class="u-small">Counting…</span>}
      </div>
      <Field label="Cells">
        <Segmented label="Cells" value={filters.level} onChange={(level) => set({level})} options={levels} />
      </Field>
    </section>

    {picked ? <section class="c-layer-cell" aria-label="Selected cell">
      <h2 class="u-h4">Selected cell</h2>
      <div><b>{picked.count.toLocaleString("en")}</b> {noun.toLowerCase()} · {short(picked.count / (picked.cell_m / 1000) ** 2)} per
        km² · {picked.cell_m / 1000} km cell</div>
      {centre && <div class="u-small u-mono">{centre[0].toFixed(4)}, {centre[1].toFixed(4)}</div>}
      <div class="c-layer-search">
        {layerBands.map((b) => <Button key={b.name} icon="search" href={cellHash(cube.id, b.name, picked.level, picked.i, picked.j)}>
          Search here: {b.name} · {range(b.lengths[0], b.lengths[1])}</Button>)}
      </div>
      <p class="u-small">A search of the cell and the band's longest line around it, with the band's settings.</p>
    </section> : <p class="u-small">Click a cell to see its count and search it.</p>}

    <section class="c-layer-notes">
      <h2 class="u-h4">About these counts</h2>
      <ul class="u-small">
        <li>A spot is a pair of 50 m clusters of anchors with a line between them: coarser than the groups of a search.</li>
        <li class={filters.mode === "spots" && several ? "c-layer-warn" : undefined}>With several filters, spots are an upper
          bound: each filter may be met by another line of the spot.</li>
        <li>Only lines with both anchors inside the country are counted.</li>
        <li>Each band has its own grid: {layerBands.map((b) => `${b.name} ${b.resolution} m (${range(b.lengths[0], b.lengths[1])})`).join(", ")}.</li>
        {!cube.dsm && <li>No surface model: trees and buildings under a line were not checked.</li>}
        {cube.notes.map((n, k) => <li key={k}>{n}</li>)}
      </ul>
    </section>

    {cube.credits.length > 0 &&
      <p class="u-small c-layer-credits" dangerouslySetInnerHTML={{__html: creditsHtml(cube.credits, user.local ? "" : "/about")}} />}
  </div>;
}

export function LayerPage({country}: {country: string | null}) {
  if (!user.local && !user.admin) return <div class="c-page"><p>The local app and administrators only.</p></div>;
  return <MapPage title="Highline layer">{(place) =>
    <LayerPanel place={place} source={SERVER} country={country} onCountry={(id) => go(layerHash(id), true)} />}</MapPage>;
}
