// ?ui=kit: every base component in the light and the dark theme side by side, for review and tests.
// The toggle shows one column in the chosen theme instead (remembered for B and C).
// ?ui=kit-layer (KitLayer): the highline layer's page (app/c/LayerPage) on canned data, without a server:
// two cubes (Slovakia and a made-up country north-west of it) and cells made up from a few hot spots (?theme=light|dark).

import { useState } from "preact/hooks";
import { BottomNav, Button, Chip, Chips, Field, IconButton, Panel, Progress, Range, RangePair, Rail, Screen,
         Segmented, Sheet, Stat, Stats, StatusChip, Tabs, Toast, type Snap, type Theme } from "./components";
import { ICONS, Icon, Logo, type IconName } from "./icons";
import { storeTheme, storedTheme, uiHref } from "./choice";
import { DESKTOP, useMedia } from "./components";
import { ApiError, type CountryBand, type CountryCells, type CountryCube, type CountryHistogram, type CountryOutline } from "../app/api";
import { MapPage } from "../app/c/Account";
import { LayerPanel, type LayerSource } from "../app/c/LayerPage";

function Column({theme}: {theme: Theme}) {
  const [mode, setMode] = useState<"point" | "area" | "cliffs" | "file">("point");
  const [tab, setTab] = useState<"lines" | "details">("lines");
  const [chips, setChips] = useState({clear: true, trees: false});
  const [extra, setExtra] = useState(["≤ 10 m Δh"]);
  const [length, setLength] = useState(120);
  const [span, setSpan] = useState<[number, number]>([30, 150]);
  const [nav, setNav] = useState<"search" | "searches" | "favourites">("search");
  const [snap, setSnap] = useState<Snap>("half");
  const [toast, setToast] = useState(true);
  return <Screen theme={theme} screen={false} class="u-gal-col">
    <h2 class="u-h u-xl">{{auto: "System theme", light: "Light", dark: "Dark"}[theme]}</h2>

    <section class="u-gal-sec"><h3>Logo and icons</h3>
      <Logo />
      <div class="u-gal-icons">{(Object.keys(ICONS) as IconName[]).map((n) =>
        <div key={n}><Icon name={n} />{n}</div>)}<div><Icon name="star" fav />star (fav)</div></div>
    </section>

    <section class="u-gal-sec"><h3>Buttons</h3>
      <div class="u-row">
        <Button kind="primary" icon="search">Find lines</Button>
        <Button icon="share">Share</Button>
        <Button kind="ghost" icon="back">Back</Button>
        <Button kind="danger">Delete</Button>
        <Button disabled>Disabled</Button>
      </div>
      <Button kind="primary" large full iconRight="next">Start search</Button>
      <div class="u-row">
        <IconButton icon="layers" label="Layers" />
        <IconButton icon="ruler" label="Measure" on />
        <IconButton icon="star" label="Favourite" fav plain />
        <IconButton icon="more" label="More" round />
      </div>
    </section>

    <section class="u-gal-sec"><h3>Chips</h3>
      <Chips>
        <Chip on={chips.clear} onClick={() => setChips({...chips, clear: !chips.clear})}>Clear</Chip>
        <Chip on={chips.trees} onClick={() => setChips({...chips, trees: !chips.trees})}>Over trees</Chip>
        {extra.map((e) => <Chip key={e} on onRemove={() => setExtra(extra.filter((x) => x !== e))}>{e}</Chip>)}
        <Chip add onClick={() => setExtra([...extra, `filter ${extra.length + 1}`])}>More filters</Chip>
      </Chips>
    </section>

    <section class="u-gal-sec"><h3>Segmented and tabs</h3>
      <Segmented label="Where" value={mode} onChange={setMode} options={[
        {value: "point", label: "Point", icon: "pin"}, {value: "area", label: "Area", icon: "poly"},
        {value: "cliffs", label: "Along cliffs", icon: "cliff"}, {value: "file", label: "File", icon: "file"}]} />
      <Tabs label="Result" value={tab} onChange={setTab} tabs={[
        {value: "lines", label: "Lines", icon: "list", badge: 42}, {value: "details", label: "Details", icon: "info"}]} />
    </section>

    <section class="u-gal-sec"><h3>Panel, fields and ranges</h3>
      <Panel title="Search settings" actions={<IconButton icon="close" label="Close" plain />}>
        <Field label="Longest line" value={`${length} m`} help="Lines up to this length are checked." htmlFor={`len-${theme}`}
               hint="The distance between the anchors. A narrow range gives a faster search and a clearer map.">
          <Range id={`len-${theme}`} label="Longest line" value={length} min={10} max={500} step={5} onInput={setLength} />
        </Field>
        <Field label="Length" value={`${span[0]}–${span[1]} m`}>
          <RangePair label="Length" low={span[0]} high={span[1]} min={10} max={500} step={5}
                     onInput={(lo, hi) => setSpan([lo, hi])} />
        </Field>
        <Field label="Place" help="A name, coordinates or a link." htmlFor={`place-${theme}`}>
          <input id={`place-${theme}`} class="u-input" placeholder="Żabi Koń" />
        </Field>
      </Panel>
    </section>

    <section class="u-gal-sec"><h3>Status, progress, stats</h3>
      <div class="u-row">
        <StatusChip status="running" /><StatusChip status="done" /><StatusChip status="waiting" />
        <StatusChip status="failed" /><StatusChip status="shared" />
      </div>
      <Progress value={0.62} label="Downloading · 62%" />
      <Progress value={null} label="Computing…" />
      <Stats><Stat value={142} unit="m" label="length" /><Stat value={38} unit="m" label="height" />
        <Stat value="4.1" unit="m" label="clearance" /><Stat value={12} label="variants" /></Stats>
    </section>

    <section class="u-gal-sec"><h3>Toast</h3>
      {toast ? <Toast action={{label: "Show results", onClick: () => setToast(false)}} onClose={() => setToast(false)}>
        Search "Żabi Koń" is done: 42 lines</Toast>
        : <Button onClick={() => setToast(true)}>Show the toast</Button>}
    </section>

    <section class="u-gal-sec"><h3>Rail, sheet and bottom navigation</h3>
      <div class="u-gal-stage">
        <Rail items={[{value: "search", label: "Search", icon: "search"},
                      {value: "searches", label: "Searches", icon: "clock", badge: 2},
                      {value: "favourites", label: "Favourites", icon: "star"}]}
              value={nav} onChange={setNav} top={<span class="u-mark"><Logo name={false} /></span>}
              bottom={<IconButton icon="user" label="Account" round plain />} />
        <Sheet label="Lines" desktop="sheet" snap={snap} onSnap={setSnap} peek={90}
               header={<div class="u-row"><b class="u-grow">42 lines</b><span class="u-small">{snap}</span></div>}>
          <p>Drag the handle, click it, or use the arrow keys on it.</p>
          {Array.from({length: 12}, (_, i) => <p key={i} class="u-small">Line {i + 1}</p>)}
        </Sheet>
      </div>
      <div class="u-gal-stage">
        <BottomNav items={[{value: "search", label: "Home", icon: "home"},
                           {value: "searches", label: "Search", icon: "plus"},
                           {value: "favourites", label: "Favourites", icon: "star", badge: 3}]}
                   value={nav} onChange={setNav} />
      </div>
    </section>
  </Screen>;
}

