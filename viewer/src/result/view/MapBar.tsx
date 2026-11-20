// The result view's bar on the map (docs/line-volume/spec-view.md B.2 items 1, 3, 5-8; spec-search.md 3.9): at
// the top the switch Auto / Area / Spots / Lines with "Best" 10 / 30 / 100 / All; at the bottom the line that says
// what is drawn (with "Kept while you zoom." and "Back to Auto" while a level is held; marked when the lines are too
// many to draw; "No line passes the filters." while none does), beside it the frame's hint, and the legend: exactly
// the shapes and colours on the map now (SpotMap's legend()), at Area the squares' value (a select) and its five
// classes, a favourite's halo, the search area's outline and Compare's other runs while they are drawn, and in a run
// with the access mark the three marks with the "i" of their key while an anchor of the selected line is in view
// (the user's L b). One "i" for the map (the user's 7 b): on a desktop at the switch's end, its panel under the switch
// with the texts of the levels and of Best (at Area also why Best is off); on a phone it is the foot's "i" (the access
// key's before), its panel "About the map" with the parts "Auto, Area, Spots, Lines", "Best" and, in a run with the
// mark, "Anchors" (the key), one open at a time, opening on "Anchors" (the button's meaning before; without the mark
// on the first part: the planner's choice). On a phone (the pilot's arrangement of 2026-11-18, docs/DESIGN.md) the
// foot stands from the bottom up at the left beside the scale: the row of "Legend", the map's "i" and the hint's
// button, the legend (short labels; not kept: unfolded while the sheet is low, folded while it is at half or higher,
// see MapBar), then the status line, whose box holds the measuring tip or the map's message as its first line while
// it lasts; the map's help opens as a panel above the map's controls. The columns take the phone's foot (the legend
// behind "Legend") where the legend would reach the top controls, and while the profile's card is open (`short`: the
// user's 4 a). The bar's boxes carry `data-map-control`: the canvas places no number under them. Styles in mapbar.css
// (classes v-*).

import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { AccessKey, AccessMark, ACCESS_STATES, accessWord, useAccessHelp } from "../../access";
import { t } from "../../i18n";
import { COLORS } from "../../style";
import { IconButton, type Snap } from "../../ui/components";
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
  // no line passes the filters: the map draws nothing at any level (the user's W14)
  if (!view.counts.lines) return {text: t("ui.view.map.status_none_pass"), refused: false};
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

/** A favourite's sign in the legend as the map draws it: the line inside its gold band (the map's own colours,
 *  style.ts COLORS; the accepted mock-up's sign, the design review's F5). */
function FavSign() {
  return <span class="v-fav" style={{background: COLORS.favourite}} aria-hidden="true"><i style={{background: COLORS.clean}} /></span>;
}

/** A dashed outline's sign in the legend (the search area's, another run's in its colour): the dashes on a chip of
 *  the map's own paper, as the outline lies on the light tiles in both themes (the mock-up's polish 14). */
function Dash({color}: {color?: string}) {
  return <svg class="v-dash" viewBox="0 0 16 12" aria-hidden="true"><rect width="16" height="12" rx="3" />
    <path d="M1 6H15" style={color ? {stroke: color} : undefined} /></svg>;
}

