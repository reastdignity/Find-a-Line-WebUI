// ?ui=kit: every base component in the light and the dark theme side by side, for review and tests.
// The toggle shows one column in the chosen theme instead (remembered for the app).
// ?ui=kit-layer (KitLayer): the highline layer's page (app/c/LayerPage) on canned data, without a server:
// two cubes v2 (Slovakia and a made-up country north-west of it) and rows of the 30″ lattice made up from a few hot spots,
// cells the border cuts and partner rows beyond it (?theme=light|dark; ?pick=border selects a cut cell).

import { useState } from "preact/hooks";
import { BottomNav, Button, Chip, Chips, Field, IconButton, Panel, Progress, Range, RangePair, Screen,
         Segmented, Sheet, Stat, Stats, StatusChip, type Snap, type Theme } from "./components";
import { ICONS, Icon, Logo, type IconName } from "./icons";
import { storeTheme, storedTheme, uiHref } from "./choice";
import { DESKTOP, useMedia } from "./components";
import { ApiError, type CountryBand, type CountryCells, type CountryCube, type CountryHistogram, type CountryOutline } from "../app/api";
import { MapPage } from "../app/c/Account";
import { LayerPanel, type LayerSource } from "../app/c/LayerPage";

function Column({theme}: {theme: Theme}) {
  const [mode, setMode] = useState<"point" | "area" | "cliffs" | "file">("point");
  const [chips, setChips] = useState({clear: true, trees: false});
  const [extra, setExtra] = useState(["≤ 10 m Δh"]);
  const [length, setLength] = useState(120);
  const [span, setSpan] = useState<[number, number]>([30, 150]);
  const [nav, setNav] = useState<"search" | "searches" | "favourites">("search");
  const [snap, setSnap] = useState<Snap>("half");
  return <Screen theme={theme} screen={false} class="u-gal-col">
    <h2 class="u-h u-xl">{{auto: "System theme", light: "Light", dark: "Dark"}[theme]}</h2>

    <section class="u-gal-sec"><h3>Logo and icons</h3>
      <div class="u-row"><Logo /><Logo name={false} /></div>
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

    <section class="u-gal-sec"><h3>Segmented</h3>
      <Segmented label="Where" value={mode} onChange={setMode} options={[
        {value: "point", label: "Point", icon: "pin"}, {value: "area", label: "Area", icon: "poly"},
        {value: "cliffs", label: "Along cliffs", icon: "cliff"}, {value: "file", label: "File", icon: "file"}]} />
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

    <section class="u-gal-sec"><h3>Sheet and bottom navigation</h3>
      <div class="u-gal-stage">
        <Sheet label="Lines" snap={snap} onSnap={setSnap} peek={90}
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
      <a href={uiHref("c")}>The app</a>
    </header>
    <div class="u-gal-cols">
      {theme === "both" ? <><Column theme="light" /><Column theme="dark" /></> : <Column key={theme} theme={theme} />}
    </div>
  </Screen>;
}

// The canned highline layer of ?ui=kit-layer: two cubes v2 as /api/countries gives them (Slovakia and a made-up
// country north-west of it, their boxes apart), every dimension's edges and kinds of countcube, their neighbours (the
// other cube among them, so its partner lines are replaced as web.Countries.replaced does) and the border totals.
// The cells are those of the global 30″ lattice and its levels inside a rounded outline of the cube's bounds, of a
// made-up density around some hot spots: a cell the outline cuts gives its part inside (the outline clipped to the
// cell) and, under border=all, a partner row over its part beyond (the rectangle less that part, drawn even-odd);
// cells beyond the outline near it partner rows of their own (the neighbour by direction, or 7 where none is). The
// filters thin them by the made-up shares of each dimension's bins; the histograms split the cells' total by them.

