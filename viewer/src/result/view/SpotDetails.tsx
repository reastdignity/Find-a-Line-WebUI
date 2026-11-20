// The details of the selected spot in the result view (docs/line-volume/spec-view.md B.2 item 10; the frame's
// `details` slot): "Spot 7.1" and "104 lines" with × (ends the selection, as Esc and the row pressed again), the
// selected line's four values as tiles (length, mean height, clearance, highest point; a tight line's clearance tile
// in the warning colour with the word "Tight": the pilot of 2026-11-18, no banner), "Reaching the anchors" (in a run
// with the access mark: "A1", "A2"), "‹ Line 1 of 104 ›" stepping through every passing line of
// the spot by mean height (the map does not move), "Stands for …" in the view's own words (W5 a), the line's actions
// ("3D view", "Copy link", "Profile" after the profile was closed: SpotActions.tsx), the two buttons "Lines from
// anchor A1 / A2" (they open "Lines from here" at that anchor) and the line's facts as a table with a column per
// anchor (viewFacts: the view's own words; today's page keeps LineDetails' lineFacts). Step 3c joined today's
// features in the accepted mock-up's places (the user's "11 a", "4 d"): the star in the head (beside ×), a phone's
// profile dock under the four values, "Report this line" below the facts (the `lineActions` slot); today's "Zoom" is
// left out. While "Lines from here" is open its panel stands here instead (FanPanel). "Open spot" stays hidden (B-5).
//
// This file also holds what stands in the frame's slots (SLOTS, which SpotPanels.tsx PANELS calls): the list, these
// details, the table of spots, the hint, a phone's sheet head (what is open: the title of "Lines from here" with
// "Close", the spot's title with its star and ×, or the headline; the buttons of a head work while the sheet is at its
// lowest, where its body is cut off) and the line's actions after the details (Report).

import { useEffect, useRef } from "preact/hooks";
import L from "leaflet";
import { Button, IconButton } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { AccessMark, AccessPair, accessState, accessWord, hasAccess, useAccessHelp } from "../../access";
import { shortMetres } from "../../endzone";
import { dh } from "../../filters";
import { t } from "../../i18n";
import { clearanceText, isTight } from "../../tight";
import type { Line } from "../../types";
import { count, cx, num, TightIcon } from "./common";
import { FanHead, FanPanel } from "./FanPanel";
import { Hint } from "./Hint";
import { ordinal } from "./LineDetails";
import { LineActions, LineDock, LineStar, ReportLine } from "./SpotActions";
import { SpotChooser } from "./SpotChooser";
import { FOCUS_REST, keepFocus, metres, SpotList, useViewPanels } from "./SpotList";
import { panelState } from "./viewstate";
import type { ChooserProps, PanelProps } from "./SpotPanels";
import { SpotCount } from "./SpotSummary";

/** "Spot 7.1" with "104 lines" beside it (the spot's passing lines), the selected line's two access marks, its star
 *  (where the page keeps favourites: SpotActions.tsx LineStar) and ×. */
export function SpotHead(p: PanelProps) {
  const {view} = p, sel = view.selected;
  if (!sel) return null;
  const n = view.passingCount(sel.spot);
  return <>
    <h3 class="vl-spot-title">{t("ui.view.spot", {label: view.label(sel.spot)})}
      {" "}<span class="vl-spot-count">{t("ui.view.spot_lines", {count: n, n: count(n)})}</span>
      {hasAccess(sel.line) && <>{" "}<AccessPair line={sel.line} /></>}</h3>
    <LineStar {...p} />
    <IconButton icon="close" label={t("ui.view.close")} plain class="vl-dclose" onClick={() => view.select(null)} />
  </>;
}

/** A tile of the selected line's four values: the value with its unit above its label; the clearance of a tight
 *  line in the warning colour with the tight mark and the word "Tight" as a second label line. */
function Tile({value, label, tight, lift}: {value: string; label: string; tight?: boolean; lift?: number | null}) {
  return <div class={cx("vl-tile", tight && "vl-is-tight")}>
    <span class="vl-tile-v">{tight && <TightIcon lift={lift} />}{value}<small>m</small></span>
    <span class="vl-tile-l">{label}{tight && <b class="vl-tword">{t("ui.view.tile.tight")}</b>}</span>
  </div>;
}

/** "Reaching the anchors" (a line of a run with the access mark): its "i" (the help, which opens under the rows),
 *  then a row per anchor: "A1", the mark, the state's words. */
function AccessRows({line: l}: {line: Line}) {
  const help = useAccessHelp(undefined, true);
  return <section class="vl-acc" aria-label={t("ui.access.title")}>
    <h4 class="vl-acc-h">{t("ui.access.title")}{help.button}</h4>
    {[l.access1, l.access2].map((value, k) => {
      const state = accessState(value);
      return <div class="vl-acc-row" key={k}>
        <span class="vl-acc-a">{t("ui.view.anchor_short", {n: k + 1})}</span>
        {state === null ? <span aria-hidden="true" /> : <AccessMark state={state} label={t("ui.access.anchor_state", {n: k + 1, state: accessWord(state)})} />}
        {state === null ? <span role="img" aria-label={t("ui.access.anchor_none", {n: k + 1})}>–</span> : <span>{accessWord(state)}</span>}
      </div>;
    })}
    {help.panel}
  </section>;
}

