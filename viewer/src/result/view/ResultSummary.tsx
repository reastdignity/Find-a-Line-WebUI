// The head of a result: "31 spots · 48 lines" (counts with a no-break space as the thousands separator), how
// many lines the filters hide, in a run made with the square rule a second line "1 930 found. Why so many?" whose
// link opens what the found lines are (WhyBox), the legend of the line colours (style.ts), under it the legend's
// row of the access mark when a run shown has it (AccessLegend: the three states and the "?" of the help), and
// the model's note (a link to a line, a favourite not saved).

import { useState } from "preact/hooks";
import { Button } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { COLORS } from "../../style";
import { t } from "../../i18n";
import { ACCESS_STATES, AccessMark, accessWord, useAccessHelp } from "../../access";
import { fallbacks, layerName, percent, warns } from "../../coarser";
import { NEED_FILTERS } from "../../filters";
import type { ResultModel } from "../model";
import { count, cx, Swatch, useModel } from "./common";

export interface ResultSummaryProps {
  model: ResultModel;
  /** Show the legend (default true). */
  legend?: boolean;
  /** Show model.note with its action (default true). */
  note?: boolean;
}

/** The note of the model (model.note) with its action. */
export function ResultNote({model}: {model: ResultModel}) {
  useModel(model);
  const note = model.note;
  if (!note) return null;
  return <div class="r-note" role="status"><Icon name="info" /><span class="u-grow">{note.text}</span>
    {note.action && <Button kind="ghost" onClick={() => note.onAction?.()}>{note.action}</Button>}
    <button type="button" class="r-note-x" aria-label="Close" onClick={() => model.setNote(null)}>
      <Icon name="close" /></button>
  </div>;
}

/** The head's note when the fallbacks gave FALLBACK_WARN_SHARE of the land or more (coarser.warns): their share,
 *  their names, and "Show on map" while the map can show their regions. */
export function CoarserNote({model}: {model: ResultModel}) {
  useModel(model);
  const sources = model.data.terrain_sources;
  if (!warns(sources)) return null;
  const source = sources.layers.find((l) => l.role === "source");
  return <div class="r-note r-coarse" role="status"><Icon name="info" />
    <span class="u-grow">{t("ui.coarse.head", {percent: percent(sources.fallback_share),
                                                 fallback: fallbacks(sources).map(layerName).join(" and "),
                                                 source: source ? source.name : ""})}</span>
    {model.coarserFit && <Button kind="ghost" onClick={() => model.coarserFit?.()}>{t("ui.coarse.show")}</Button>}
  </div>;
}

/** "Why so many lines?" of a run made with the square rule: what the found lines are, and on a run with the no-fall
 *  zone or A-frames how many of its lines need each class of rigging, with a bar of their shares and a "Show"
 *  checkbox each (a cleared one hides that class: filters.ts hideNeed*, like any filter). */
function WhyBox({model, found, onClose}: {model: ResultModel; found: number; onClose(): void}) {
  const needs = model.needCounts(), f = model.filters;
  const keys = ["ui.result.need_none", "ui.result.need_zone", "ui.result.need_lift"];
  return <section class="r-why" id="r-why" aria-label={t("ui.result.why_title")}>
    <div class="r-why-head"><b class="u-grow">{t("ui.result.why_title")}</b>
      <button type="button" class="r-note-x" aria-label={t("ui.result.why_close")} onClick={onClose}>
        <Icon name="close" /></button></div>
    <p class="u-small r-why-text">{t("ui.result.why_text", {found: count(found)})}
      {needs && <>{" "}{t("ui.result.why_of", {n: count(model.count)})}</>}</p>
    {needs && <>
      <div class="r-why-bar" aria-hidden="true">{needs.map((n, k) =>
        <i key={k} class={cx(`r-why-k${k}`, f[NEED_FILTERS[k]] && "r-off")} style={{flexGrow: n}} />)}</div>
      {needs.map((n, k) => <label key={k} class="r-why-row">
        <i class={`r-why-k${k}`} aria-hidden="true" />
        <span class="u-grow">{t(keys[k], {count: n, n: count(n)})}</span>
        <span class="r-why-show"><input type="checkbox" checked={!f[NEED_FILTERS[k]]}
                                        onChange={(e) => model.setFilters({...f, [NEED_FILTERS[k]]: !e.currentTarget.checked})} />
          {t("ui.result.show")}</span>
      </label>)}
    </>}
  </section>;
}

/** The legend's row of the access mark: "Anchors", the three states with their dots, the "?" and the help it
 *  opens under the row; nothing while no run shown has the mark. */
export function AccessLegend({model}: {model: ResultModel}) {
  useModel(model);
  const help = useAccessHelp();
  if (!model.hasAccess) return null;
  return <div class="r-legend-box">
    <div class="r-legend r-legend-acc"><b>{t("ui.access.legend")}</b>
      {ACCESS_STATES.map((state) => <span key={state}><AccessMark state={state} />{accessWord(state)}</span>)}
      {help.button}
    </div>
    {help.panel}
  </div>;
}

export function ResultSummary({model, legend = true, note = true}: ResultSummaryProps) {
  useModel(model);
  const [why, setWhy] = useState(false);
  const {spots, lines} = model.shown, total = model.total, hidden = total - lines;
  const grouped = model.state.group;
  // A run made with the square rule: one line was kept per pair of anchor squares, of `found` lines found
  const {found, square} = model.data, known = typeof found === "number";
  const linesText = t("ui.result.lines", {count: lines, n: count(lines)});
  return <div class="r-summary">
    <div class="r-summary-count">
      <span class="u-h">{grouped ? `${t("ui.result.spots", {count: spots, n: count(spots)})} · ${linesText}` : linesText}</span>
      {hidden > 0 && <span class="u-small">{t("ui.result.hidden", {n: count(hidden)})}</span>}
    </div>
    {known && <>
      <p class="u-small r-found-line"><span class="r-found" title={t("ui.result.found_title", {m: square})}>
        {t("ui.result.found", {n: count(found as number)})}</span>{" "}
        <button type="button" class="r-link r-why-link" aria-expanded={why} aria-controls="r-why"
                onClick={() => setWhy(!why)}>{t("ui.result.why")}</button></p>
      {why && <WhyBox model={model} found={found as number} onClose={() => setWhy(false)} />}
    </>}
    {legend && <div class="r-legend">
      <span><Swatch color={COLORS.clean} />{t("ui.result.legend_clear")}</span>
      {model.nOver > 0 && <span><Swatch color={COLORS.over} />{t("ui.result.legend_over")}</span>}
      {model.favouritesOn && <span><Swatch color={COLORS.favourite} class="r-sw-fav" />{t("ui.result.legend_favourite")}</span>}
      {Array.from(model.others.values()).map((r) =>
        <span key={r.info.id} title={r.info.description}><Swatch color={r.color} />{r.info.name}</span>)}
    </div>}
    {legend && <AccessLegend model={model} />}
    <CoarserNote model={model} />
    {note && <ResultNote model={model} />}
  </div>;
}