const KIT_EDGES: CountryCube["edges"] = {
  length: [30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000], prominence: [0, 5, 10, 20, 50], wall: [0, 30, 45, 60, 90],
  clearance: [0, 2, 5, 10, 20], height: [0, 10, 20, 50, 100], water_m: [0, 5, 20, 50, 100], elevation_low: [0, 500, 1000, 1500, 2000],
  elevation_high: [0, 500, 1000, 1500, 2000], height_mean: [0, 10, 20, 50, 100], prominence_high: [0, 5, 10, 20, 50],
  drop: [0, 20, 50, 100, 200], high_pct: [0, 25, 50, 75, 90], height_diff: [0, 5, 10, 20, 50], clearance_trees: [0, 2, 5, 10, 20],
  lift_needed: [0, 0.5, 1, 1.5, 2], lift_no_zone: [0, 0.5, 1, 1.5, 2]};
const KIT_KINDS: CountryCube["kinds"] = {
  prominence: "floor", wall: "below", clearance: "floor", height: "floor", water_m: "floor", elevation_low: "floor",
  elevation_high: "below", height_mean: "floor", prominence_high: "floor", drop: "floor", high_pct: "floor", height_diff: "below",
  clearance_trees: "floor", lift_needed: "at_most", lift_no_zone: "at_most"};
/** The made-up shares of the lines per bin of each dimension (its bins, then unknown), plausible for the Tatras. */
const KIT_SHARES: Record<string, number[]> = {
  clearance: [.30, .21, .15, .10, .24, 0], height: [.25, .18, .22, .15, .20, 0], height_mean: [.38, .20, .20, .12, .10, 0],
  high_pct: [.35, .18, .17, .12, .18, 0], clearance_trees: [.22, .19, .15, .12, .32, 0], water_m: [.965, .015, .01, .006, .004, 0],
  prominence: [.43, .25, .13, .08, .09, .02], prominence_high: [.15, .20, .22, .20, .23, 0], wall: [.08, .14, .28, .48, .02, 0],
  drop: [.30, .25, .20, .15, .10, 0], elevation_low: [0, .12, .38, .35, .15, 0], elevation_high: [0, .08, .32, .38, .22, 0],
  lift_needed: [.62, .12, .09, .07, .10, 0, 0], lift_no_zone: [.55, .10, .08, .06, .06, .15, 0], height_diff: [.12, .10, .15, .25, .38, 0]};
const KIT_BANDS = (options: boolean): CountryBand[] =>
  [["S", 30, 300, 1, "formula", 60, 5000, true, 2200], ["M", 300, 1000, 2, "sag", 60, 10000, true, 560],
   ["L", 1000, 5000, 5, "sag", 45, 20000, true, 150], ["M2", 1000, 2000, 2, "sag", 60, 10000, false, 560]]
    .map(([name, lo, hi, resolution, model, slope, core, layer, tiles]) => ({
      name: name as string, lengths: [lo, hi] as [number, number], resolution: resolution as number, model: model as string,
      slope_threshold: slope as number, core_m: core as number, layer: layer as boolean, tiles: tiles as number,
      done: name === "L" ? 120 : tiles as number, seconds: 0,
      params: {max_length: hi, high_above: 20, ...(options ? {end_zone: 5, anchor_lift: 2} : {})}}));

