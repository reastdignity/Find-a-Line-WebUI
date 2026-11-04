// ?ui=kit: every base component in the light and the dark theme side by side, for review and tests.
// The toggle shows one column in the chosen theme instead (remembered for the app).
// ?ui=kit-layer (KitLayer): the highline layer's page (app/c/LayerPage) on canned data, without a server:
// a cube of Slovakia and cells made up from a few hot spots (?theme=light|dark).

import { useState } from "preact/hooks";
import { BottomNav, Button, Chip, Chips, Field, IconButton, Panel, Progress, Range, RangePair, Screen,
         Segmented, Sheet, Stat, Stats, StatusChip, type Snap, type Theme } from "./components";
import { ICONS, Icon, Logo, type IconName } from "./icons";
import { storeTheme, storedTheme, uiHref } from "./choice";
import { DESKTOP, useMedia } from "./components";
import { ApiError, type CountryCells, type CountryCube } from "../app/api";
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

// The canned highline layer of ?ui=kit-layer: cube.json as /api/countries gives it, and cells of a made-up
// density around some Slovak ranges, in cells of a plain degree grid (the server's are cells of the
// country's CRS); the filters thin them by rough factors.

const KIT_CUBE: CountryCube = {
  id: "slovakia", name: "Slovakia", crs: "EPSG:8353", cell_m: 1000, levels: [1, 2, 4, 8], cluster_m: 50,
  bounds_wgs84: [16.83, 47.73, 22.57, 49.61],
  edges: {length: [30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000], prominence: [0, 5, 10, 20, 50],
          wall: [0, 30, 45, 60, 90], clearance: [0, 2, 5, 10, 20], height: [0, 10, 20, 50, 100]},
  bands: [["S", 30, 300, 1, "formula", 60, 5000, true, 2200], ["M", 300, 1000, 2, "sag", 60, 10000, true, 560],
          ["L", 1000, 5000, 5, "sag", 45, 20000, true, 150], ["M2", 1000, 2000, 2, "sag", 60, 10000, false, 560]]
    .map(([name, lo, hi, resolution, model, slope, core, layer, tiles]) => ({
      name: name as string, lengths: [lo, hi] as [number, number], resolution: resolution as number, model: model as string,
      slope_threshold: slope as number, core_m: core as number, layer: layer as boolean, tiles: tiles as number,
      done: name === "L" ? 120 : tiles as number, seconds: 0, params: {}})),
  dsm: false, water: true, partial: true, totals: {lines: 2.4e9, spots: 4.1e6}, built: "2026-11-03T10:00:00Z",
  credits: [{data: "dem", attribution: "ÚGKK SR", licence: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/", notice: ""},
            {data: "osm", attribution: "© OpenStreetMap contributors", licence: "ODbL", url: "https://www.openstreetmap.org/copyright", notice: ""}],
  notes: ["A sample of made-up counts for the demo."],
};

/** [lat, lon, lines per km² at the centre, radius in km] */
const HOT = [[49.18, 20.08, 1.2e6, 7], [48.94, 20.38, 2e5, 9], [49.2, 19.05, 3e5, 5], [49.12, 18.55, 6e4, 3],
             [48.75, 20.05, 4e4, 6], [48.63, 20.65, 8e4, 8], [48.95, 19.6, 2e4, 10]];
const KIT_LAT0 = 47.7, KIT_LON0 = 16.8, KM_LAT = 111.32, KM_LON = 111.32 * Math.cos(48.7 * Math.PI / 180);

function noise(i: number, j: number): number {
  const x = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function kitCells(query: Record<string, string>): CountryCells {
  const [west, south, east, north] = query.bbox.split(",").map(Number);
  const [bw, bs, be, bn] = KIT_CUBE.bounds_wgs84;
  const w = Math.max(west, bw), s = Math.max(south, bs), e = Math.min(east, be), n = Math.min(north, bn);
  const km2 = Math.max(0, e - w) * KM_LON * Math.max(0, n - s) * KM_LAT;
  let level = query.level === "auto" ? 8 : Number(query.level);
  if (query.level === "auto") for (const l of [8, 4, 2, 1]) if (km2 / (l * l) <= 4000) level = l;
  else if (km2 / (level * level) > 20000) throw new ApiError("too many cells: zoom in or choose a coarser level", 400);
  const dlat = level / KM_LAT, dlon = level / KM_LON;
  const [lo, hi] = (query.length || "30-5000").split("-").map(Number);
  const mode = query.mode === "spots" ? "spots" : "lines";
  let factor = Math.min(1, (Math.log(hi) - Math.log(lo)) / Math.log(5000 / 30) * 1.2);
  factor *= 0.55 ** KIT_CUBE.edges.prominence.indexOf(Number(query.prominence || 0));
  factor *= 0.7 ** KIT_CUBE.edges.clearance.indexOf(Number(query.clearance || 0));
  factor *= 0.7 ** KIT_CUBE.edges.height.indexOf(Number(query.height || 0));
  if (query.wall) factor *= 0.25 * KIT_CUBE.edges.wall.indexOf(Number(query.wall));
  factor *= query.water === "water" ? 0.04 : query.water === "land" ? 0.98 : 1;
  const cells: number[][] = [];
  let total = 0, max = 0;
  for (let i = Math.floor((w - KIT_LON0) / dlon); KIT_LON0 + i * dlon < e; i++) {
    for (let j = Math.floor((s - KIT_LAT0) / dlat); KIT_LAT0 + j * dlat < n; j++) {
      const lat = KIT_LAT0 + (j + 0.5) * dlat, lon = KIT_LON0 + (i + 0.5) * dlon;
      let density = noise(i, j) < 0.25 ? 3 : 0;
      for (const [hlat, hlon, peak, r] of HOT) {
        const d2 = ((lat - hlat) * KM_LAT) ** 2 + ((lon - hlon) * KM_LON) ** 2;
        density += peak * Math.exp(-d2 / (2 * r * r));
      }
      density *= 0.3 + 2 * noise(j, i) * factor;
      if (mode === "spots") density = 0.3 * density ** 0.6;
      const count = Math.round(density * level * level);
      if (count <= 0) continue;
      const y0 = KIT_LAT0 + j * dlat, x0 = KIT_LON0 + i * dlon;
      cells.push([i, j, count, y0, x0, y0, x0 + dlon, y0 + dlat, x0 + dlon, y0 + dlat, x0].map((v, k) => k < 3 ? v : +v.toFixed(6)));
      total += count;
      max = Math.max(max, count);
    }
  }
  return {level, cell_m: level * 1000, total, max, cells};
}

const KIT_SOURCE: LayerSource = {
  countries: () => Promise.resolve({countries: [KIT_CUBE]}),
  cells: (_id, query) => new Promise((resolve, reject) => {
    try { resolve(kitCells(query)); } catch (e) { reject(e); }
  }),
};

/** The densest cell of the first answer, selected for the review's screenshots. */
const densest = (data: CountryCells) => data.cells.reduce<number[] | null>((best, row) => !best || row[2] > best[2] ? row : best, null);

export function KitLayer() {
  const asked = new URLSearchParams(location.search).get("theme");
  const theme: Theme = asked === "light" || asked === "dark" ? asked : storedTheme();
  const wide = useMedia(DESKTOP);
  return <Screen theme={theme} class={`u-app-c c-app ${wide ? "c-wide" : "c-narrow"}`}>
    <main class="c-main c-main-layer">
      <MapPage title="Highline layer">{(place) =>
        <LayerPanel place={place} source={KIT_SOURCE} country={null} onCountry={() => {}} pick={densest} />}</MapPage>
    </main>
  </Screen>;
}
