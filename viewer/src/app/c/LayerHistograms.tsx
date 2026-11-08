// The right panel of the highline layer (LayerPage.tsx): the counts in view per bin of each dimension of the cube
// (cube.json's edges and kinds: the length and fifteen more), from /api/countries/<id>/histogram summed over the
// cubes in view, in three topics (layerState.ts TOPICS: The line, Anchors and terrain, Rigging; the length chart
// leads). Each histogram is a row of buttons: a bar's height is log10(1 + count) over log10(1 + the largest), the
// count above it, the bins inside the current limit pressed. The length histogram sets the range (a click one bin,
// shift-click extends the range to it); the others set a limit by their kind (a floor: the bin's lower edge; a
// "below": the bin's upper edge, the last bin "any"; an at_most: the bin's upper edge, the last bin "any"); the
// unknown bin ("?") cannot be picked. The chart of the dimension changed last (`open`) is ringed on a desktop, where
// the charts stand two a row while the panel holds two of 220 px (a container query, c.css), and scrolled into view;
// on phones each topic is a swiped strip of small charts and that chart is enlarged in place (its strip scrolls to
// it, the column does not move; a tap on a chart's title enlarges it).

import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef } from "preact/hooks";
import { binsOf, type CountryCube, type CountryHistogram, type DimensionKind } from "../api";
import { t } from "../../i18n";
import { short, type LayerMode } from "./cellsLayer";
import { dimensions, topicsOf, type LayerState } from "./layerState";

/** The histograms of the cubes in view summed elementwise (web.py's CountryHistogram without its level): the
 *  total, both modes' totals, the lines' border split and the bins of each dimension. */
export interface SummedHistogram {
  total: number;
  totals: {lines: number; spots: number} | null;
  border: {interior: number; owned: number; partner: number} | null;
  bins: Record<string, number[]>;
}

/** The number of bins of a dimension and its unknown bin: the length's 9, an at_most's edges + 2, else edges + 1. */
export function binCount(cube: CountryCube, dimension: string): number {
  if (dimension === "length") return cube.edges.length.length - 1;
  return cube.edges[dimension].length + (cube.kinds[dimension] === "at_most" ? 2 : 1);
}

export function emptyHistogram(cube: CountryCube): SummedHistogram {
  const bins: Record<string, number[]> = {length: Array(binCount(cube, "length")).fill(0)};
  for (const [d] of dimensions(cube)) bins[d] = Array(binCount(cube, d)).fill(0);
  return {total: 0, totals: null, border: null, bins};
}

/** `into` plus an answer, bin by bin (a dimension the answer lacks adds nothing). */
export function addHistogram(into: SummedHistogram, more: CountryHistogram) {
  into.total += more.total;
  if (more.totals) {
    into.totals = {lines: (into.totals?.lines || 0) + more.totals.lines, spots: (into.totals?.spots || 0) + more.totals.spots};
  }
  if (more.border) {
    const b = into.border || {interior: 0, owned: 0, partner: 0};
    into.border = {interior: b.interior + more.border.interior, owned: b.owned + more.border.owned, partner: b.partner + more.border.partner};
  }
  for (const [key, bins] of Object.entries(into.bins)) {
    const add = binsOf(more, key);
    for (let k = 0; k < bins.length; k++) bins[k] += add[k] || 0;
  }
}

/** The unit of a dimension's values. */
export const unitOf = (dimension: string): string => dimension === "wall" ? "°" : dimension === "high_pct" ? "%" : "m";
const withUnit = (v: number, dimension: string) => unitOf(dimension) === "m" ? `${v} m` : `${v}${unitOf(dimension)}`;

/** What the texts of the dimensions need of the cubes in view: the "high" share's threshold (the bands' high_above,
 *  20 m by default) and the no-fall zone (the bands' end_zone, none without the options). */
export interface DimensionContext { high: number; zone: number | null }

