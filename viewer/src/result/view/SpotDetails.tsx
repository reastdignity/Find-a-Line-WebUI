// The details of the selected spot in the result view (docs/line-volume/spec-view.md B.2 item 10; the frame's
// `details` slot): "Spot 7.1 · 104 lines" with × (ends the selection, as Esc and the row pressed again), the
// selected line's four values (long, mean height, clear, highest point), the tight line, "Reaching the anchors"
// (today's AccessBlock, in a run with the access mark), "‹ Line 1 of 104 ›" stepping through every passing line of
// the spot by mean height (the map does not move), "Stands for: …" in phase 4's words, the two buttons "Lines
// from anchor A1 / A2" (they open "Lines from here" at that anchor) and today's facts of the line. While "Lines
// from here" is open its panel stands here instead (FanPanel). Not here yet (they join with today's other features,
// step 3c): "Open spot", the star, the profile, the 3D view, the line's links.
//
// This file also holds what stands in the frame's slots (SLOTS, which SpotPanels.tsx PANELS calls): the list, these
// details, the table of spots, the hint, and a phone's sheet head (what is open: the title of "Lines from here"
// with "Close", the spot's title with ×, or the headline; the buttons of a head work while the sheet is at its
// lowest, where its body is cut off).

import { Fragment } from "preact";
import { useEffect, useRef } from "preact/hooks";
import L from "leaflet";
import { Button, IconButton, Stat, Stats } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { AccessPair, hasAccess } from "../../access";
import { t } from "../../i18n";
import { clearanceText, isTight, tightLine } from "../../tight";
import type { SpotView } from "../spots";
import { count, cx, num } from "./common";
import { FanHead, FanPanel } from "./FanPanel";
import { Hint } from "./Hint";
import { AccessBlock, lineFacts } from "./LineDetails";
import { SpotChooser } from "./SpotChooser";
import { SpotList, useViewPanels } from "./SpotList";
import type { ChooserProps, PanelProps } from "./SpotPanels";
import { SpotCount } from "./SpotSummary";

/** "Spot 7.1 · 104 lines" (the spot's passing lines), the selected line's two access marks, and ×. */
export function SpotHead({view}: {view: SpotView}) {
  const sel = view.selected;
  if (!sel) return null;
  const n = view.passingCount(sel.spot);
  return <>
    <h3 class="vl-spot-title">{t("ui.view.spot", {count: n, label: view.label(sel.spot), n: count(n)})}
      {hasAccess(sel.line) && <>{" "}<AccessPair line={sel.line} /></>}</h3>
    <IconButton icon="close" label={t("ui.view.close")} class="vl-dclose" onClick={() => view.select(null)} />
  </>;
}

/** The details; `head` false: without the title and × (a phone's sheet shows them in its head). */
export function SpotDetails({head = true, ...p}: PanelProps & {head?: boolean}) {
  const {view, wide} = p;
  useViewPanels(view);
  const root = useRef<HTMLDivElement>(null), pressed = useRef<1 | -1 | 0>(0);
  const sel = view.selected, at = view.selectedIndex;
  // a stepper's button that went off at the spot's first or last line hands the focus to its pair
  useEffect(() => {
    const by = pressed.current;
    pressed.current = 0;
    if (!by || !root.current) return;
    const button = (dir: number) => root.current!.querySelector<HTMLButtonElement>(dir > 0 ? ".vl-next" : ".vl-prev");
    const same = button(by), pair = button(-by);
    if (same?.disabled && pair && !pair.disabled) pair.focus();
  }, [sel?.row]);
  if (!sel) return null;
  const model = view.model, l = sel.line, lift = model.liftOf(l), n = view.passingCount(sel.spot);
  const step = (by: 1 | -1) => {
    pressed.current = by;
    view.step(by);
  };
  const fan = (end: 1 | 2) => view.openFan(L.latLng(end === 1 ? l.lat1 : l.lat2, end === 1 ? l.lon1 : l.lon2), {row: sel.row, end});
  const stands = t("ui.details.stands_for");
  const facts = lineFacts(l, model.data.high_above, model.data).filter(([label]) => label !== stands);
  return <div class={cx("vl-details", !wide && "vl-phone", l.over && "r-over")} ref={root} data-spot={sel.spot} data-row={sel.row}>
    {head && <div class="vl-dhead"><SpotHead view={view} /></div>}
    <Stats>
      <Stat value={num(l.len)} unit="m" label={t("ui.details.stat.long")} />
      <Stat value={num(l.hmean, 1)} unit="m" label={t("ui.details.stat.mean")} />
      <Stat value={clearanceText(l.clr)} unit="m" label={t(l.over ? "ui.details.stat.clear_terrain" : "ui.details.stat.clear")} />
      <Stat value={num(l.hmax)} unit="m" label={t("ui.details.stat.highest")} />
    </Stats>
    {isTight(l.clr) && <p class="r-tight-line"><i class="r-tight" aria-hidden="true" />{tightLine(l.clr, lift)}</p>}
    {hasAccess(l) && <AccessBlock line={l} />}
    <div class="vl-step">
      <IconButton icon="back" label={t("ui.view.line_before")} plain class="vl-prev" disabled={at <= 0} onClick={() => step(-1)} />
      <span class="vl-step-text">{t("ui.view.line_of", {k: count(at + 1), n: count(n)})}</span>
      <IconButton icon="next" label={t("ui.view.line_next")} plain class="vl-next" disabled={at >= n - 1} onClick={() => step(1)} />
    </div>
    {typeof l.stands_for === "number" && <p class="vl-stands">
      {t("ui.view.stands_for", {text: t("ui.details.stands_for_n", {count: l.stands_for, n: count(l.stands_for)})})}</p>}
    <div class="vl-acts">
      <Button full class="vl-from-1" onClick={() => fan(1)}>{t("ui.view.from_anchor", {n: 1})}</Button>
      <Button full class="vl-from-2" onClick={() => fan(2)}>{t("ui.view.from_anchor", {n: 2})}</Button>
    </div>
    <dl class="r-kv">{facts.map(([label, value]) => <Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>)}</dl>
  </div>;
}

/** The frame's `details` slot: "Lines from here" while it is open, else the selected spot, else (in the columns)
 *  what to do. */
function Details(p: PanelProps) {
  const {view, wide} = p;
  useViewPanels(view);
  if (view.fan) return <FanPanel {...p} head={wide} />;
  if (view.selected) return <SpotDetails {...p} head={wide} />;
  return wide ? <p class="c-pick vl-empty"><Icon name="info" />{t("ui.view.empty")}</p> : null;
}

/** A phone's sheet head: the head of what is open ("Lines from here" with "Close", the spot with its ×), else the
 *  headline. */
function SheetHead({view}: PanelProps) {
  useViewPanels(view);
  return <div class="vl-sheet-row">
    {view.fan ? <FanHead view={view} /> : view.selected ? <SpotHead view={view} /> : <SpotCount view={view} />}
  </div>;
}

/** What stands in the frame's slots (SpotPanels.tsx PANELS takes them: its entries call these when the frame
 *  draws, so the two files may import each other). */
export const SLOTS = {
  list: (p: PanelProps) => <SpotList {...p} />,
  details: (p: PanelProps) => <Details {...p} />,
  sheetHead: (p: PanelProps) => <SheetHead {...p} />,
  hint: (p: PanelProps) => <Hint {...p} />,
  chooser: (p: ChooserProps) => <SpotChooser key={`${p.at.x},${p.at.y}`} {...p} />,
};
