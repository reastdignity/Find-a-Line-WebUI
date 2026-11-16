// The result view's bar on the map (docs/line-volume/spec-view.md B.2 items 1, 5-7): at the top the switch Auto /
// Area / Spots / Lines with "Best" 10 / 30 / 100 / All; at the bottom the line that says what is drawn (with
// "Held by you." and "Back to Auto" while a level is held; marked when the lines are too many to draw) and, beside
// it, the frame's hint. Its boxes carry `data-map-control`: the canvas places no number under them (SpotMap).
// Styles in mapbar.css (classes v-*).
//
// MILESTONE 1: the switch, Best and the status line. The legend comes with milestone 3.

import type { ComponentChildren } from "preact";
import { t } from "../../i18n";
import type { Best, SpotView } from "../spots";
import type { Level } from "../viewgeom";
import { count, cx } from "./common";
import "./mapbar.css";

const LEVELS: (Level | "auto")[] = ["auto", "area", "spots", "lines"];
const BESTS: Best[] = [10, 30, 100, "all"];

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

/** The bar's two parts over the map; `hint`: the frame's hint (a desktop: beside the status line). */
export function MapBar({view, hint}: {view: SpotView; hint?: ComponentChildren}) {
  const pressed = view.auto ? "auto" : view.level, status = statusOf(view), area = view.level === "area";
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
    <div class="v-foot">
      <div class="v-row">
        <div class={cx("v-status", status.refused && "v-refused")} role="status" data-map-control>
          <span class="v-status-text">{status.text}</span>
          {!view.auto && <>
            <span class="u-small">{t("ui.view.map.held")}</span>
            <button type="button" class="r-link v-back-auto" onClick={() => view.setLevel("auto")}>{t("ui.view.map.back_auto")}</button>
          </>}
        </div>
        {hint}
      </div>
    </div>
  </>;
}