export function dimensionContext(cubes: CountryCube[]): DimensionContext {
  const params = cubes.flatMap((c) => c.bands.filter((b) => b.layer).map((b) => b.params || {}));
  const high = params.map((p) => Number(p.high_above)).find((v) => Number.isFinite(v) && v > 0) ?? 20;
  const zone = params.map((p) => Number(p.end_zone)).find((v) => Number.isFinite(v) && v > 0) ?? null;
  return {high, zone};
}

/** A text of the catalogue, or `fallback` where it has none (a dimension of a newer cube). */
function text(key: string, fallback: string, values?: Record<string, unknown>): string {
  const found = t(key, values);
  return found === key ? fallback : found;
}

/** A dimension's label in the filters (its long name), its short one (a chip), its chart's title. */
export function dimensionLabel(dimension: string, ctx: DimensionContext): string {
  if (dimension === "lift_needed" && ctx.zone !== null) return t("ui.layer.dim.lift_needed.label_zone", {zone: ctx.zone});
  return text(`ui.layer.dim.${dimension}.label`, dimension, {high: ctx.high});
}
export function dimensionShort(dimension: string, ctx: DimensionContext): string {
  return text(`ui.layer.dim.${dimension}.short`, dimensionLabel(dimension, ctx), {high: ctx.high});
}
export function dimensionTitle(dimension: string, ctx: DimensionContext): string {
  return text(`ui.layer.dim.${dimension}.title`, dimension, {high: ctx.high});
}

/** A limit as text: "≥ 5 m", "< 45°", "None needed", "≤ 1 m", "Any". */
export function limitText(kind: DimensionKind, dimension: string, value: number | null, on: boolean): string {
  if (!on || value === null) return t("ui.layer.any");
  if (kind === "floor") return `≥ ${withUnit(value, dimension)}`;
  if (kind === "below") return `< ${withUnit(value, dimension)}`;
  return value === 0 ? t("ui.layer.none_needed") : `≤ ${withUnit(value, dimension)}`;
}

interface Bar { value: number; pressed: boolean; pickable: boolean; title: string }

/** One histogram: `title` (on phones a button enlarging it), the bars (a button each when pickable), `axis` the
 *  labels under the bars (one per bar, or one more for the bins' edges), `onPick(k, shift)`. */
export function Histogram({name, title, bars, axis, open, wide, onPick, onTitle, children}:
                          {name: string; title: string; bars: Bar[]; axis: string[]; open: boolean; wide: boolean;
                           onPick(k: number, shift: boolean): void; onTitle(): void; children?: ComponentChildren}) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const height = (v: number) => `${Math.round(100 * Math.log10(1 + v) / Math.log10(1 + max))}%`;
  const edges = axis.length === bars.length + 1;
  return <section class={`c-layer-hist${open ? " c-layer-hist-open" : ""}`} data-hist={name} aria-label={title}>
    <h3 class="c-layer-hist-title">{wide ? title
      : <button type="button" class="c-layer-hist-name" aria-expanded={open} title={title} onClick={onTitle}>{title}</button>}</h3>
    <div class="c-layer-hist-bars" role="group" aria-label={title}>
      {bars.map((b, k) => {
        const fill = <span class="c-layer-bar-fill" style={{height: height(b.value)}} aria-hidden="true" />;
        const count = <span class="c-layer-bar-n">{b.value > 0 ? short(b.value).replace(" ", "") : ""}</span>;
        return b.pickable
          ? <button key={k} type="button" class={`c-layer-bar${b.pressed ? " u-on" : ""}`} data-value={b.value}
                    aria-pressed={b.pressed} title={b.title} onClick={(e) => onPick(k, e.shiftKey)}>{count}{fill}</button>
          : <span key={k} class="c-layer-bar c-layer-bar-off" data-value={b.value} title={b.title}>{count}{fill}</span>;
      })}
    </div>
    <div class={`c-layer-hist-axis${edges ? " c-layer-hist-edges" : ""}`} aria-hidden="true">
      {axis.map((label, k) => <span key={k}>{label}</span>)}
    </div>
    {children}
  </section>;
}

