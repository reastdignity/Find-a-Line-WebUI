// The selected line of a result (model.selected): "Spot k of N" with ‹ › and × (ends the selection), its
// numbers, "Reaching the anchors" (the access mark of each anchor, for a line of a run made with it), the other
// lines of its spot, and its actions: favourite,
// copy link, zoom, the 3D view (where the shell gives it), and the profile again after it was closed.

import { Fragment } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { Button, IconButton, Stat, Stats } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { dh } from "../../filters";
import type { Line } from "../../types";
import type { ResultModel } from "../model";
import { canReport, openReport } from "../../report";
import { FavouritePicker } from "./FavouritePicker";
import { ResultNote } from "./ResultSummary";
import { count, cx, num, Swatch, useModel } from "./common";
import { clearanceText, isTight, tightLine } from "../../tight";
import { day } from "../../time";
import { t } from "../../i18n";
import { shortMetres } from "../../endzone";
import { AccessMark, AccessPair, accessState, accessWord, hasAccess, useAccessHelp } from "../../access";

// The rank of a spot's first line, by "Show per spot" (model.state.by; texts ui.details.first_<by>)
const BY_LABEL = ["mean", "clearance", "longest", "height"];
const DOTS = 12;  // dots of the spot's lines; more are a number only

/** The app's link to a line: its address with `#run=<id>&line=<lat1,lon1,lat2,lon2>`. */
export function appLink(model: ResultModel, l: Line): string {
  const base = typeof location !== "undefined" ? location.origin + location.pathname + location.search : "";
  return `${base}#run=${encodeURIComponent(model.runOf(l))}&line=${encodeURIComponent(model.lineLink(l))}`;
}

/** Put a text on the clipboard; false when the browser does not allow it (then LinkField shows it to copy by hand). */
export async function copy(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** A link the clipboard did not take: selected in a read-only field to copy by hand. */
export function LinkField({text}: {text: string}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); ref.current?.select(); }, [text]);
  return <label class="r-linkfield"><span class="u-small">Copy this link:</span>
    <input ref={ref} class="u-input" readOnly value={text} onFocus={(e) => e.currentTarget.select()} /></label>;
}

export interface LineDetailsProps {
  model: ResultModel;
  /** The link "Copy link" gives (default appLink: this page with #run=…&line=…). */
  linkOf?(line: Line): string;
  /** The address of the line's 3D view (/view3d#run=…&line=…); no button without it. */
  view3dOf?(line: Line): string;
  /** "Zoom" was pressed (hidden without it). */
  onZoom?(line: Line): void;
  /** ‹ › or a line of the spot selected another line (e.g. to bring it into the map's view). */
  onStep?(line: Line): void;
  /** "head": "Spot k of N", title and ‹ › only (a sheet's peek); "body": the rest; default both. */
  part?: "all" | "head" | "body";
  /** Show model.note (default false: ResultSummary shows it). */
  note?: boolean;
}

/** A whole number as an English ordinal: 1st, 2nd, 3rd, 4th, 11th-13th, 21st, ... */
export function ordinal(n: number): string {
  const tens = n % 100, ones = n % 10;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ones === 1 ? "st" : ones === 2 ? "nd" : ones === 3 ? "rd" : "th";
  return `${n}${suffix}`;
}

/** The row "Rigging" of a line of a run with a no-fall zone or A-frames: the run's options (`run`: its "end_zone"
 *  and "lift"; none for another run's line) and what the line needs; null for a line without the values. */
export function riggingText(l: Line, run?: {end_zone?: number; lift?: number}): string | null {
  if (typeof l.lift_needed !== "number") return null;
  const parts: string[] = [];
  if (run) {
    parts.push(run.end_zone ? t("ui.details.zone", {m: shortMetres(run.end_zone)}) : t("ui.details.no_zone"));
    parts.push(run.lift ? t("ui.details.lift", {m: shortMetres(run.lift)}) : t("ui.details.no_lift"));
  }
  let needs = l.lift_needed < 0.05 ? t("ui.details.needs_none") : t("ui.details.needs", {m: l.lift_needed.toFixed(1)});
  if ((!run || run.end_zone) && typeof l.lift_no_zone === "number") {
    needs += " " + (l.lift_no_zone < 0.05 ? t("ui.details.without_none") : t("ui.details.without", {m: l.lift_no_zone.toFixed(1)}));
  }
  parts.push(needs);
  return parts.join(" · ");
}

/** The facts of a line beyond its four numbers, as label and value; `run`: the options of the line's run (this
 *  run's data.js "end_zone" and "lift") for the row "Rigging". */