/** A row of the facts: its label, then a value per anchor (two cells) or one value for the line (across both). */
type Fact = {label: string; note?: string; values: [string, string] | [string]} | {group: string};

/** The facts of the selected line beyond its four values (R9: labelled values, a column per anchor): where the anchors
 *  are, their heights and percentiles, the wall's angle, their prominence and drop, then the line's clearance over
 *  trees or buildings, its height difference, how much of it is high above the ground, over water and over filled
 *  gaps, and in a run with a no-fall zone or A-frames its rigging (the run's options and what the line needs). */
export function viewFacts(l: Line, highAbove: number, run?: {end_zone?: number; lift?: number}): Fact[] {
  const out: Fact[] = [];
  const pct = (p: number | null) => p === null ? t("ui.view.fact.pct_none") : ordinal(p);
  const m = (v: number | null, digits = 0) => v === null ? "–" : metres(v, digits);
  out.push({label: t("ui.view.fact.lat"), values: [l.lat1.toFixed(6), l.lat2.toFixed(6)]});
  out.push({label: t("ui.view.fact.lon"), values: [l.lon1.toFixed(6), l.lon2.toFixed(6)]});
  out.push({label: t("ui.view.fact.elev"), values: [metres(l.e1, 1), metres(l.e2, 1)]});
  out.push({label: t("ui.view.fact.pct"), values: [pct(l.pct1), pct(l.pct2)]});
  if (isFinite(l.angle1)) {
    out.push({label: t("ui.view.fact.angle"), note: t("ui.view.fact.angle_note"), values: [`${num(l.angle1)}°`, `${num(l.angle2)}°`]});
  }
  if (l.prom1 !== null || l.drop1 !== null) {
    out.push({label: t("ui.view.fact.prom"), values: [m(l.prom1), m(l.prom2)]});
    out.push({label: t("ui.view.fact.drop"), values: [m(l.drop1), m(l.drop2)]});
  }
  if (l.clrN !== null) out.push({label: t("ui.view.fact.over"), values: [t("ui.view.fact.over_value", {m: num(l.clrN, 1)})]});
  out.push({label: t("ui.details.dh"), values: [t("ui.details.dh_value", {m: num(dh(l), 1)})]});
  if (Number.isFinite(l.highPct)) out.push({label: t("ui.details.above"), values: [t("ui.details.above_value", {pct: num(l.highPct), m: highAbove})]});
  if (l.water > 0) out.push({label: t("ui.view.fact.water"), values: [t("ui.view.fact.water_value", {m: num(l.water), len: num(l.len)})]});
  if (l.filled > 0) out.push({label: t("ui.view.fact.filled"), values: [t("ui.view.fact.filled_value", {m: num(l.filled)})]});
  if (typeof l.lift_needed === "number") {
    out.push({group: t("ui.details.rigging")});
    if (run) {
      out.push({label: t("ui.view.fact.zone"), values: [run.end_zone ? t("ui.view.fact.zone_value", {m: shortMetres(run.end_zone)}) : t("ui.view.fact.none")]});
      out.push({label: t("ui.view.fact.lift"), values: [run.lift ? t("ui.view.metres", {v: shortMetres(run.lift)}) : t("ui.view.fact.none")]});
    }
    const needs = (v: number) => v < 0.05 ? t("ui.view.fact.needs_none") : t("ui.view.fact.needs_value", {m: v.toFixed(1)});
    out.push({label: t("ui.view.fact.needs"), values: [needs(l.lift_needed)]});
    if ((!run || run.end_zone) && typeof l.lift_no_zone === "number") out.push({label: t("ui.view.fact.without"), values: [needs(l.lift_no_zone)]});
  }
  return out;
}

/** The facts as a table: "A1" and "A2" over the anchors' columns, thin rules between the rows. */
function Facts({facts}: {facts: Fact[]}) {
  return <table class="vl-facts">
    <thead><tr><th><span class="u-sr">{t("ui.view.fact.label")}</span></th>
      <th scope="col">{t("ui.view.anchor_short", {n: 1})}</th><th scope="col">{t("ui.view.anchor_short", {n: 2})}</th></tr></thead>
    <tbody>{facts.map((f) => "group" in f
      ? <tr key={f.group}><th scope="rowgroup" colSpan={3} class="vl-facts-group">{f.group}</th></tr>
      : <tr key={f.label}><th scope="row">{f.label}{f.note && <span class="vl-facts-note">{f.note}</span>}</th>
        {f.values.length === 2 ? <><td>{f.values[0]}</td><td>{f.values[1]}</td></> : <td colSpan={2}>{f.values[0]}</td>}</tr>)}
    </tbody>
  </table>;
}