/** A length edge for the axis: 1000 → "1 k". */
const edgeText = (m: number) => m >= 1000 ? `${+(m / 1000).toFixed(1)} k` : String(m);
/** A dimension's edge for the axis (compact). */
const axisEdge = (v: number) => v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : String(v);

/** The open chart: the dimension changed last (the elevation pair: both of its charts). */
const isOpen = (open: string | null, dimension: string) =>
  !!open && (open === dimension || (open === "elevation" && dimension.startsWith("elevation_")));

export function LayerHistograms({cube, state, hist, status, error, countries, ctx, open, wide, border, onLength, onLimit, onOpen}:
                                {cube: CountryCube; state: LayerState; hist: SummedHistogram | null;
                                 status: "waiting" | "ready" | "error"; error: string; countries: number; ctx: DimensionContext;
                                 open: string | null; wide: boolean; border: boolean;
                                 onLength(lo: number, hi: number, extend: boolean): void;
                                 onLimit(dimension: string, value: number | null): void; onOpen(dimension: string | null): void}) {
  const edges = cube.edges;
  const mode: LayerMode = state.mode;
  const noun = mode === "lines" ? t("ui.layer.lines") : t("ui.layer.spots");
  const h = hist || emptyHistogram(cube);
  const binsFor = (d: string) => h.bins[d] || Array(binCount(cube, d)).fill(0);
  const root = useRef<HTMLDivElement>(null);
  const lo = edges.length.indexOf(state.length[0]), hi = edges.length.indexOf(state.length[1]);
  const n = (value: number) => `${value.toLocaleString("en")} ${noun}`;

  const lengthBars: Bar[] = binsFor("length").map((value, k) => ({
    value, pressed: k >= lo && k < hi, pickable: true,
    title: t("ui.layer.hist.length_bin", {from: edges.length[k], to: edges.length[k + 1], n: value.toLocaleString("en"), noun})}));
  const bars = (d: string): Bar[] => {
    const e = edges[d], kind = cube.kinds[d], value = state.limits[d] ?? null, u = (v: number) => withUnit(v, d);
    const known = kind === "at_most" ? e.length + 1 : e.length;
    return binsFor(d).map((count, k) => {
      const unknown = k >= known;
      let pressed: boolean, title: string;
      if (kind === "floor") {
        pressed = !unknown && k >= e.indexOf(value ?? e[0]);
        title = k === e.length - 1 ? `≥ ${u(e[k])}` : `${e[k]}–${u(e[k + 1])}`;
      } else if (kind === "below") {
        const limit = value === null || (d !== "wall" && value === e[0]) ? e.length : e.indexOf(value);
        pressed = !unknown && k < limit;
        title = k === e.length - 1 ? `≥ ${u(e[k])}` : `${e[k]}–${u(e[k + 1])}`;
      } else {
        pressed = !unknown && (value === null || k <= e.indexOf(value));
        title = k === 0 ? (e[0] === 0 ? t("ui.layer.none_needed") : `≤ ${u(e[0])}`) : k === e.length ? `> ${u(e[k - 1])}`
          : `${e[k - 1]}–${u(e[k])}`;
      }
      if (unknown) title = t("ui.layer.hist.unknown");
      return {value: count, pressed, pickable: !unknown, title: `${title}: ${n(count)}`};
    });
  };
  const axisOf = (d: string): string[] => {
    const e = edges[d], kind = cube.kinds[d];
    if (kind === "floor") return [...e.map((v) => `≥${axisEdge(v)}`), "?"];
    if (kind === "below") return [...e.slice(1).map((v) => `<${axisEdge(v)}`), t("ui.layer.any"), "?"];
    return [e[0] === 0 ? t("ui.layer.hist.none") : `≤${axisEdge(e[0])}`, ...e.slice(1).map((v) => `≤${axisEdge(v)}`),
            `>${axisEdge(e[e.length - 1])}`, "?"];
  };
  const pick = (d: string) => (k: number) => {
    const e = edges[d], kind = cube.kinds[d];
    if (kind === "floor") onLimit(d, e[k]);
    else if (kind === "below") onLimit(d, k >= e.length - 1 ? null : e[k + 1]);
    else onLimit(d, k >= e.length ? null : e[k]);
  };
  const openKey = (d: string) => d.startsWith("elevation_") ? "elevation" : d;

  // A new open chart: ringed and scrolled into view in the desktop's panel; on phones its strip scrolled to it (the
  // column stays where it is). Not at the first render.
  const shownOpen = useRef(open);
  useLayoutEffect(() => {
    if (shownOpen.current === open) return;
    shownOpen.current = open;
    const chart = root.current?.querySelector<HTMLElement>(".c-layer-hist-open");
    if (!chart) return;
    if (wide) {
      const panel = chart.closest<HTMLElement>(".c-col-scroll");
      if (!panel) return;
      const top = chart.getBoundingClientRect().top - panel.getBoundingClientRect().top;
      if (top < 0 || top + chart.offsetHeight > panel.clientHeight) panel.scrollTop += top - 40;
    } else {
      const strip = chart.closest<HTMLElement>(".c-layer-charts");
      if (strip) strip.scrollLeft += chart.getBoundingClientRect().left - strip.getBoundingClientRect().left - 16;
    }
  });
  useEffect(() => { shownOpen.current = open; }, []);

  const chart = (d: string) => {
    const title = d === "length" ? t("ui.layer.hist.by_length") : dimensionTitle(d, ctx);
    const props = {name: d, title, open: isOpen(open, d), wide, onTitle: () => onOpen(isOpen(open, d) ? null : openKey(d))};
    if (d === "length") {
      return <Histogram key={d} {...props} bars={lengthBars} axis={edges.length.map(edgeText)}
                        onPick={(k, shift) => onLength(edges.length[k], edges.length[k + 1], shift)}>
        {wide && <p class="u-small c-layer-note">{t("ui.layer.hist.length_note")}{mode === "spots" ? ` ${t("ui.layer.hist.spots_note")}` : ""}</p>}
      </Histogram>;
    }
    return <Histogram key={d} {...props} bars={bars(d)} axis={axisOf(d)} onPick={pick(d)} />;
  };

  const other = mode === "lines" ? h.totals?.spots : h.totals?.lines;
  const cross = h.border ? h.border.owned + h.border.partner : null;
  // While a round counts, the last answer stays, dimmed (a pan does not blank the panel)
  return <div ref={root} class={`c-layer-right${status === "waiting" ? " c-layer-waiting" : ""}`}>
    <section class="c-layer-inview" aria-live="polite">
      <h2 class="c-layer-hist-title">{t("ui.layer.in_view")}</h2>
      {status !== "error" && hist
        ? <>
            <div class="c-layer-stat"><span class="c-layer-stat-n" title={hist.total.toLocaleString("en")}>{short(hist.total)}</span>
              <span class="c-layer-stat-u">{noun}{mode === "spots" ? ` · ${t("ui.layer.upper_bound")}` : ""}
                {countries > 1 ? ` · ${t("ui.layer.countries", {count: countries})}` : ""}</span></div>
            {other !== undefined && <div class="c-layer-inview-more">
              <b>{short(other)}</b> {mode === "lines" ? t("ui.layer.spots") : t("ui.layer.lines")}
              {border && cross !== null && <> · <b>{short(cross)}</b> {t("ui.layer.lines_across")}</>}</div>}
          </>
        : status === "error" ? <p class="c-error u-small" role="alert">{t("ui.layer.hist.failed")} {error}</p>
        : <p class="u-small">{t("ui.layer.counting")}</p>}
    </section>
    {topicsOf(cube).map((topic) => <section key={topic.id} class="c-layer-topic" aria-label={t(`ui.layer.topic.${topic.id}`)}>
      <h2 class="c-layer-topic-name">{t(`ui.layer.topic.${topic.id}`)}</h2>
      <div class="c-layer-charts">{topic.charts.map(chart)}</div>
    </section>)}
    <p class="u-small c-layer-note">{wide ? t("ui.layer.hist.dimensions_note") : t("ui.layer.hist.strip_note")}</p>
  </div>;
}