export function Gallery() {
  const [theme, setTheme] = useState<Theme | "both">("both");
  const choose = (t: Theme | "both") => { setTheme(t); if (t !== "both") storeTheme(t); };
  return <Screen theme={theme === "both" ? storedTheme() : theme} class="u-gallery">
    <header class="u-gal-top">
      <Logo />
      <b class="u-grow">Component gallery</b>
      <Segmented label="Theme" value={theme} onChange={choose} options={[
        {value: "both", label: "Both"}, {value: "auto", label: "Auto"}, {value: "light", label: "Light"}, {value: "dark", label: "Dark"}]} />
      <a href={uiHref("b")}>B</a><a href={uiHref("c")}>C</a><a href={uiHref("d")}>D</a>
    </header>
    <div class="u-gal-cols">
      {theme === "both" ? <><Column theme="light" /><Column theme="dark" /></> : <Column key={theme} theme={theme} />}
    </div>
  </Screen>;
}

// The canned highline layer of ?ui=kit-layer: two cubes as /api/countries gives them (Slovakia and a made-up
// country north-west of it, their boxes apart), cells of a made-up density around some hot spots in cells of a plain degree grid (the
// server's are cells of the country's CRS), the filters thinning them by rough factors; the histograms split
// the cells' total by fixed shares per bin, consistent with the cells (the length filter is the sum of its
// bins' shares); the outlines are rounded polygons of the bounds.

