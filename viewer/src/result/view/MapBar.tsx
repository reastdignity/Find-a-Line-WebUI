// The result view's bar on the map (docs/line-volume/spec-view.md B.2 items 1, 3, 5-8; spec-search.md 3.9): at
// the top the switch Auto / Area / Spots / Lines with "Best" 10 / 30 / 100 / All; at the bottom the line that says
// what is drawn (with "Held by you." and "Back to Auto" while a level is held; marked when the lines are too many
// to draw), beside it the frame's hint, and the legend: exactly the shapes and colours on the map now (SpotMap's
// legend()), at Area the squares' value (a select) and its five classes, and in a run with the access mark the
// three marks with their "?". On a phone the legend is two lines of short labels with a fold (not kept: it starts
// unfolded). The bar's boxes carry `data-map-control`: the canvas places no number under them. Styles in
// mapbar.css (classes v-*).

import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import { AccessMark, ACCESS_STATES, accessWord, useAccessHelp } from "../../access";
import { t } from "../../i18n";
import { COLORS } from "../../style";
import { Icon } from "../../ui/icons";
import type { Legend, MarkKind, SpotMap } from "../SpotMap";
import type { Best, SpotView } from "../spots";
import { FAN_HERE, type Level, type SquareBy } from "../viewgeom";
import { count, cx, Swatch } from "./common";
import "./mapbar.css";

const LEVELS: (Level | "auto")[] = ["auto", "area", "spots", "lines"];
const BESTS: Best[] = [10, 30, 100, "all"];
const BYS: SquareBy[] = ["spots", "lines", "clr", "len"];

/** The line that says what the map draws now, and whether it is the refusal of too many lines. */
export function statusOf(view: SpotView): {text: string; refused: boolean} {
  const v = view.inView, level = view.level, all = view.best === "all";
  if (level === "area") return {text: t(view.auto ? "ui.view.map.status_area" : "ui.view.map.status_area_held"), refused: false};
  if (!v.m) return {text: t("ui.view.map.status_empty"), refused: false};
  if (v.refused) {
    const lower = all ? 100 : view.best === 100 ? 30 : view.best === 30 ? 10 : 0;
    return {text: lower ? t("ui.view.map.status_refused", {n: count(v.refused), lower}) : t("ui.view.map.status_refused_10", {n: count(v.refused)}),
            refused: true};
  }
  if (level === "spots") {
    return {text: all ? t("ui.view.map.status_spots_all", {m: count(v.m)})
      : t("ui.view.map.status_spots", {n: v.best.length, m: count(v.m)}), refused: false};
  }
  return {text: all ? t("ui.view.map.status_lines_all", {n: count(v.strokes)})
    : t("ui.view.map.status_lines", {n: v.best.length, m: count(v.m)}), refused: false};
}

const SHAPES: Record<MarkKind, string> = {
  B: "M6 2h28a4 4 0 0 1 4 4v12a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V6a4 4 0 0 1 4-4z", P: "M20 1.2 38.8 12 20 22.8 1.2 12z",
  L: "M8 2h24l6.8 10L32 22H8L1.2 12z", A: "M9.4 12a10.6 10.6 0 1 0 21.2 0a10.6 10.6 0 1 0-21.2 0z"};

/** A number's shape as it is on the map, for a row or the legend: its outline with its text inside. */
export function Shape({kind, text}: {kind: MarkKind; text: string}) {
  return <svg class="v-sh" viewBox="0 0 40 24" role="img" aria-label={text} data-shape={kind}>
    <path d={SHAPES[kind]} /><text x="20" y="12.5">{text}</text></svg>;
}

/** The five classes of the squares as texts: whole numbers "1–4", "5–19", "80+"; metres "under 5", "5–12", "40+";
 *  a class no whole number falls into is left out (null). */
export function classTexts(breaks: number[], whole: boolean): (string | null)[] {
  return [0, 1, 2, 3, 4].map((k) => {
    const from = k === 0 ? (whole ? 1 : 0) : breaks[k - 1], to = k === 4 ? null : whole ? breaks[k] - 1 : breaks[k];
    if (to === null) return `${from}+`;
    if (!whole) return k === 0 ? t("ui.view.map.class_under", {to}) : `${from}–${to}`;
    return to < from ? null : from === to ? String(from) : `${from}–${to}`;
  });
}

function Item({kind, mark, children}: {kind: string; mark: ComponentChildren; children: ComponentChildren}) {
  return <span class="v-lg" data-kind={kind}>{mark}<span class="v-lg-t">{children}</span></span>;
}