export function lineFacts(l: Line, highAbove: number, run?: {end_zone?: number; lift?: number}): [string, string][] {
  const facts: [string, string][] = [];
  if (l.run) facts.push(["Run", `${day(l.run.info.created)} ${l.run.info.name}`]);
  const pct = (p: number | null) => p === null ? " (percentile not known)" : ` (${ordinal(p)} percentile)`;
  facts.push(["Anchor 1", `${l.lat1.toFixed(6)}, ${l.lon1.toFixed(6)} · ${num(l.e1, 1)} m${pct(l.pct1)}`]);
  facts.push(["Anchor 2", `${l.lat2.toFixed(6)}, ${l.lon2.toFixed(6)} · ${num(l.e2, 1)} m${pct(l.pct2)}`]);
  if (l.clrN !== null) facts.push(["Over trees/buildings", `${num(l.clrN, 1)} m clear`]);
  // the highest point and the mean height are the stats above the facts
  facts.push([t("ui.details.dh"), t("ui.details.dh_value", {m: num(dh(l), 1)})]);
  if (Number.isFinite(l.highPct)) {
    facts.push([t("ui.details.above"), t("ui.details.above_value", {pct: num(l.highPct), m: highAbove})]);
  }
  if (isFinite(l.angle1)) facts.push(["Angle to the wall", `A1 ${num(l.angle1)}°, A2 ${num(l.angle2)}° (0° straight out)`]);
  const m = (v: number | null) => v === null ? "–" : num(v) + " m";
  if (l.prom1 !== null || l.drop1 !== null) {
    facts.push(["Anchors stand out", `prominence ${m(l.prom1)} / ${m(l.prom2)} · drop ${m(l.drop1)} / ${m(l.drop2)}`]);
  }
  if (l.water > 0) facts.push(["Over water", `${num(l.water)} m of ${num(l.len)} m`]);
  if (l.filled > 0) facts.push(["Over filled gaps", `${num(l.filled)} m (less precise data)`]);
  const rigging = riggingText(l, run);
  if (rigging) facts.push([t("ui.details.rigging"), rigging]);
  // a run made with the square rule: the found lines between the same two anchor squares this line stands for
  if (typeof l.stands_for === "number") {
    facts.push([t("ui.details.stands_for"), t("ui.details.stands_for_n", {count: l.stands_for, n: count(l.stands_for)})]);
  }
  return facts;
}

/** "Reaching the anchors" of a line with the access mark: a row per anchor (the mark, "Anchor 1", the state's
 *  words) and the "?" of the help, which opens under the rows. */
function AccessBlock({line: l}: {line: Line}) {
  const help = useAccessHelp();
  return <div class="r-acc">
    <div class="r-acc-h">{t("ui.access.title")}{help.button}</div>
    {[l.access1, l.access2].map((value, k) => {
      const state = accessState(value), name = t("ui.access.anchor", {n: k + 1});
      return <div class="r-acc-row" key={k}>
        {state === null ? <span /> : <AccessMark state={state} label={t("ui.access.anchor_state", {n: k + 1, state: accessWord(state)})} />}
        <span class="r-acc-a">{name}</span><span>{state === null ? "–" : accessWord(state)}</span>
      </div>;
    })}
    {help.panel}
  </div>;
}

// The button pressed for ‹ ›: its details are drawn again under the next row (another component), which
// gives the same button the focus; a button disabled at the end hands it to its pair
let refocus: string | null = null;
const PAIRS: Record<string, string> = {"Previous spot": "Next spot", "Next spot": "Previous spot",
                                       "Previous line of the spot": "Next line of the spot",
                                       "Next line of the spot": "Previous line of the spot"};

