// The panel of "Lines from here" (docs/line-volume/spec-view.md B.2 item 11; spec-search.md 3.9 for the column
// "Far end"): shown in the details' place while the view's fan is open (SpotView.fan; the canvas opens it at a
// right click, a press and hold, a press on A1 or A2; the details' two buttons at an anchor). Its sentence ("648
// lines start within 10 m of this point, to 29 far ends.", and "The best 40 are shown." when there are more far
// ends than rows), the five sorts (Mean height at the start, Clearance, Length, Height diff. with the smallest
// first, Direction by bearing; the model sorts, because the L numbers on the map follow the rows, and numbered
// rows stay first), and a row per far end: the shape it carries on the map (B3, P1, else L1 …), length, mean
// height, clearance with the tight mark, the height difference from the near end to the far end (signed, 0.1 m),
// the direction ("SE 141°"), in a run with the access mark the far anchor's mark, and for a line over trees or
// buildings the list's words on a line of their own under its values (R4.2; no swatch: the rows carry none). A row
// selects its line and closes the fan (SpotView.select); "Close" closes it and keeps the selection. Rows as
// SpotList's: a list item with one button, one tab stop for the list (the first row), arrows, Home and End.

import { useEffect, useRef } from "preact/hooks";
import { Button } from "../../ui/components";
import { AccessMark, accessState, accessWord } from "../../access";
import { t } from "../../i18n";
import type { Fan, FanRow, FanSort, SpotView } from "../spots";
import { bearing, FAN_HERE } from "../viewgeom";
import { count, cx, TightIcon, TightKey } from "./common";
import { Shape } from "./Shape";
import { Head, metres, OverWords, overRow, rowKeys, tightRow, useHover, useViewPanels, Value, withAccess } from "./SpotList";
import type { PanelProps } from "./SpotPanels";
import { clearanceText } from "../../tight";

/** The sorts in the order of their buttons, and the columns in the order of a row. */
const SORT_KEYS: FanSort[] = ["hmean", "clr", "len", "dh", "dir"];
const COLUMNS: FanSort[] = ["len", "hmean", "clr", "dh", "dir"];

/** The panel's sentence. */
export function fanText(fan: Fan): string {
  const text = t("ui.view.fan.text", {lines: t("ui.view.fan.lines", {count: fan.lines, n: count(fan.lines)}), m: FAN_HERE,
                                      ends: t("ui.view.fan.ends", {count: fan.farEnds, n: count(fan.farEnds)})});
  return fan.capped ? `${text} ${t("ui.view.fan.capped", {n: fan.rows.length})}` : text;
}

/** A height difference with its sign, 0.1 m: "+3.2 m", "−0.4 m", "0.0 m". */
export function signedMetres(dh: number): string {
  if (!Number.isFinite(dh)) return "–";
  const shown = Math.abs(dh).toFixed(1);
  return t("ui.view.metres", {v: (Number(shown) === 0 ? "" : dh > 0 ? "+" : "−") + shown});
}

/** A direction as the row writes it: "SE 141°" (degrees from true north). */
export function directionText(deg: number): string {
  if (!Number.isFinite(deg)) return "–";
  const rad = deg * Math.PI / 180;
  return t("ui.view.fan.direction", {word: bearing(Math.sin(rad), Math.cos(rad)).word, deg: Math.round(deg) % 360});
}

/** The panel's title with "Close" (a phone: in the sheet's head). */
export function FanHead({view}: {view: SpotView}) {
  return <>
    <h3 class="vl-fan-title">{t("ui.view.fan.title")}</h3>
    <Button class="vl-fan-close" onClick={() => view.closeFan()}>{t("ui.view.fan.close")}</Button>
  </>;
}

function FanLine({p, r, tab}: {p: PanelProps; r: FanRow; tab: boolean}) {
  const {view, map, padding} = p, v = view.values, c = view.model.data.columns, row = r.row;
  const hover = useHover(map, row);
  const far = accessState(r.near === 1 ? c.access2.at(row) : c.access1.at(row)), over = overRow(view, row);
  const press = () => {
    view.select(view.spotOf(row), row);  // selects the line and closes the fan
    map?.reveal(row, padding());
  };
  return <li class={cx("vl-row", over && "vl-over")}>
    <button type="button" class="vl-main" tabIndex={tab ? 0 : -1} data-row={row} data-label={r.label} onClick={press}
            {...hover}>
      <Shape text={r.label} />
      <Value name={t("ui.list.col.length")}>{metres(v.len[row])}</Value>
      <Value name={t("ui.list.col.mean")}>{metres(v.hmean[row], 1)}</Value>
      <Value name={t("ui.view.col.clear")} class="vl-clr">
        {tightRow(view, row) && <TightIcon lift={view.model.data.lift} />}{metres(Number(clearanceText(v.clr[row])), 1)}</Value>
      <Value name={t("ui.view.fan.sort.dh")}>{signedMetres(r.dh)}</Value>
      <Value name={t("ui.view.fan.sort.dir")}>{directionText(r.bearing)}</Value>
      {withAccess(view) && <span class="vl-cell-acc">{far === null ? <span class="ac-none" aria-hidden="true">–</span>
        : <AccessMark state={far} label={t("ui.view.fan.far_end_state", {state: accessWord(far)})} />}</span>}
      {over && <OverWords />}
    </button>
  </li>;
}

const HEADS: Record<FanSort, string> = {len: "ui.list.col.length", hmean: "ui.list.col.mean", clr: "ui.view.col.clear",
                                        dh: "ui.view.fan.sort.dh", dir: "ui.view.fan.sort.dir"};

/** The panel; `head` false: without its title and "Close" (a phone's sheet shows them in its head). */
export function FanPanel({head = true, ...p}: PanelProps & {head?: boolean}) {
  const {view, wide} = p;
  useViewPanels(view);
  const root = useRef<HTMLDivElement>(null);
  // a phone: the sheet shows the panel from its top
  useEffect(() => {
    const body = !wide && root.current?.closest<HTMLElement>(".u-sheet-body");
    if (body) body.scrollTop = 0;
  }, [view.fan?.at]);
  const fan = view.fan;
  if (!fan) return null;
  const acc = withAccess(view);
  return <div class={cx("vl-fan", !wide && "vl-phone")} ref={root}>
    {head && <div class="vl-dhead"><FanHead view={view} /></div>}
    <p class="vl-stands vl-fan-text">{fanText(fan)}</p>
    <div class="vl-fan-sort"><div class="u-seg" role="group" aria-label={t("ui.view.fan.sort")}>
      {SORT_KEYS.map((k) => <button type="button" key={k} data-sort={k} class={fan.sort === k ? "u-on" : ""} aria-pressed={fan.sort === k}
                                    onClick={() => view.sortFan(k)}>{t(`ui.view.fan.sort.${k}`)}</button>)}
    </div></div>
    <div class={cx("vl-cols", acc && "vl-with-acc")} aria-hidden="true"><span />
      {COLUMNS.map((k) => <Head key={k} by={fan.sort === k} text={t(HEADS[k])} />)}
      {acc && <span class="vl-cell-acc">{t("ui.view.fan.far_end")}</span>}
    </div>
    <ul class={cx("vl-rows", acc && "vl-with-acc")} aria-label={t("ui.view.fan.title")} onKeyDown={rowKeys}>
      {fan.rows.map((r, k) => <FanLine key={r.row} p={p} r={r} tab={k === 0} />)}
    </ul>
    {fan.rows.some((r) => tightRow(view, r.row)) && <TightKey lift={view.model.data.lift} drawn />}
  </div>;
}