/** A line's "Stands for" in the view's own words (the user's W5 a; today's page keeps phase 4's, LineDetails'
 *  lineFacts): "Stands for 41 lines found a few metres apart", or "Stands for this line only". */
export function standsFor(n: number): string {
  return t("ui.view.stands_for_n", {count: n, n: count(n)});
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
  const fan = (end: 1 | 2) => {
    panelState(view).fanFrom = `.vl-from-${end}`;  // where the focus returns when the fan closes
    view.openFan(L.latLng(end === 1 ? l.lat1 : l.lat2, end === 1 ? l.lon1 : l.lon2), {row: sel.row, end});
  };
  return <div class={cx("vl-details", !wide && "vl-phone", l.over && "r-over")} ref={root} data-spot={sel.spot} data-row={sel.row}>
    {head && <div class="vl-dhead"><SpotHead {...p} /></div>}
    <div class="vl-tiles">
      <Tile value={num(l.len)} label={t("ui.view.tile.len")} />
      <Tile value={num(l.hmean, 1)} label={t("ui.view.tile.mean")} />
      {/* an over-trees line's clearance is the clearance above the terrain (helpers.py LineResult.clearance: over the
          NMT; over the trees or buildings it is a fact below, clrN) */}
      <Tile value={clearanceText(l.clr)} label={t(l.over ? "ui.view.tile.clear_terrain" : "ui.view.tile.clear")} tight={isTight(l.clr)} lift={lift} />
      <Tile value={num(l.hmax)} label={t("ui.view.tile.highest")} />
    </div>
    {/* a phone's profile right under the four values (4 d); a desktop's is the frame's card */}
    {!wide && <LineDock {...p} />}
    {hasAccess(l) && <AccessRows line={l} />}
    <div class="vl-step">
      <IconButton icon="back" label={t("ui.view.line_before")} plain class="vl-prev" disabled={at <= 0} onClick={() => step(-1)} />
      <span class="vl-step-text">{t("ui.view.line_of", {k: count(at + 1), n: count(n)})}</span>
      <IconButton icon="next" label={t("ui.view.line_next")} plain class="vl-next" disabled={at >= n - 1} onClick={() => step(1)} />
    </div>
    {typeof l.stands_for === "number" && <p class="vl-stands">{standsFor(l.stands_for)}</p>}
    <LineActions {...p} />
    <div class="vl-acts">
      <Button full class="vl-from-1" onClick={() => fan(1)}>{t("ui.view.from_anchor", {n: 1})}</Button>
      <Button full class="vl-from-2" onClick={() => fan(2)}>{t("ui.view.from_anchor", {n: 2})}</Button>
    </div>
    <Facts facts={viewFacts(l, model.data.high_above, model.data)} />
  </div>;
}

/** The frame's `details` slot: "Lines from here" while it is open, else the selected spot, else (in the columns)
 *  what to do. */
function Details(p: PanelProps) {
  const {view, wide} = p;
  useViewPanels(view);
  // the focus never falls to the page's body when what held it goes: the fan opened (its first row), the fan
  // closed over a spot (the button that opened it, else the spot's row), the selection ended (its row, the list)
  const now = view.fan ? "fan" : view.selected ? "spot" : "none", spot = view.selected?.spot ?? null;
  const was = useRef<{shown: string; spot: number | null}>({shown: now, spot});
  useEffect(() => {
    const before = was.current;
    was.current = {shown: now, spot};
    if (before.shown === now && before.spot === spot) return;
    const row = (k: number | null) => k === null ? [] : [`#vl-row-${k} .vl-main`, `#vl-top-${k} .vl-main`];
    if (now === "fan") keepFocus(".vl-fan .vl-main[tabindex='0']", ".vl-fan-close");
    else if (now === "spot") keepFocus(before.shown === "fan" ? panelState(view).fanFrom : null, ...row(spot), ".vl-dclose", ...FOCUS_REST);
    else keepFocus(...row(before.spot), ...FOCUS_REST);
    if (now !== "fan" && before.shown === "fan") panelState(view).fanFrom = null;
  }, [now, spot]);
  if (view.fan) return <FanPanel {...p} head={wide} />;
  if (view.selected) return <SpotDetails {...p} head={wide} />;
  return wide ? <p class="c-pick vl-empty"><Icon name="info" />{t("ui.view.empty")}</p> : null;
}

/** A phone's sheet head: the head of what is open ("Lines from here" with "Close", the spot with its ×), else the
 *  headline. */
function SheetHead(p: PanelProps) {
  const {view} = p;
  useViewPanels(view);
  return <div class="vl-sheet-row">
    {view.fan ? <FanHead view={view} /> : view.selected ? <SpotHead {...p} /> : <SpotCount view={view} />}
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
  // drawn after the details: "Report this line" below the facts (the line's other actions stand inside the details)
  lineActions: (p: PanelProps) => <ReportLine {...p} />,
};