/** The legend's items: `short` on a phone (lines of short labels: the lines and numbers; the pick, the favourite, the
 *  search area and other runs; the anchors). The access mark's three rows only while an anchor of the selected line
 *  is in view (`ends`: the user's L b). */
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
  const access = view.model.hasAccess && on.ends && ACCESS_STATES.map((state) =>
    <span class="v-lg" data-kind={`access-${state}`} key={state}><AccessMark state={state} />{accessWord(state)}</span>);
  // drawn besides the spots (the canvas's `fav`, `area`, `runs`): a favourite's halo, the search area's outline,
  // Compare's other runs (their names)
  const runs = legend.runs;
  const extra = <>
    {on.fav && <Item kind="fav" mark={<FavSign />}>{t("ui.result.legend_favourite")}</Item>}
    {on.area && <Item kind="area" mark={<Dash />}>{word("area")}</Item>}
    {runs.map((run) => <span class="v-lg" data-kind="run" key={run.id}>
      <span class="v-runmark"><Swatch color={run.color} /><Dash color={run.color} /></span><span class="v-lg-t">{run.name}</span></span>)}
  </>;
  if (short) {
    // a phone: the squares or the lines and numbers; the pick at Area, what else is drawn, and without the access
    // mark the selected line's circle; then the access mark's three rows
    const second = (area && on.P) || on.fav || on.area || runs.length > 0 || (!view.model.hasAccess && on.A);
    return <>
      <div class="v-lg-line">{squares}{lines}{!area && numbers}{fan}</div>
      {second && <div class="v-lg-line">{area && numbers}{extra}{!view.model.hasAccess && anchor}</div>}
      {access && <div class="v-lg-line">{access}</div>}
    </>;
  }
  return <>
    {squares}{lines}{numbers}{anchor}{fan}{extra}
    {/* "Anchors" and its three marks on one row (a wrapped legend never parts them: the design review's F4) */}
    {access && <span class="v-lg-group"><span class="v-lg"><b>{t("ui.access.legend")}</b></span>{access}</span>}
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
  /** A phone: the measuring tip, the first line of the status line's box while measuring (the user's 11 a). */
  tip?: string;
  /** The columns: the profile's card is open, so the foot is the short one (the legend behind "Legend"; the user's
   *  4 a, docs/DESIGN.md row 18). */
  short?: boolean;
}

const LEGEND_LINE = 24;  // px: the least room an unfolded legend is shown in (one line of it)
const GAP = 8;  // px between the foot's boxes (R7)

type Part = "levels" | "best" | "anchors";

/** The map's one "i" and its help (the user's 7 b): the part open (a desktop shows every text whatever the part), or
 *  null: closed. Esc closes it (before the frame's own order of Esc); from inside the help the focus goes to `back`
 *  (its "i"), as its × gives it. */
function useMapHelp(back: () => void): [Part | null, (open: Part | null) => void] {
  const [open, setOpen] = useState<Part | null>(null);
  const latest = useRef(back);
  latest.current = back;
  // (a layout effect: the listener is there when the help is drawn, not a frame later; an Esc pressed at once closes it)
  useLayoutEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();  // this Esc closes the help only
      const inside = document.activeElement instanceof Element && !!document.activeElement.closest("#v-about");
      setOpen(null);
      if (inside) latest.current();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open]);
  return [open, setOpen];
}

/** Best's text, and at Area why it is off (the user's W11). */
function bestText(area: boolean): string {
  return `${t("ui.view.map.best_help")}.${area ? " " + t("ui.view.map.best_area") : ""}`;
}

/** The help's close (the mock-up's ×): the panel also closes by its own "i" and by Esc. */
function HelpClose({onClose}: {onClose(): void}) {
  return <IconButton icon="close" label={t("ui.view.map.help_close")} plain class="v-about-x" onClick={onClose} />;
}

/** The map's help as a desktop shows it: both texts, under the switch. */
function HelpAll({area, onClose}: {area: boolean; onClose(): void}) {
  return <div class="v-help v-about v-about-all" id="v-about" role="note" data-map-control>
    <div class="v-about-txt">
      <p><b>{t("ui.view.map.help_levels")}.</b> {t("ui.view.map.levels_help")}</p>
      <p><b>{t("ui.view.map.help_best")}.</b> {bestText(area)}</p>
    </div>
    <HelpClose onClose={onClose} />
  </div>;
}

/** The map's help as a phone shows it: its parts, one always open (`open`; a press on another opens that one and
 *  folds the first: the mock-up's), the others folded to a row. */
function HelpParts({open, onPart, onClose, area, access}: {open: Part; onPart(part: Part): void; onClose(): void; area: boolean;
                                                           access: boolean}) {
  const part = (id: Part, title: string, text: ComponentChildren) => <>
    <button type="button" class="v-part" data-part={id} aria-expanded={open === id} onClick={() => onPart(id)}>
      <Icon name={open === id ? "down" : "next"} /><b>{title}</b></button>
    {open === id && <div class="v-part-text">{text}</div>}
  </>;
  return <div class="v-help v-about v-about-parts" id="v-about" role="group" aria-label={t("ui.view.map.about")} data-map-control>
    <div class="v-about-txt">
      {part("levels", t("ui.view.map.help_levels"), <p>{t("ui.view.map.levels_help")}</p>)}
      {part("best", t("ui.view.map.help_best"), <p>{bestText(area)}</p>)}
      {access && part("anchors", t("ui.access.legend"), <AccessKey />)}
    </div>
    <HelpClose onClose={onClose} />
  </div>;
}