/** The legend's items: `short` on a phone (two lines of short labels: the lines and numbers, then the anchors). */
function LegendItems({view, map, legend, short}: {view: SpotView; map: SpotMap; legend: Legend; short: boolean}) {
  const on = legend.shapes, area = legend.level === "area", whole = legend.by === "spots" || legend.by === "lines";
  const word = (key: string) => t(`ui.view.map.lg_${key}${short ? "_short" : ""}`);
  const squares = area && on.sq && <>
    <select class="v-select v-by" aria-label={t("ui.view.map.colour_by")} title={t("ui.view.map.colour_by")} value={legend.by}
            onChange={(e) => map.setSquareBy(e.currentTarget.value as SquareBy)}>
      {BYS.map((by) => <option key={by} value={by}>{t(`ui.view.map.by_${by}`)}</option>)}
    </select>
    <span class="v-classes" data-kind="sq">
      {classTexts(legend.breaks, whole).map((text, k) => text !== null &&
        <span class="v-lg v-class" key={k}><i class={`v-lay v-lay-${k + 1}`} />{text}</span>)}
    </span>
  </>;
  const lines = !area && <>
    {on.clear && <Item kind="clear" mark={<Swatch color={COLORS.clean} />}>{t("ui.result.legend_clear")}</Item>}
    {on.over && <Item kind="over" mark={<Swatch color={COLORS.over} />}>
      {short ? t("ui.view.map.lg_over_short") : t("ui.result.legend_over")}</Item>}
  </>;
  const numbers = <>
    {on.P && <Item kind="P" mark={<Shape kind="P" text="P1" />}>{word("pick")}</Item>}
    {on.B && <Item kind="B" mark={<Shape kind="B" text="B1" />}>{word("best")}</Item>}
    {on.pale && <Item kind="pale" mark={<i class="v-pale" />}>{word("pale")}</Item>}
  </>;
  const fan = <>
    {on.L && <Item kind="L" mark={<Shape kind="L" text="L1" />}>{word("fan")}</Item>}
    {on.here && !short && <Item kind="here" mark={<i class="v-ring" />}>{t("ui.view.map.lg_here", {m: FAN_HERE})}</Item>}
  </>;
  const anchor = on.A && <Item kind="A" mark={<Shape kind="A" text="A1" />}>{word("anchor")}</Item>;
  const access = view.model.hasAccess && ACCESS_STATES.map((state) =>
    <span class="v-lg" data-kind={`access-${state}`} key={state}><AccessMark state={state} />{accessWord(state)}</span>);
  if (short) {
    // a phone: the squares or the lines and numbers; then the anchors: the three marks, or without the access mark
    // the selected line's circle
    const second = access || anchor;
    return <>
      <div class="v-lg-line">{squares}{lines}{!area && numbers}{fan}</div>
      {(area && on.P || second) && <div class="v-lg-line">{area && numbers}{second}</div>}
    </>;
  }
  return <>
    {squares}{lines}{numbers}{anchor}{fan}
    {access && <><span class="v-lg"><b>{t("ui.access.legend")}</b></span>{access}</>}
  </>;
}

export interface MapBarProps {
  view: SpotView;
  /** The canvas (null until the map is made): its legend() says what is drawn. */
  map: SpotMap | null;
  /** The columns (else a phone: the legend in two short lines with its fold). */
  wide: boolean;
  /** The frame's hint (a desktop: beside the status line). */
  hint?: ComponentChildren;
}

/** The bar's two parts over the map. */
export function MapBar({view, map, wide, hint}: MapBarProps) {
  const pressed = view.auto ? "auto" : view.level, status = statusOf(view), area = view.level === "area";
  const [, setTick] = useState(0);
  useEffect(() => map?.subscribe(() => setTick((n) => n + 1)), [map]);
  const [folded, setFolded] = useState(false);
  const help = useAccessHelp();
  const legend = map?.legend(), access = view.model.hasAccess;
  const shown = legend && map && (wide || !folded);
  return <>
    <div class="v-switch">
      <div class="u-seg v-levels" role="group" aria-label={t("ui.view.map.levels")} title={t("ui.view.map.levels_help")}
           data-map-control>
        {LEVELS.map((k) => <button type="button" key={k} data-level={k} aria-pressed={pressed === k}
                                   class={cx(pressed === k && "u-on", view.auto && k === view.level && "v-now")}
                                   onClick={() => view.setLevel(k)}>{t(`ui.view.map.level_${k}`)}</button>)}
      </div>
      <label class={cx("v-best", area && "v-off")} title={t("ui.view.map.best_help")} data-map-control>
        {t("ui.view.map.best")}
        <select class="v-select" value={String(view.best)} disabled={area}
                onChange={(e) => view.setBest(e.currentTarget.value === "all" ? "all" : Number(e.currentTarget.value) as Best)}>
          {BESTS.map((b) => <option key={b} value={String(b)}>{b === "all" ? t("ui.view.map.best_all") : b}</option>)}
        </select>
      </label>
    </div>
    <div class={cx("v-foot", !wide && "v-foot-phone")}>
      {access && help.panel && <div class="v-help" data-map-control>{help.panel}</div>}
      <div class="v-row">
        <div class={cx("v-status", status.refused && "v-refused")} role="status" data-map-control>
          <span class="v-status-text">{status.text}</span>
          {!view.auto && <>
            <span class="u-small">{t("ui.view.map.held")}</span>
            <button type="button" class="r-link v-back-auto" onClick={() => view.setLevel("auto")}>{t("ui.view.map.back_auto")}</button>
          </>}
        </div>
        {!wide && <button type="button" class={cx("v-fold", folded && "v-folded")} aria-expanded={!folded} aria-controls="v-legend"
                          title={t(folded ? "ui.view.map.legend_show" : "ui.view.map.legend_hide")} data-map-control
                          onClick={() => setFolded(!folded)}>{t("ui.view.map.legend_fold")}<Icon name="down" /></button>}
        {!wide && access && <span class="v-help-button" data-map-control>{help.button}</span>}
        {hint}
      </div>
      {shown && <div class={cx("v-legend", !wide && "v-legend-phone")} id="v-legend" aria-label={t("ui.view.map.legend")} data-map-control>
        <LegendItems view={view} map={map} legend={legend} short={!wide} />
        {wide && access && help.button}
        {wide && area && legend.shapes.sq && <span class="v-lg-note">{t("ui.view.map.squares_note")}</span>}
      </div>}
    </div>
  </>;
}