const KIT_CUBE: CountryCube = {
  id: "slovakia", name: "Slovakia", crs: "EPSG:8353", version: 2, cell_deg: 1 / 120, levels: [1, 2, 4, 8], clusters_per_cell: 20,
  bounds_wgs84: [16.83, 47.73, 22.57, 49.61], edges: KIT_EDGES, kinds: KIT_KINDS, neighbours: ["poland", "westland", "austria"],
  bands: KIT_BANDS(true), dsm: false, water: true, partial: true,
  totals: {lines: 2.4e9, spots: 4.1e6, border: {lines: {owned: 3.1e7, partner: 2.2e7}, spots: {owned: 5.2e4, partner: 3.8e4}}},
  built: "2026-11-08T10:00:00Z",
  credits: [{data: "dem", attribution: "ÚGKK SR", licence: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/", notice: ""},
            {data: "osm", attribution: "© OpenStreetMap contributors", licence: "ODbL", url: "https://www.openstreetmap.org/copyright", notice: ""}],
  notes: ["A sample of made-up counts for the demo.",
          "Lines across the borders with Hungary and Ukraine: only where Slovakia's own data reach beyond the border (no source covers them yet).",
          "The surface model (trees, buildings) was not used: every line counts as not over trees or buildings."],
};
const KIT_CUBE_2: CountryCube = {
  ...KIT_CUBE, id: "westland", name: "Westland", crs: "EPSG:5514", bounds_wgs84: [12.1, 49.7, 16.8, 51.1], neighbours: ["slovakia"],
  bands: KIT_BANDS(false), dsm: true, partial: false,
  totals: {lines: 1.1e9, spots: 2.2e6, border: {lines: {owned: 1.2e7, partner: 0.9e7}, spots: {owned: 2.1e4, partner: 1.7e4}}},
  built: "2026-11-08T08:00:00Z",
  credits: [{data: "dem", attribution: "ČÚZK", licence: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/", notice: ""},
            {data: "osm", attribution: "© OpenStreetMap contributors", licence: "ODbL", url: "https://www.openstreetmap.org/copyright", notice: ""}],
  notes: ["A second made-up country of the demo, counted without the no-fall zone and the A-frames."],
};
export const KIT_CUBES = [KIT_CUBE, KIT_CUBE_2];

/** [lat, lon, lines per km² at the centre, radius in km] per cube. */
const HOT: Record<string, number[][]> = {
  slovakia: [[49.18, 20.08, 1.2e6, 7], [48.94, 20.38, 2e5, 9], [49.2, 19.05, 3e5, 5], [49.12, 18.55, 6e4, 3],
             [48.75, 20.05, 4e4, 6], [48.63, 20.65, 8e4, 8], [48.95, 19.6, 2e4, 10], [49.42, 20.5, 2e5, 6]],
  westland: [[50.75, 14.3, 5e5, 6], [50.55, 15.7, 2.5e5, 8], [49.95, 13.4, 9e4, 9], [50.3, 12.9, 4e4, 5],
             [50.0, 16.1, 3e4, 7], [50.85, 16.5, 1.5e5, 4]],
};
const KM_LAT = 111.32, kmLon = (lat: number) => 111.32 * Math.cos(lat * Math.PI / 180);
/** The share of each length bin (geometric, summing to 1): the cells' length filter is the sum of its bins. */
const BIN_SHARES = (() => { const w = [1, 0.9, 0.8, 0.62, 0.45, 0.22, 0.09, 0.03, 0.012]; const s = w.reduce((a, b) => a + b, 0); return w.map((x) => x / s); })();

function noise(i: number, j: number): number {
  const x = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

/** The share of the lines a dimension's limit passes (its kind's rule over KIT_SHARES; unknown passes none); a cube
 *  counted without the A-frames knows none of their values. */
function passing(cube: CountryCube, d: string, text: string | undefined): number {
  if (!text) return 1;
  const e = KIT_EDGES[d], k = e.indexOf(Number(text)), kind = KIT_KINDS[d];
  if (k < 0 || (kind === "floor" && k === 0)) return 1;
  if ((d === "lift_needed" || d === "lift_no_zone") && !cube.bands.some((b) => b.params.end_zone)) return 0;
  const shares = KIT_SHARES[d], known = kind === "at_most" ? e.length + 1 : e.length;
  const take = kind === "floor" ? shares.slice(k, known) : kind === "below" ? shares.slice(0, k) : shares.slice(0, k + 1);
  return take.reduce((s, x) => s + x, 0);
}

/** The thinning of a cube's counts by the filters; `except`: that filter left out (a histogram's own dimension). */
function kitFactor(cube: CountryCube, query: Record<string, string>, except: string = ""): number {
  let factor = 1;
  if (except !== "length") {
    const [lo, hi] = (query.length || "30-5000").split("-").map(Number);
    const a = KIT_EDGES.length.indexOf(lo), b = KIT_EDGES.length.indexOf(hi);
    factor *= BIN_SHARES.slice(a < 0 ? 0 : a, b < 0 ? 9 : b).reduce((s, x) => s + x, 0);
  }
  for (const d of Object.keys(KIT_KINDS)) if (d !== except) factor *= passing(cube, d, query[d]);
  factor *= query.water === "water" ? 0.04 : query.water === "land" ? 0.98 : 1;
  factor *= query.trees === "only" ? 0.3 : query.trees === "no" ? 0.7 : 1;
  return factor;
}

/** The level of a query over a box: Auto as the server picks it, an explicit one refused over 20000 cells. */
function kitLevel(query: Record<string, string>, cells1: number): number {
  let level = query.level === "auto" || !query.level ? 8 : Number(query.level);
  if (query.level === "auto" || !query.level) for (const l of [8, 4, 2, 1]) if (cells1 / (l * l) <= 4000) level = l;
  else if (cells1 / (level * level) > 20000) throw new ApiError("too many cells: zoom in or choose a coarser level", 400);
  return level;
}

/** The outline of a cube: a rounded polygon of its bounds, [lon, lat] rings; its normalised radius at an angle. */
const wobble = (a: number) => 0.9 + 0.08 * Math.sin(3 * a) + 0.04 * Math.cos(5 * a);
function outlineRing(cube: CountryCube): number[][] {
  const [w, s, e, n] = cube.bounds_wgs84;
  const cx = (w + e) / 2, cy = (s + n) / 2, rx = (e - w) / 2, ry = (n - s) / 2;
  const ring: number[][] = [];
  for (let k = 0; k < 72; k++) {
    const a = k * Math.PI / 36;
    ring.push([+(cx + rx * wobble(a) * Math.cos(a)).toFixed(4), +(cy + ry * wobble(a) * Math.sin(a)).toFixed(4)]);
  }
  ring.push(ring[0]);
  return ring;
}
/** How far beyond the outline a point lies, in its normalised radius (< 0 inside), and its angle. */
function beyond(cube: CountryCube, lon: number, lat: number): [number, number] {
  const [w, s, e, n] = cube.bounds_wgs84;
  const x = (lon - (w + e) / 2) / ((e - w) / 2), y = (lat - (s + n) / 2) / ((n - s) / 2);
  const a = Math.atan2(y, x);
  return [Math.hypot(x, y) - wobble(a), a];
}
/** A ring clipped to a lon/lat rectangle (Sutherland–Hodgman, the rectangle convex). */
function clipRing(ring: number[][], w: number, s: number, e: number, n: number): number[][] {
  let out = ring.slice(0, -1);
  const edges: [(p: number[]) => boolean, (a: number[], b: number[]) => number[]][] = [
    [(p) => p[0] >= w, (a, b) => [w, a[1] + (b[1] - a[1]) * (w - a[0]) / (b[0] - a[0])]],
    [(p) => p[0] <= e, (a, b) => [e, a[1] + (b[1] - a[1]) * (e - a[0]) / (b[0] - a[0])]],
    [(p) => p[1] >= s, (a, b) => [a[0] + (b[0] - a[0]) * (s - a[1]) / (b[1] - a[1]), s]],
    [(p) => p[1] <= n, (a, b) => [a[0] + (b[0] - a[0]) * (n - a[1]) / (b[1] - a[1]), n]]];
  for (const [inside, cross] of edges) {
    const input = out;
    out = [];
    for (let k = 0; k < input.length; k++) {
      const cur = input[k], prev = input[(k + input.length - 1) % input.length];
      if (inside(cur)) { if (!inside(prev)) out.push(cross(prev, cur)); out.push(cur); }
      else if (inside(prev)) out.push(cross(prev, cur));
    }
    if (!out.length) break;
  }
  return out;
}
/** A [lon, lat] ring's km² (shoelace at its latitude). */
function ringKm2(ring: number[][]): number {
  let a = 0, lat = 0;
  for (let k = 0; k < ring.length; k++) {
    const p = ring[k], q = ring[(k + 1) % ring.length];
    a += p[0] * q[1] - q[0] * p[1];
    lat += p[1] / ring.length;
  }
  return Math.abs(a) / 2 * kmLon(lat) * KM_LAT;
}
const latLon = (ring: number[][]) => ring.map(([lon, lat]) => [+lat.toFixed(6), +lon.toFixed(6)]);

/** The rows of a cube under the query (as /api/countries/<id>/cells); `factor` the filters' thinning. */
function kitCells(cube: CountryCube, query: Record<string, string>, factor = kitFactor(cube, query)): CountryCells {
  const [bw, bs, be, bn] = cube.bounds_wgs84;
  const reach = 0.08;  // degrees of the outline's surroundings holding partner rows (about the L band's 5 km)
  const [west, south, east, north] = query.bbox ? query.bbox.split(",").map(Number) : cube.bounds_wgs84;
  const w = Math.max(west, bw - reach), s = Math.max(south, bs - reach), e = Math.min(east, be + reach), n = Math.min(north, bn + reach);
  const cells1 = Math.max(0, (e - w) * 120) * Math.max(0, (n - s) * 120);
  const level = kitLevel(query, cells1);
  const deg = level / 120, i0 = Math.floor((bw - 0.2) * 15) * 8, j0 = Math.floor((bs - 0.2) * 15) * 8;
  const mode = query.mode === "spots" ? "spots" : "lines";
  const ring = outlineRing(cube);
  const replaced = new Set((cube.neighbours || []).map((id, k) => KIT_CUBES.some((c) => c.id === id) ? k + 1 : 0));
  const partnerOf = (a: number) => {  // north: the first neighbour, west: the second (south-west: the third), else none
    const p = a > Math.PI / 4 && a < 3 * Math.PI / 4 ? 1 : Math.abs(a) > 3 * Math.PI / 4 ? (a > 0 ? 2 : 3) : 7;
    return p <= (cube.neighbours || []).length || p === 7 ? p : 7;
  };
  const cells: number[][] = [], cut: CountryCells["cut"] = {};
  let total = 0, max = 0;
  const push = (row: number[]) => { cells.push(row); total += row[2]; max = Math.max(max, row[2]); };
  for (let I = Math.floor(w / deg); I * deg < e; I++) {
    for (let J = Math.floor(s / deg); J * deg < n; J++) {
      const x0 = I * deg, y0 = J * deg, x1 = x0 + deg, y1 = y0 + deg, lat = y0 + deg / 2, lon = x0 + deg / 2;
      let density = noise(I, J) < 0.25 ? 3 : 0;
      for (const [hlat, hlon, peak, r] of HOT[cube.id]) {
        const d2 = ((lat - hlat) * KM_LAT) ** 2 + ((lon - hlon) * kmLon(lat)) ** 2;
        density += peak * Math.exp(-d2 / (2 * r * r));
      }
      density *= (0.3 + 2 * noise(J, I)) * factor;
      if (mode === "spots") density = 0.3 * density ** 0.6;
      const corners = [y0, x0, y0, x1, y1, x1, y1, x0].map((v) => +v.toFixed(6));
      const i = I - i0 / level, j = J - j0 / level;
      const inside = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [lon, lat]].map(([x, y]) => beyond(cube, x, y)[0] < 0);
      const whole = ringKm2([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]);
      let inKm2 = 0;
      if (inside.every(Boolean)) inKm2 = whole;
      else if (inside.some(Boolean)) {
        const part = clipRing(ring, x0, y0, x1, y1);
        inKm2 = part.length >= 3 ? Math.min(whole, ringKm2(part)) : 0;
        if (inKm2 > 0) {
          cut[`${i},${j}`] = {km2: +inKm2.toFixed(6), shape: [[latLon(part)]]};
          if (whole - inKm2 > 1e-6) {
            cut[`${i},${j},out`] = {km2: +(whole - inKm2).toFixed(6),
                                    shape: [[latLon([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]), latLon(part)]]};
          }
        }
      }
      const own = Math.round(density * inKm2);
      if (own > 0) push([i, j, own, ...corners, 0]);
      const [far, angle] = beyond(cube, lon, lat);
      const partner = partnerOf(angle);
      if (query.border !== "own" && !replaced.has(partner) && whole - inKm2 > 1e-6 && far < reach / ((be - bw) / 2)) {
        const count = Math.round(density * (whole - inKm2) * 0.3 * Math.exp(-Math.max(0, far) * 40));
        if (count > 0) push([i, j, count, ...corners, partner]);
      }
    }
  }
  return {level, cell_deg: deg, total, max, cells, cut};
}

/** The histogram of a cube under the query (as /histogram): each dimension under every other filter but its own,
 *  the rows' total split by the shares; spots' length bins summing to about 1.4 × the total; both modes' totals and
 *  the lines' border split. */
function kitHistogram(cube: CountryCube, query: Record<string, string>): CountryHistogram {
  const cells = kitCells(cube, query);
  const spots = query.mode === "spots";
  const totalOf = (except: string) => kitCells(cube, query, kitFactor(cube, query, except)).total;
  const t0 = totalOf("length");
  const out: Record<string, unknown> = {level: cells.level, cell_deg: cells.cell_deg, total: cells.total,
    length: BIN_SHARES.map((share) => Math.round(t0 * share * (spots ? 1.4 : 1)))};
  for (const d of Object.keys(KIT_KINDS)) {
    const t = totalOf(d), shares = KIT_SHARES[d];
    const unknownAll = (d === "lift_needed" || d === "lift_no_zone") && !cube.bands.some((b) => b.params.end_zone);
    out[d] = unknownAll ? [...shares.slice(0, -1).map(() => 0), t] : shares.map((x) => Math.round(t * x));
  }
  const lines = spots ? kitCells(cube, {...query, mode: "lines"}) : cells;
  const own = lines.cells.filter((r) => !r[11]).reduce((s, r) => s + r[2], 0);
  const partner = lines.total - own;
  out.totals = {lines: lines.total, spots: spots ? cells.total : kitCells(cube, {...query, mode: "spots"}).total};
  out.border = {interior: Math.round(own * 0.96), owned: own - Math.round(own * 0.96), partner};
  return out as unknown as CountryHistogram;
}

/** The outline of a cube for the map (as /outline), with its km². */
function kitOutline(cube: CountryCube): CountryOutline {
  const ring = outlineRing(cube);
  return {tolerance: 0.01, area_km2: Math.round(ringKm2(ring)), geometry: {type: "Polygon", coordinates: [ring]}};
}

const answer = <T,>(make: () => T) => new Promise<T>((resolve, reject) => { try { resolve(make()); } catch (e) { reject(e); } });
const cubeOf = (id: string) => { const c = KIT_CUBES.find((k) => k.id === id); if (!c) throw new ApiError("no such country", 404); return c; };
export const KIT_SOURCE: LayerSource = {
  countries: () => Promise.resolve({countries: KIT_CUBES}),
  cells: (id, query) => answer(() => kitCells(cubeOf(id), query)),
  histogram: (id, query) => answer(() => kitHistogram(cubeOf(id), query)),
  outline: (id) => answer(() => kitOutline(cubeOf(id))),
};

/** The densest row of the first answer, selected for the review's screenshots (?pick=border: the densest of the
 *  rows of a cell the border cuts). */
const densest = (data: CountryCells) => {
  const border = new URLSearchParams(location.search).get("pick") === "border";
  const rows = border ? data.cells.filter((r) => !r[11] && data.cut[`${r[0]},${r[1]}`]) : data.cells;
  return rows.reduce<number[] | null>((best, row) => !best || row[2] > best[2] ? row : best, null);
};

export function KitLayer() {
  const asked = new URLSearchParams(location.search).get("theme");
  const theme: Theme = asked === "light" || asked === "dark" ? asked : storedTheme();
  const wide = useMedia(DESKTOP);
  return <Screen theme={theme} class={`u-app-c c-app ${wide ? "c-wide" : "c-narrow"}`}>
    <main class="c-main c-main-layer">
      <MapPage title="Highline layer" aside="Counts in view">{(place, aside, extras) =>
        <LayerPanel place={place} aside={aside} source={KIT_SOURCE} params={new URLSearchParams(location.hash.replace(/^#/, ""))}
                    pick={densest} extras={extras} />}</MapPage>
    </main>
  </Screen>;
}