/** The bar's two parts over the map. */
export function MapBar({view, map, wide, hint, sheet, onSheet, message, tip, short}: MapBarProps) {
  const pressed = view.auto ? "auto" : view.level, status = statusOf(view), area = view.level === "area";
  const [, setTick] = useState(0);
  useEffect(() => map?.subscribe(() => setTick((n) => n + 1)), [map]);
  const aboutRef = useRef<HTMLButtonElement>(null);
  const [about, setAbout] = useMapHelp(() => aboutRef.current?.focus({preventScroll: true}));
  // a phone's help is not drawn while the sheet is at full (the map unseen): closed then, so Esc is not taken by it
  useEffect(() => { if (!wide && sheet === "full" && about) setAbout(null); }, [wide, sheet, about]);
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
  const credits = useRef(0);  // the columns' credits as last drawn unfolded (the compact foot folds them: ui.css)
  const foot = useRef<HTMLDivElement>(null), natural = useRef(56);  // the unfolded legend's own height, as last drawn
  const asked = choice && choice.at === sheet ? choice.folded : null, high = sheet === "half" || sheet === "full";
  // the sheet changed its stop: the person's choice was for the one before (one made for this stop stays)
  useEffect(() => setChoice((made) => made && made.at === sheet ? made : null), [sheet]);
  // the profile's card opened or closed (a desktop): a choice made with the other foot is not kept
  const shortNow = !!short;
  useEffect(() => setChoice(null), [shortNow]);
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
  // the phone's foot: the legend behind its fold (the columns: where it has no room, `roomy`; or while the profile's
  // card is open, `short`, folded until it is asked for)
  const roomy = wide && roomWide < natural.current, compact = !wide || roomy || shortNow;
  const asPanel = compact && asked === false && room < LEGEND_LINE && !high;
  const folded = compact && (asked === null ? high || shortNow || room < natural.current : asked || (room < LEGEND_LINE && !asPanel));
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
  const key = `${sheet}|${status.text}|${message ?? ""}|${tip ?? ""}|${view.auto}|${asked}|${compact}|${frame}`;
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
    // the columns with the phone's foot for want of room: the zoom's + and − side by side in one row, as on a phone
    // (mapbar.css; the planner's decision of 2026-11-18); not for the profile's card alone (`short`: the mock-up's 4 a
    // keeps the zoom as it is)
    if (column.classList.contains("v-compact") !== roomy) column.classList.toggle("v-compact", roomy);
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
      // the zoom counted stacked and the credits unfolded, as the columns draw them, also while the compact foot lays the
      // zoom across and folds the credits (which lowers the foot as much): the choice must not undo itself
      const line = el.querySelector(".v-row:not(.v-buttons)")?.getBoundingClientRect(), zoom = column.querySelector(".leaflet-control-zoom");
      const stacked = zoom ? zoom.getBoundingClientRect().top + Array.from(zoom.children, (a) => a.getBoundingClientRect().height).reduce((h, v) => h + v, 0) : 0;
      const shown = column.querySelector(".leaflet-bottom .leaflet-control-attribution")?.getBoundingClientRect().height ?? 0;
      if (!compact) credits.current = shown;
      // (the card folds the credits too, and stands on them: the foot is not lowered by that)
      const lowered = compact && !shortNow ? Math.max(0, credits.current - shown) : 0;
      const plain = Math.floor(box.bottom - lowered - (line ? line.height : 0) - GAP - Math.max(floor, stacked) - 4);
      if (plain !== roomWide) setRoomWide(plain);
    }
    // a press on "Legend" above the low stop: the legend just drawn unfolded stays where it fits whole, else the sheet
    // goes to its low stop and the legend unfolds there (this runs before the frame is painted)
    if (choice?.check && choice.at === sheet && drawn) {
      if (drawn.scrollHeight + 2 > next) { lower(); return; }
      setChoice({at: choice.at, folded: false});
    }
    // the panels over the map (the map's help, the access key, the legend as a panel) stop under the level switch's
    // row, which the help explains (the mock-up's 7 b; the design review's F3)
    const switchBox = column.querySelector(".v-switch")?.getBoundingClientRect();
    const status = el.querySelector(".v-status")?.getBoundingClientRect(), ceiling = switchBox ? switchBox.bottom + GAP : col.top;
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
  const keyShown = access && !!legend?.shapes.ends;  // the access key's "i" and panel follow its rows (L b)
  const shown = legend && map && !folded;  // (the columns' legend folds only in the phone's arrangement: `compact`)
  // the legend unfolded or folded (a press on "Legend", the card's short foot): the canvas places its numbers clear of
  // it at once, not at the frame's next rest (no number under the legend meanwhile)
  useLayoutEffect(() => { map?.refresh(); }, [map, !!shown]);
  const legendBox = shown && <div class={cx("v-legend", !wide && "v-legend-phone")} id="v-legend" role="group" aria-label={t("ui.view.map.legend")} data-map-control
                                  style={compact && !asPanel && room < natural.current
                                    ? {maxHeight: `${Math.max(room, LEGEND_LINE)}px`, ...(wide ? {overflowY: "auto"} : {})} : undefined}>
    <LegendItems view={view} map={map} legend={legend} short={!wide} />
    {!compact && keyShown && help.button}
    {wide && area && legend.shapes.sq && <span class="v-lg-note">{t("ui.view.map.squares_note")}</span>}
  </div>;
  // the access mark's key (the columns: in the legend, or in the short foot's row), as its rows only while an anchor
  // of the selected line is in view (the user's L b); a phone's key is a part of the map's help
  const helpBox =wide && keyShown && help.panel && <div class="v-help" data-map-control>{help.panel}</div>;
  // the map's one "i" (the user's 7 b): a desktop's at the switch's end, a phone's in the foot's row; a phone's opens
  // on the access key where the run has the mark
  const aboutButton = <button type="button" class={cx("u-ib u-plain v-info", about && "u-on")} aria-label={t("ui.view.map.about")}
                              title={t("ui.view.map.about")} aria-expanded={!!about} aria-controls="v-about" ref={aboutRef}
                              onClick={() => setAbout(about ? null : wide || !access ? "levels" : "anchors")}><Icon name="info" /></button>;
  /** The help's × closes it; the focus goes back to its "i". */
  const closeAbout = () => { setAbout(null); aboutRef.current?.focus({preventScroll: true}); };
  const aboutBox = about && (wide ? <HelpAll area={area} onClose={closeAbout} />
    : <HelpParts open={about === "anchors" && !access ? "levels" : about} area={area} access={access} onPart={setAbout} onClose={closeAbout} />);
  // the status line; on a phone the measuring tip or the map's message is its first line while it lasts (one box for
  // the map's words)
  const statusBox = <div class={cx("v-status", status.refused && "v-refused")} role="status" data-map-control>
    {tip && <span class="v-msg v-tip">{tip}</span>}
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
      {wide && <span class="v-about-button" data-map-control>{aboutButton}</span>}
    </div>
    {wide && aboutBox}
    <div class={cx("v-foot", !wide && "v-foot-phone", sheet === "full" && "v-foot-off", row && "v-foot-inline")} ref={foot}
         style={row ? {right: `${row.right}px`} : undefined}>
      {!compact && helpBox}
      {wide ? <div class="v-row">{statusBox}{hint}</div> : statusBox}
      {compact && !asPanel && legendBox}
      {compact && <div class="v-row v-buttons">
        <button type="button" class={cx("v-fold", folded && "v-folded")} aria-expanded={!folded} aria-controls="v-legend"
                title={t(folded ? "ui.view.map.legend_show" : "ui.view.map.legend_hide")} data-map-control
                onClick={pressLegend}>{t("ui.view.map.legend_fold")}<Icon name="down" /></button>
        {wide ? keyShown && <span class="v-help-button" data-map-control>{help.button}</span>
          : <span class="v-help-button" data-map-control>{aboutButton}</span>}
        {!wide && hint}
      </div>}
      {!compact && legendBox}
    </div>
    {compact && over && sheet !== "full" && (helpBox || (!wide && aboutBox) || (asPanel && legendBox)) &&
      <div class="v-over" style={{bottom: `${over.bottom}px`, maxHeight: `${over.max}px`}}>
        {helpBox}
        {!wide && aboutBox}
        {asPanel && legendBox}
      </div>}
  </>;
}