const KIT_EDGES: CountryCube["edges"] = {length: [30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000], prominence: [0, 5, 10, 20, 50],
                                        wall: [0, 30, 45, 60, 90], clearance: [0, 2, 5, 10, 20], height: [0, 10, 20, 50, 100]};
const KIT_BANDS = (): CountryBand[] =>
  [["S", 30, 300, 1, "formula", 60, 5000, true, 2200], ["M", 300, 1000, 2, "sag", 60, 10000, true, 560],
   ["L", 1000, 5000, 5, "sag", 45, 20000, true, 150], ["M2", 1000, 2000, 2, "sag", 60, 10000, false, 560]]
    .map(([name, lo, hi, resolution, model, slope, core, layer, tiles]) => ({
      name: name as string, lengths: [lo, hi] as [number, number], resolution: resolution as number, model: model as string,
      slope_threshold: slope as number, core_m: core as number, layer: layer as boolean, tiles: tiles as number,
      done: name === "L" ? 120 : tiles as number, seconds: 0, params: {}}));

const KIT_CUBE: CountryCube = {
  id: "slovakia", name: "Slovakia", crs: "EPSG:8353", cell_m: 1000, levels: [1, 2, 4, 8], cluster_m: 50,
  bounds_wgs84: [16.83, 47.73, 22.57, 49.61], edges: KIT_EDGES, bands: KIT_BANDS(),
  dsm: false, water: true, partial: true, totals: {lines: 2.4e9, spots: 4.1e6}, built: "2026-11-03T10:00:00Z",
  credits: [{data: "dem", attribution: "ÚGKK SR", licence: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/", notice: ""},
            {data: "osm", attribution: "© OpenStreetMap contributors", licence: "ODbL", url: "https://www.openstreetmap.org/copyright", notice: ""}],
  notes: ["A sample of made-up counts for the demo.", "Only lines with both anchors inside Slovakia are counted.",
          "The surface model (trees, buildings) was not used: every line counts as not over trees or buildings."],
};
const KIT_CUBE_2: CountryCube = {
  ...KIT_CUBE, id: "westland", name: "Westland", crs: "EPSG:5514", bounds_wgs84: [12.1, 49.7, 16.8, 51.1], bands: KIT_BANDS(),
  dsm: true, partial: false, totals: {lines: 1.1e9, spots: 2.2e6}, built: "2026-11-04T08:00:00Z",
  credits: [{data: "dem", attribution: "ČÚZK", licence: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/", notice: ""},
            {data: "osm", attribution: "© OpenStreetMap contributors", licence: "ODbL", url: "https://www.openstreetmap.org/copyright", notice: ""}],
  notes: ["A second made-up country of the demo.", "Only lines with both anchors inside Westland are counted."],
};
export const KIT_CUBES = [KIT_CUBE, KIT_CUBE_2];

/** [lat, lon, lines per km² at the centre, radius in km] per cube. */
const HOT: Record<string, number[][]> = {
  slovakia: [[49.18, 20.08, 1.2e6, 7], [48.94, 20.38, 2e5, 9], [49.2, 19.05, 3e5, 5], [49.12, 18.55, 6e4, 3],
             [48.75, 20.05, 4e4, 6], [48.63, 20.65, 8e4, 8], [48.95, 19.6, 2e4, 10]],
  westland: [[50.75, 14.3, 5e5, 6], [50.55, 15.7, 2.5e5, 8], [49.95, 13.4, 9e4, 9], [50.3, 12.9, 4e4, 5],
             [50.0, 16.1, 3e4, 7], [50.85, 16.5, 1.5e5, 4]],
};
const KM_LAT = 111.32, KM_LON = 111.32 * Math.cos(49 * Math.PI / 180);
/** The share of each length bin (geometric, summing to 1): the cells' length filter is the sum of its bins. */
const BIN_SHARES = (() => { const w = [1, 0.9, 0.8, 0.62, 0.45, 0.22, 0.09, 0.03, 0.012]; const s = w.reduce((a, b) => a + b, 0); return w.map((x) => x / s); })();
/** The share of the lines at or above each threshold of a dimension (bin k of the histogram: the share between). */
const ABOVE: Record<"prominence" | "clearance" | "height", number[]> = {
  prominence: [1, 0.55, 0.3, 0.17, 0.09], clearance: [1, 0.7, 0.49, 0.34, 0.24], height: [1, 0.7, 0.49, 0.34, 0.24]};
/** The share of the lines below each wall edge (index k: below edges[k]). */
const BELOW_WALL = [0, 0.25, 0.5, 0.75, 1];

function noise(i: number, j: number): number {
  const x = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

/** The thinning of a cube's counts by the filters; `except`: that filter left out (a histogram's own dimension). */
function kitFactor(query: Record<string, string>, except: string = ""): number {
  const edges = KIT_EDGES;
  let factor = 1;
  if (except !== "length") {
    const [lo, hi] = (query.length || "30-5000").split("-").map(Number);
    const a = edges.length.indexOf(lo), b = edges.length.indexOf(hi);
    factor *= BIN_SHARES.slice(a < 0 ? 0 : a, b < 0 ? 9 : b).reduce((s, x) => s + x, 0);
  }
  for (const d of ["prominence", "clearance", "height"] as const) {
    if (except !== d) factor *= ABOVE[d][Math.max(0, edges[d].indexOf(Number(query[d] || 0)))];
  }
  if (except !== "wall" && query.wall) factor *= BELOW_WALL[Math.max(0, edges.wall.indexOf(Number(query.wall)))];
  factor *= query.water === "water" ? 0.04 : query.water === "land" ? 0.98 : 1;
  factor *= query.trees === "only" ? 0.3 : query.trees === "no" ? 0.7 : 1;
  return factor;
}

/** The level of a query over a box: Auto as the server picks it, an explicit one refused over 20000 cells. */
function kitLevel(query: Record<string, string>, km2: number): number {
  let level = query.level === "auto" || !query.level ? 8 : Number(query.level);
  if (query.level === "auto" || !query.level) for (const l of [8, 4, 2, 1]) if (km2 / (l * l) <= 4000) level = l;
  else if (km2 / (level * level) > 20000) throw new ApiError("too many cells: zoom in or choose a coarser level", 400);
  return level;
}

/** The cells of a cube under the query (as /api/countries/<id>/cells); `factor` the filters' thinning. */
function kitCells(cube: CountryCube, query: Record<string, string>, factor = kitFactor(query)): CountryCells {
  const [bw, bs, be, bn] = cube.bounds_wgs84;
  const [west, south, east, north] = query.bbox ? query.bbox.split(",").map(Number) : cube.bounds_wgs84;
  const w = Math.max(west, bw), s = Math.max(south, bs), e = Math.min(east, be), n = Math.min(north, bn);
  const km2 = Math.max(0, e - w) * KM_LON * Math.max(0, n - s) * KM_LAT;
  const level = kitLevel(query, km2);
  const dlat = level / KM_LAT, dlon = level / KM_LON;
  const mode = query.mode === "spots" ? "spots" : "lines";
  const cells: number[][] = [];
  let total = 0, max = 0;
  for (let i = Math.floor((w - bw) / dlon); bw + i * dlon < e; i++) {
    for (let j = Math.floor((s - bs) / dlat); bs + j * dlat < n; j++) {
      const lat = bs + (j + 0.5) * dlat, lon = bw + (i + 0.5) * dlon;
      let density = noise(i, j) < 0.25 ? 3 : 0;
      for (const [hlat, hlon, peak, r] of HOT[cube.id]) {
        const d2 = ((lat - hlat) * KM_LAT) ** 2 + ((lon - hlon) * KM_LON) ** 2;
        density += peak * Math.exp(-d2 / (2 * r * r));
      }
      density *= (0.3 + 2 * noise(j, i)) * factor;
      if (mode === "spots") density = 0.3 * density ** 0.6;
      const count = Math.round(density * level * level);
      if (count <= 0) continue;
      const y0 = bs + j * dlat, x0 = bw + i * dlon;
      cells.push([i, j, count, y0, x0, y0, x0 + dlon, y0 + dlat, x0 + dlon, y0 + dlat, x0].map((v, k) => k < 3 ? v : +v.toFixed(6)));
      total += count;
      max = Math.max(max, count);
    }
  }
  return {level, cell_m: level * 1000, total, max, cells};
}

/** The histogram of a cube under the query (as /histogram): each dimension under every other filter but its own,
 *  the cells' total split by the shares; spots' length bins summing to about 1.4 × the total. */
function kitHistogram(cube: CountryCube, query: Record<string, string>): CountryHistogram {
  const edges = KIT_EDGES;
  const cells = kitCells(cube, query);
  const spots = query.mode === "spots";
  const totalOf = (except: string) => kitCells(cube, query, kitFactor(query, except)).total;
  const t0 = totalOf("length");
  const length = BIN_SHARES.map((share) => Math.round(t0 * share * (spots ? 1.4 : 1)));
  const dimension = (d: "prominence" | "clearance" | "height") => {
    const t = totalOf(d), above = ABOVE[d];
    // a few lines whose prominence is not known (the bin "?")
    return [...above.map((a, k) => Math.round(t * (a - (above[k + 1] ?? 0)))), d === "prominence" ? Math.round(t * 0.02) : 0];
  };
  const tw = totalOf("wall");
  const wall = [...BELOW_WALL.slice(1).map((b, k) => Math.round(tw * (b - BELOW_WALL[k]))), 0, 0];
  return {level: cells.level, cell_m: cells.cell_m, total: cells.total, length, prominence: dimension("prominence"), wall,
          clearance: dimension("clearance"), height: dimension("height")};
}

/** A rounded polygon of the cube's bounds, with its km². */
function kitOutline(cube: CountryCube): CountryOutline {
  const [w, s, e, n] = cube.bounds_wgs84;
  const cx = (w + e) / 2, cy = (s + n) / 2, rx = (e - w) / 2, ry = (n - s) / 2;
  const ring: number[][] = [];
  for (let k = 0; k < 36; k++) {
    const a = k * Math.PI / 18, wobble = 0.9 + 0.08 * Math.sin(3 * a) + 0.04 * Math.cos(5 * a);
    ring.push([+(cx + rx * wobble * Math.cos(a)).toFixed(4), +(cy + ry * wobble * Math.sin(a)).toFixed(4)]);
  }
  ring.push(ring[0]);
  return {tolerance: 0.01, area_km2: Math.round(Math.PI * rx * KM_LON * ry * KM_LAT * 0.81), geometry: {type: "Polygon", coordinates: [ring]}};
}

const answer = <T,>(make: () => T) => new Promise<T>((resolve, reject) => { try { resolve(make()); } catch (e) { reject(e); } });
const cubeOf = (id: string) => { const c = KIT_CUBES.find((k) => k.id === id); if (!c) throw new ApiError("no such country", 404); return c; };
export const KIT_SOURCE: LayerSource = {
  countries: () => Promise.resolve({countries: KIT_CUBES}),
  cells: (id, query) => answer(() => kitCells(cubeOf(id), query)),
  histogram: (id, query) => answer(() => kitHistogram(cubeOf(id), query)),
  outline: (id) => answer(() => kitOutline(cubeOf(id))),
};

/** The densest cell of the first answer, selected for the review's screenshots. */
const densest = (data: CountryCells) => data.cells.reduce<number[] | null>((best, row) => !best || row[2] > best[2] ? row : best, null);

export function KitLayer() {
  const asked = new URLSearchParams(location.search).get("theme");
  const theme: Theme = asked === "light" || asked === "dark" ? asked : storedTheme();
  const wide = useMedia(DESKTOP);
  return <Screen theme={theme} class={`u-app-c c-app ${wide ? "c-wide" : "c-narrow"}`}>
    <main class="c-main c-main-layer">
      <MapPage title="Highline layer" aside="Counts in view">{(place, aside) =>
        <LayerPanel place={place} aside={aside} source={KIT_SOURCE} params={new URLSearchParams(location.hash.replace(/^#/, ""))}
                    pick={densest} />}</MapPage>
    </main>
  </Screen>;
}
