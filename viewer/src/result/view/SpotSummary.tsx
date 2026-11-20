// The head of a result in the result view (docs/line-volume/spec-view.md B.2 item 14, A.2): "624 spots, 36 296
// lines" of the lines that pass the filters (the view's counts; thousands with a no-break space), how many lines
// the filters hide ("Top level only" among them), and in a run made with the square rule the second line "2 010 351
// found. Why so many?" whose link opens today's box (ResultSummary's WhyBox: its "Show" boxes are filters like the
// others). Under them, as on today's page: a run whose access mark was asked for and left out (its area too wide:
// RunHead.access_skipped) says so in today's muted line (ResultSummary's AccessLegend, which for a run without the
// mark draws only that line); then today's notes: the coarser terrain's and the model's. The legend is the map's
// (MapBar).

import { t } from "../../i18n";
import type { SpotView } from "../spots";
import { count } from "./common";
import { AccessLegend, CoarserNote, ResultNote, WhyBox } from "./ResultSummary";
import { changePanels, panelState } from "./viewstate";

/** The headline alone: the spots and lines that pass, and the lines hidden. */
export function SpotCount({view}: {view: SpotView}) {
  const c = view.counts;
  return <div class="r-summary-count vl-count">
    <span class="u-h">{t("ui.view.headline", {spots: t("ui.result.spots", {count: c.spots, n: count(c.spots)}),
                                               lines: t("ui.result.lines", {count: c.lines, n: count(c.lines)})})}</span>
    {c.hidden > 0 && <span class="u-small">{t("ui.result.hidden", {n: count(c.hidden)})}</span>}
  </div>;
}

/** The head of the list; `headline` false: without the counts (a phone's sheet shows them in its head). The
 *  caller follows the view (SpotList's useViewPanels). */
export function SpotSummary({view, headline = true}: {view: SpotView; headline?: boolean}) {
  const model = view.model, ui = panelState(view);
  // A run made with the square rule: one line was kept per pair of anchor squares, of `found` lines found
  const {found, square} = model.data, known = typeof found === "number";
  const setWhy = (why: boolean) => changePanels(view, (s) => { s.why = why; });
  return <div class="r-summary vl-summary">
    {headline && <SpotCount view={view} />}
    {known && <>
      <p class="u-small r-found-line"><span class="r-found" title={t("ui.result.found_title", {m: square})}>
        {t("ui.result.found", {n: count(found as number)})}</span>{" "}
        <button type="button" class="r-link r-why-link" aria-expanded={ui.why} aria-controls="r-why"
                onClick={() => setWhy(!ui.why)}>{t("ui.result.why")}</button></p>
      {ui.why && <WhyBox model={model} found={found as number} onClose={() => setWhy(false)} />}
    </>}
    {/* the line "Anchors' access not marked: …" only (a run with the mark has its legend on the map) */}
    {!model.hasAccess && <AccessLegend model={model} />}
    <CoarserNote model={model} />
    <ResultNote model={model} />
  </div>;
}