export function LineDetails({model, linkOf, view3dOf, onZoom, onStep, part = "all", note = false}: LineDetailsProps) {
  useModel(model);
  const [copied, setCopied] = useState<{line: Line; ok: boolean; text: string} | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const sel = model.selected;
  useEffect(() => {
    if (!refocus || !root.current) return;
    const find = (label: string) => root.current!.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
    const button = find(refocus), pair = find(PAIRS[refocus]);
    const target = button && !button.disabled ? button : pair && !pair.disabled ? pair : null;
    if (target) { target.focus(); refocus = null; }
  });
  if (!sel) return note ? <ResultNote model={model} /> : null;
  const {group, line: l} = sel;
  const k = model.position, n = model.rows.length, size = group.size, at = model.variantIndex();
  const members = model.membersOf(group), lift = model.liftOf(l);
  const pressed = (e: Event) => { refocus = (e.currentTarget as HTMLElement).getAttribute("aria-label"); };
  const step = (by: 1 | -1, e: Event) => {
    pressed(e);
    if (by > 0 ? model.next() : model.prev()) onStep?.(model.selected!.line);
  };
  const variant = (to: number, e?: Event) => {
    if (e) pressed(e);
    const line = members[to];
    model.choose(group, line);
    onStep?.(line);
  };
  const by = BY_LABEL.includes(model.state.by) ? model.state.by : "clearance";
  const link = () => {
    const text = (linkOf || ((x: Line) => appLink(model, x)))(l);
    copy(text).then((ok) => setCopied({line: l, ok, text}));
  };
  const shownCopy = copied && copied.line === l ? copied : null;

  const head = <div class="r-dhead">
    <div class="u-grow">
      <div class="r-eyebrow">{k >= 0 ? `Spot ${k + 1} of ${n}` : "Spot"}{size > 1 && ` · ${size} similar`}</div>
      <div class="r-dtitle">{l.run && <Swatch color={l.run.color} />}{num(l.len)} m · {clearanceText(l.clr)} m clear
        {/* a phone's sheet shows only this head at first: the two marks stand in it */}
        {part === "head" && hasAccess(l) && <AccessPair line={l} />}</div>
    </div>
    <div class="r-pager">
      <IconButton icon="back" label="Previous spot" disabled={k <= 0 && k !== -1} onClick={(e) => step(-1, e)} />
      <IconButton icon="next" label="Next spot" disabled={k >= n - 1} onClick={(e) => step(1, e)} />
      <IconButton icon="close" label="Close the spot" class="r-dclose" onClick={() => model.select(null)} />
    </div>
  </div>;
  if (part === "head") return <div class="r-details" ref={root}>{head}</div>;

  return <div class={cx("r-details", l.over && "r-over")} ref={root}>
    {part === "all" && head}
    {note && <ResultNote model={model} />}
    <Stats>
      <Stat value={num(l.len)} unit="m" label={t("ui.details.stat.long")} />
      <Stat value={num(l.hmean, 1)} unit="m" label={t("ui.details.stat.mean")} />
      <Stat value={clearanceText(l.clr)} unit="m" label={t(l.over ? "ui.details.stat.clear_terrain" : "ui.details.stat.clear")} />
      <Stat value={num(l.hmax)} unit="m" label={t("ui.details.stat.highest")} />
    </Stats>
    {isTight(l.clr) && <p class="r-tight-line"><i class="r-tight" aria-hidden="true" />{tightLine(l.clr, lift)}</p>}
    {l.over && <p class="r-warn"><Icon name="warn" />Passes over trees or buildings: check it on the photo.</p>}
    {hasAccess(l) && <AccessBlock line={l} />}
    {size > 1 && <div class="r-var">
      <IconButton icon="back" label="Previous line of the spot" plain disabled={at <= 0}
                  onClick={(e) => variant(at - 1, e)} />
      {size <= DOTS && <span class="r-dots" aria-hidden="true">{members.map((_, i) =>
        <i key={i} class={i === at ? "r-on" : ""} />)}</span>}
      <span class="u-grow"><b>{at + 1} of {size}</b> similar lines
        {at === 0 ? ` · ${t(`ui.details.first_${by}`)}`
          : <> · <button type="button" class="r-link" onClick={() => variant(0)}>back to the first</button></>}</span>
      <IconButton icon="next" label="Next line of the spot" plain disabled={at >= size - 1}
                  onClick={(e) => variant(at + 1, e)} />
    </div>}
    <div class="r-acts">
      {model.favouritesOn && <FavouritePicker model={model} line={l} />}
      <Button icon="link" class="r-copy" onClick={link}>{shownCopy?.ok ? "Link copied" : "Copy link"}</Button>
      {onZoom && <Button icon="zoom" onClick={() => onZoom(l)}>Zoom</Button>}
      {view3dOf && <Button icon="cliff" class="r-view3d" href={view3dOf(l)}>{t("ui.view3d.open")}</Button>}
      {model.profileClosed && <Button icon="ruler" class="r-reprofile" onClick={() => model.showProfile()}>Profile</Button>}
      {canReport() && <Button icon="warn" kind="ghost" class="r-report"
                              onClick={() => openReport({category: "results", about: `a line of ${l.run ? l.run.info.name : model.data.run.name}`,
                                                         context: {run: model.runOf(l), line: model.lineLink(l)}})}>
        Report this line</Button>}
    </div>
    {shownCopy && !shownCopy.ok && <LinkField text={shownCopy.text} />}
    {shownCopy?.ok && <input type="hidden" class="r-copied" value={shownCopy.text} />}
    <dl class="r-kv">{lineFacts(l, model.data.high_above, l.run ? undefined : model.data).map(([label, value]) =>
      <Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>)}</dl>
  </div>;
}
