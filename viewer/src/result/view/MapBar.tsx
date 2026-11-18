// The result view's bar on the map (docs/line-volume/spec-view.md B.2 items 1, 3, 5-8; spec-search.md 3.9): at
// the top the switch Auto / Area / Spots / Lines with "Best" 10 / 30 / 100 / All; at the bottom the line that says
// what is drawn (with "Held by you." and "Back to Auto" while a level is held; marked when the lines are too many
// to draw), beside it the frame's hint, and the legend: exactly the shapes and colours on the map now (SpotMap's
// legend()), at Area the squares' value (a select) and its five classes, and in a run with the access mark the
// three marks with the "i" of their key. On a phone (the pilot's arrangement of 2026-11-18, docs/DESIGN.md) the foot
// stands from the bottom up at the left beside the scale: the row of "Legend", the key's "i" and the hint's button,
// the legend (two lines of short labels; not kept: unfolded while the sheet is low, folded while it is at half or
// higher, see MapBar), then the status line, whose box holds the map's message as its first line while it lasts; the
// access mark's key opens as a panel above the map's controls. The bar's boxes carry `data-map-control`: the canvas
// places no number under them. Styles in mapbar.css (classes v-*).

import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { AccessMark, ACCESS_STATES, accessWord, useAccessHelp } from "../../access";
import { t } from "../../i18n";
import { COLORS } from "../../style";
import type { Snap } from "../../ui/components";
import { Icon } from "../../ui/icons";
import type { Legend, SpotMap } from "../SpotMap";
import type { Best, SpotView } from "../spots";
import { FAN_HERE, type Level, type SquareBy } from "../viewgeom";
import { count, cx, Swatch } from "./common";
import { Shape } from "./Shape";
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
    {short
      // a phone: the five classes as one ramp between its lowest and its highest value (the classes' texts are its name)
      ? <span class="v-ramp" data-kind="sq" role="img" aria-label={classTexts(legend.breaks, whole).filter((text) => text !== null).join(", ")}>
        {whole ? 1 : 0}<span class="v-ramp-bar">{[1, 2, 3, 4, 5].map((k) => <i key={k} class={`v-lay v-lay-${k}`} />)}</span>
        {classTexts(legend.breaks, whole)[4]}</span>
      : <span class="v-classes" data-kind="sq">
        {classTexts(legend.breaks, whole).map((text, k) => text !== null &&
          <span class="v-lg v-class" key={k}><i class={`v-lay v-lay-${k + 1}`} />{text}</span>)}
      </span>}
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
  /** A phone: the stop of its sheet (the legend folds itself while the sheet is at half or higher). */
  sheet?: Snap;
  /** A phone: move the sheet to a stop (a press on "Legend" where the legend has no room lowers the sheet). */
  onSheet?(snap: Snap): void;
  /** A phone: the map's message (after a crowded tap), the first line of the status line's box while it lasts. */
  message?: string;
}

const LEGEND_LINE = 24;  // px: the least room an unfolded legend is shown in (one line of it)
const GAP = 8;  // px between the foot's boxes (R7)

