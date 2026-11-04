// The right panel of the highline layer (LayerPage.tsx): the counts in view per bin of each dimension of the
// cube, from /api/countries/<id>/histogram summed over the cubes in view. Each histogram is a row of buttons:
// a bar's height is log10(1 + count) over log10(1 + the largest), the count above it, the bins inside the
// current filter pressed. The length histogram sets the range (a click one bin, shift-click extends the range to
// it); the four small ones set a threshold (prominence, clearance, height: the bin's lower edge; the wall: the
// bin's upper edge, the last bin "any"); the unknown bin ("?") cannot be picked.

import type { ComponentChildren } from "preact";
import type { CountryCube } from "../api";
import { t } from "../../i18n";
import { short, type LayerMode } from "./cellsLayer";
import type { LayerState } from "./layerState";

/** The histograms of the cubes in view summed elementwise (web.py's CountryHistogram without its level). */
export interface SummedHistogram { total: number; length: number[]; prominence: number[]; wall: number[]; clearance: number[]; height: number[] }
export const DIMENSIONS = ["prominence", "wall", "clearance", "height"] as const;
export type Dimension = typeof DIMENSIONS[number];

export function emptyHistogram(): SummedHistogram {
  return {total: 0, length: Array(9).fill(0), prominence: Array(6).fill(0), wall: Array(6).fill(0),
          clearance: Array(6).fill(0), height: Array(6).fill(0)};
}

/** `into` plus `more`, bin by bin. */
export function addHistogram(into: SummedHistogram, more: SummedHistogram) {
  into.total += more.total;
  for (const key of ["length", ...DIMENSIONS] as const) {
    const bins = more[key] || [];
    for (let k = 0; k < into[key].length; k++) into[key][k] += bins[k] || 0;
  }
}

interface Bar { value: number; label: string; pressed: boolean; pickable: boolean; title: string }

/** One histogram: `title`, the bars (a button each when pickable), `axis` the labels under the bars (one per bar,
 *  or one more for the bins' edges), `onPick(k, shift)`. */
export function Histogram({title, bars, axis, small, onPick, children}:
                          {title: string; bars: Bar[]; axis: string[]; small?: boolean;
                           onPick(k: number, shift: boolean): void; children?: ComponentChildren}) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const height = (v: number) => `${Math.round(100 * Math.log10(1 + v) / Math.log10(1 + max))}%`;
  const edges = axis.length === bars.length + 1;
  return <section class={`c-layer-hist${small ? " c-layer-hist-small" : ""}`} aria-label={title}>
    <h3 class="c-layer-hist-title">{title}</h3>
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
      {axis.map((text, k) => <span key={k}>{text}</span>)}
    </div>
    {children}
  </section>;
}

const TITLES: Record<Dimension, () => string> = {
  prominence: () => t("ui.layer.hist.prominence"), wall: () => t("ui.layer.hist.wall"),
  clearance: () => t("ui.layer.hist.clearance"), height: () => t("ui.layer.hist.height")};

/** A length edge for the axis: 1000 → "1 k". */
const edgeText = (m: number) => m >= 1000 ? `${+(m / 1000).toFixed(1)} k` : String(m);

export function LayerHistograms({cube, state, hist, status, error, countries, onLength, onThreshold}:
                                {cube: CountryCube; state: LayerState; hist: SummedHistogram | null;
                                 status: "waiting" | "ready" | "error"; error: string; countries: number;
                                 onLength(lo: number, hi: number, extend: boolean): void;
                                 onThreshold(dimension: Dimension, value: number | null): void}) {
  const edges = cube.edges;
  const mode: LayerMode = state.mode;
  const noun = mode === "lines" ? t("ui.layer.lines") : t("ui.layer.spots");
  const h = hist || emptyHistogram();
  const lo = edges.length.indexOf(state.length[0]), hi = edges.length.indexOf(state.length[1]);
  const lengthBars: Bar[] = h.length.map((value, k) => ({
    value, label: "", pressed: k >= lo && k < hi, pickable: true,
    title: t("ui.layer.hist.length_bin", {from: edges.length[k], to: edges.length[k + 1], n: value.toLocaleString("en"), noun})}));
  const bars = (dimension: Dimension): Bar[] => {
    const e = edges[dimension];
    return h[dimension].map((value, k) => {
      const unknown = k >= e.length;
      let pressed: boolean, title: string;
      if (dimension === "wall") {
        const limit = state.wall === null ? e.length : e.indexOf(state.wall);
        pressed = !unknown && k < limit;
        title = unknown ? t("ui.layer.hist.unknown") : k === e.length - 1 ? t("ui.layer.hist.wall_from", {from: e[k]})
          : t("ui.layer.hist.wall_bin", {from: e[k], to: e[k + 1]});
      } else {
        const threshold = e.indexOf(state[dimension]);
        pressed = !unknown && k >= threshold;
        title = unknown ? t("ui.layer.hist.unknown") : k === e.length - 1 ? t("ui.layer.hist.from", {from: e[k]})
          : t("ui.layer.hist.bin", {from: e[k], to: e[k + 1]});
      }
      return {value, label: "", pressed, pickable: !unknown, title: `${title}: ${value.toLocaleString("en")} ${noun}`};
    });
  };
  const axisOf = (dimension: Dimension): string[] => {
    const e = edges[dimension];
    // compact: a small histogram's bar is about 22 px wide (the bars' titles say it in full)
    const labels = dimension === "wall" ? e.slice(1).map((v) => `<${v}`).concat(t("ui.layer.any")) : e.map((v) => `≥${v}`);
    return [...labels.slice(0, h[dimension].length - 1), "?"];
  };
  const pick = (dimension: Dimension) => (k: number) => {
    const e = edges[dimension];
    if (dimension === "wall") onThreshold("wall", k >= e.length - 1 ? null : e[k + 1]);
    else onThreshold(dimension, e[k]);
  };

  // While a round counts, the last answer stays, dimmed (a pan does not blank the panel)
  return <div class={`c-layer-right${status === "waiting" ? " c-layer-waiting" : ""}`}>
    <section class="c-layer-inview" aria-live="polite">
      <h2 class="c-layer-hist-title">{t("ui.layer.in_view")}</h2>
      {status !== "error" && hist
        ? <div class="c-layer-stat"><span class="c-layer-stat-n" title={hist.total.toLocaleString("en")}>{short(hist.total)}</span>
            <span class="c-layer-stat-u">{noun}{mode === "spots" ? ` · ${t("ui.layer.upper_bound")}` : ""}
              {countries > 1 ? ` · ${t("ui.layer.countries", {count: countries})}` : ""}</span></div>
        : status === "error" ? <p class="c-error u-small" role="alert">{t("ui.layer.hist.failed")} {error}</p>
        : <p class="u-small">{t("ui.layer.counting")}</p>}
    </section>
    <Histogram title={t("ui.layer.hist.by_length")} bars={lengthBars} axis={edges.length.map(edgeText)}
               onPick={(k, shift) => onLength(edges.length[k], edges.length[k + 1], shift)}>
      <p class="u-small c-layer-note">{t("ui.layer.hist.length_note")}{mode === "spots" ? ` ${t("ui.layer.hist.spots_note")}` : ""}</p>
    </Histogram>
    <div class="c-layer-smalls">
      {DIMENSIONS.map((d) => <Histogram key={d} small title={TITLES[d]()} bars={bars(d)} axis={axisOf(d)} onPick={pick(d)} />)}
    </div>
    <p class="u-small c-layer-note">{t("ui.layer.hist.dimensions_note")}</p>
  </div>;
}