/** The bar's two parts over the map. */
export function MapBar({view, map, wide, hint, sheet, onSheet, message}: MapBarProps) {
  const pressed = view.auto ? "auto" : view.level, status = statusOf(view), area = view.level === "area";
  const [, setTick] = useState(0);
  useEffect(() => map?.subscribe(() => setTick((n) => n + 1)), [map]);
  // A phone's legend (the user's decision of 2026-11-17): by itself it is unfolded while the sheet is low and folded
  // while the sheet is at half or higher, and folded too while, unfolded, it would reach the map's own controls at
  // the top (the zoom buttons, the shore's chip, the switch). A person's fold or unfold (`choice`) holds until the
  // sheet next changes its stop; at the low stop an unfold of theirs with too little room shows the legend in the room
  // there is (it scrolls inside); at a stop above the low one, where the whole legend does not fit, their press on
  // "Legend" lowers the sheet to its low stop and unfolds the legend there (the planner's decisions of 2026-11-17 and
  // 2026-11-18, the pilot's "unfolded at the low stop only, as today": the person asked to see the legend, and the
  // map's room is what it needs): no control covers another, the button is never off. Whether it fits is measured on
  // the legend drawn unfolded before the frame is painted (`check`: its height depends on the level and the marks).
  // Where even the low stop has less than a line of room (a phone on its side: under about 400 px of height), their
  // press opens the legend as a panel above the map's other controls, as an opened layers list lies above the bar
  // (`asPanel`; it scrolls inside the map's height): closed by the same button, by Esc and by a press on the map.
  const [choice, setChoice] = useState<{at: Snap | undefined; folded: boolean; check?: boolean} | null>(null);
  const [room, setRoom] = useState(Infinity);  // px the legend may take between the top controls and the status line
  // The columns (a desktop, a tablet): where their unfolded legend would reach the map's top controls (a phone held
  // sideways that is 768 px wide or more, a short window), the foot takes the phone's arrangement and its logic: the
  // legend behind "Legend", the key's "i" beside it (the user's decision of 2026-11-18). `roomWide`: the legend's room
  // in the columns' own arrangement (without the row of buttons); a window where it fits keeps the columns' foot.
  const [roomWide, setRoomWide] = useState(Infinity);
  const foot = useRef<HTMLDivElement>(null), natural = useRef(56);  // the unfolded legend's own height, as last drawn
  const asked = choice && choice.at === sheet ? choice.folded : null, high = sheet === "half" || sheet === "full";
  // the sheet changed its stop: the person's choice was for the one before (one made for this stop stays)
  useEffect(() => setChoice((made) => made && made.at === sheet ? made : null), [sheet]);
  const lower = () => {
    setChoice({at: "peek", folded: false});
    onSheet?.("peek");
  };
  const pressLegend = () => {
    const above = sheet !== undefined && sheet !== "peek" && !!onSheet;
    if (folded && above && room < LEGEND_LINE) lower();  // not even a line of room: not drawn here at all
    else if (folded && above) setChoice({at: sheet, folded: false, check: true});  // drawn, measured, then kept or lowered
    else setChoice({at: sheet, folded: !folded});
  };
  const compact = !wide || roomWide < natural.current;  // the phone's foot: the legend behind its fold
  const asPanel = compact && asked === false && room < LEGEND_LINE && !high;
  const folded = compact && (asked === null ? high || room < natural.current : asked || (room < LEGEND_LINE && !asPanel));
  useEffect(() => {
    const column = foot.current?.parentElement;
    if (!asPanel || !column) return;
    const close = () => setChoice({at: sheet, folded: true});
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();  // this Esc closes the legend's panel only (the frame's own order of Esc comes after it)
      close();
    };
    const onPress = (e: Event) => {
      const at = e.target as Element | null;
      if (at?.closest?.(".c-leaflet") && !at.closest(".leaflet-control")) close();
    };
    document.addEventListener("keydown", onKey, true);
    column.addEventListener("pointerdown", onPress, true);
    return () => { document.removeEventListener("keydown", onKey, true); column.removeEventListener("pointerdown", onPress, true); };
  }, [asPanel, sheet]);
  // Where a phone's panels opened by the person stand (the legend as a panel, the access mark's key): from above the
  // status line up to the switch at most, px of the map's column
  const [over, setOver] = useState<{bottom: number; max: number} | null>(null);
  // A phone's foot (the pilot's arrangement of 2026-11-18, for every phone height): from the bottom up the row of
  // buttons (Legend, the access mark's key, the hint's button) at the left beside the scale (which stands at the
  // right: SpotColumns.tsx), the legend, then the status line, whose box also holds the map's message
  const [frame, setFrame] = useState("");  // the measures of the map's column the legend's room depends on
  // Where that column of boxes would still reach a control of the map's top (a phone on its side: 243 px of map
  // above the low sheet, the top's rows end at 164), the status line stands beside the row of buttons instead,
  // the foot ending left of the scale (`inline`: its right edge, px from the column's right, for the state `key` it
  // was measured in; any other state is measured again in the column first). Today's page had the same kind of
  // fallback (the foot beside the scale).
  const [inline, setInline] = useState<{key: string; right: number} | null>(null);
  const key = `${sheet}|${status.text}|${message ?? ""}|${view.auto}|${asked}|${compact}|${frame}`;
  const row = compact && inline !== null && inline.key === key ? inline : null;
  useLayoutEffect(() => {
    const el = foot.current, column = el?.parentElement;
    if (!el || !column) return;
    const visible = (r: DOMRect) => r.width > 0 && r.height > 0;
    const rects = (of: Element, selector: string) => Array.from(of.querySelectorAll(selector), (e) => e.getBoundingClientRect()).filter(visible);
    const drawn = el.querySelector<HTMLElement>(".v-legend"), box = el.getBoundingClientRect(), col = column.getBoundingClientRect();
    if (drawn) natural.current = drawn.scrollHeight + 2;
    if (!wide) {  // where the switch and Best end: a phone on its side puts its zoom and layers beside them (mapbar.css)
      const ends = rects(column, ".v-switch > *").map((r) => r.right), right = ends.length ? `${Math.round(Math.max(...ends) - col.left)}px` : "";
      if (column.style.getPropertyValue("--v-switch-right") !== right) column.style.setProperty("--v-switch-right", right);
    }
    const tops = rects(column, ".leaflet-top .leaflet-control, .v-switch > *");
    const floor = Math.max(col.top, ...tops.map((r) => r.bottom));
    const measured = [Math.round(floor - col.top), Math.round(col.width), Math.round(col.height), column.style.getPropertyValue("--v-covered"),
                      column.style.getPropertyValue("--v-corner")].join();
    if (measured !== frame) { setFrame(measured); return; }  // drawn again for this frame, then measured
    // from those controls (4 px clear) down to the foot's other boxes (the status line, the row of buttons)
    const others = box.height - (drawn ? drawn.offsetHeight + GAP : 0);
    const next = Math.floor(box.bottom - others - GAP - floor - 4);
    if (next !== room) setRoom(next);
    if (wide) {  // the room the legend would have in the columns' own arrangement: above the foot's bottom, its status row
      const line = el.querySelector(".v-row:not(.v-buttons)")?.getBoundingClientRect();
      const plain = Math.floor(box.bottom - (line ? line.height : 0) - GAP - floor - 4);
      if (plain !== roomWide) setRoomWide(plain);
    }
    // a press on "Legend" above the low stop: the legend just drawn unfolded stays where it fits whole, else the sheet
    // goes to its low stop and the legend unfolds there (this runs before the frame is painted)
    if (choice?.check && choice.at === sheet && drawn) {
      if (drawn.scrollHeight + 2 > next) { lower(); return; }
      setChoice({at: choice.at, folded: false});
    }
    const status = el.querySelector(".v-status")?.getBoundingClientRect(), ceiling = column.querySelector(".v-switch")?.getBoundingClientRect().top ?? col.top;
    if (status) {
      const at = {bottom: Math.round(col.bottom - status.top) + GAP, max: Math.max(60, Math.floor(status.top - GAP - ceiling))};
      if (!over || over.bottom !== at.bottom || over.max !== at.max) setOver(at);
    }
    if (row || !compact) return;
    const mine = rects(el, ".v-status, .v-legend, .v-buttons > :not(.v-hint-slot), .v-hint-slot > *");
    if (!mine.some((b) => tops.some((c) => b.left < c.right + 4 && b.right > c.left - 4 && b.top < c.bottom + 4 && b.bottom > c.top - 4))) return;
    // left of what stands in the map's bottom right corner above the credits (the scale)
    const scale = rects(column, ".leaflet-bottom.leaflet-right .leaflet-control-scale")[0];
    setInline({key, right: scale ? Math.round(col.right - scale.left) + GAP : GAP});
  });
  const help = useAccessHelp(undefined, true);
  const legend = map?.legend(), access = view.model.hasAccess;
  const shown = legend && map && !folded;  // (the columns' legend folds only in the phone's arrangement: `compact`)
  const legendBox = shown && <div class={cx("v-legend", !wide && "v-legend-phone")} id="v-legend" role="group" aria-label={t("ui.view.map.legend")} data-map-control
                                  style={compact && !asPanel && room < natural.current
                                    ? {maxHeight: `${Math.max(room, LEGEND_LINE)}px`, ...(wide ? {overflowY: "auto"} : {})} : undefined}>
    <LegendItems view={view} map={map} legend={legend} short={!wide} />
    {!compact && access && help.button}
    {wide && area && legend.shapes.sq && <span class="v-lg-note">{t("ui.view.map.squares_note")}</span>}
  </div>;
  const helpBox = access && help.panel && <div class="v-help" data-map-control>{help.panel}</div>;
  // the status line; on a phone the map's message is its first line while it lasts (one box for the map's words)
  const statusBox = <div class={cx("v-status", status.refused && "v-refused")} role="status" data-map-control>
    {message && <span class="v-toast v-msg">{message}</span>}
    <span class="v-status-text">{status.text}</span>
    {!view.auto && <>
      <span class="u-small">{t("ui.view.map.held")}</span>
      <button type="button" class="r-link v-back-auto" onClick={() => view.setLevel("auto")}>{t("ui.view.map.back_auto")}</button>
    </>}
  </div>;
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
    <div class={cx("v-foot", !wide && "v-foot-phone", sheet === "full" && "v-foot-off", row && "v-foot-inline")} ref={foot}
         style={row ? {right: `${row.right}px`} : undefined}>
      {!compact && helpBox}
      {wide ? <div class="v-row">{statusBox}{hint}</div> : statusBox}
      {compact && !asPanel && legendBox}
      {compact && <div class="v-row v-buttons">
        <button type="button" class={cx("v-fold", folded && "v-folded")} aria-expanded={!folded} aria-controls="v-legend"
                title={t(folded ? "ui.view.map.legend_show" : "ui.view.map.legend_hide")} data-map-control
                onClick={pressLegend}>{t("ui.view.map.legend_fold")}<Icon name="down" /></button>
        {access && <span class="v-help-button" data-map-control>{help.button}</span>}
        {!wide && hint}
      </div>}
      {!compact && legendBox}
    </div>
    {compact && over && sheet !== "full" && (helpBox || (asPanel && legendBox)) &&
      <div class="v-over" style={{bottom: `${over.bottom}px`, maxHeight: `${over.max}px`}}>
        {helpBox}
        {asPanel && legendBox}
      </div>}
  </>;
}
