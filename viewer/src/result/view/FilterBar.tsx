// The filters of a result: chips of the main ones (length, clearance, height above the ground, only
// clear lines; a set one is removable, a click edits it) and "More filters": every filter of
// filters.ts, shown only when the lines have its data, and the grouping.
// Values come from and go to the ResultModel (filters, state, ranges). "How to read the result"
// (ResultIntro) opens once, from here: the FilterBar is in every layout of a result.

import { useRef, useState } from "preact/hooks";
import { Button, Chip, Chips, CloseButton, Segmented } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { IntroLink, useIntro } from "../../ui/Intro";
import { parts, t } from "../../i18n";
import { active, liftNeed, NEED_FILTERS, NO_FILTERS, type Filters } from "../../filters";
import { liftChoices, shortMetres } from "../../endzone";
import { COLORS } from "../../style";
import { sharesText } from "../../coarser";
import { BY_MEAN, type ResultModel } from "../model";
import { Limit, Swatch, num, useModel } from "./common";
import { ResultIntro } from "./ResultIntro";

type Main = "len" | "clr" | "height";
const MAIN_KEYS: (keyof Filters)[] = ["lenMin", "lenMax", "clrMin", "heightMin"];

export interface FilterBarProps {
  model: ResultModel;
  /** "More filters" was pressed: the shell shows <MoreFilters> itself; without it they unfold under the chips. */
  onMore?: () => void;
  /** With `onMore`: the shell shows them now (the chip is marked). */
  moreOpen?: boolean;
}

const set = (model: ResultModel, change: Partial<Filters>) => model.setFilters({...model.filters, ...change});

/** How many filters are set beyond the chips (the "More filters" badge; the rigging classes are the head's). */
function moreActive(model: ResultModel): number {
  const f = model.filters;
  const main = [...MAIN_KEYS, ...NEED_FILTERS].filter((k) => f[k] !== NO_FILTERS[k]).length;
  return active(f) - main + (!model.state.showClean ? 1 : 0);
}

function lengthLabel(f: Filters): string {
  if (f.lenMin !== null && f.lenMax !== null) return `Length ${num(f.lenMin)}–${num(f.lenMax)} m`;
  if (f.lenMin !== null) return `Length ≥ ${num(f.lenMin)} m`;
  if (f.lenMax !== null) return `Length ≤ ${num(f.lenMax)} m`;
  return "Length";
}

/** The editor of a main filter, under the chips. */
export function MainEditor({model, which}: {model: ResultModel; which: Main}) {
  const f = model.filters, r = model.ranges;
  if (which === "len" && r.len) {
    return <>
      <Limit label={t("ui.filter.len_from")} value={f.lenMin} range={r.len} step={1} kind="min" unit="m"
             onChange={(v) => set(model, {lenMin: v})} />
      <Limit label={t("ui.filter.len_to")} value={f.lenMax} range={r.len} step={1} kind="max" unit="m"
             onChange={(v) => set(model, {lenMax: v})} />
    </>;
  }
  if (which === "clr" && r.clr) {
    return <Limit label={t("ui.filter.clr_min")} value={f.clrMin} range={r.clr} step={0.1} kind="min" unit="m"
                  onChange={(v) => set(model, {clrMin: v})} />;
  }
  if (which === "height" && r.hmax) {
    return <Limit label={t("ui.filter.height_min")} value={f.heightMin} range={r.hmax} step={1} kind="min"
                  unit="m" onChange={(v) => set(model, {heightMin: v})} />;
  }
  return null;
}

export function FilterBar({model, onMore, moreOpen}: FilterBarProps) {
  useModel(model);
  const [editing, setEditing] = useState<Main | null>(null);
  const [more, setMore] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  /** Close the editor; the focus back to its chip when it was in the editor (Esc, ×). */
  const closeEditor = () => {
    const chip = bar.current?.querySelector<HTMLElement>("[aria-expanded=true]");
    const inside = bar.current?.querySelector(".r-editor")?.contains(document.activeElement);
    setEditing(null);
    if (inside) chip?.focus();
  };
  const removed = (which: Main, change: Partial<Filters>) => {
    set(model, change);
    if (editing === which) setEditing(null);
  };
  const f = model.filters, r = model.ranges, s = model.state;
  const onlyClear = !s.showOver && s.showClean;
  const anything = active(f) > 0 || !s.showOver || !s.showClean;
  const toggle = (which: Main) => setEditing(editing === which ? null : which);
  const extra = moreActive(model);
  const intro = useIntro("result");
  return <div class="r-filters" ref={bar}>
    <ResultIntro state={intro} />
    <Chips>
      {r.len && <Chip on={f.lenMin !== null || f.lenMax !== null} onClick={() => toggle("len")} expanded={editing === "len"}
                      onRemove={f.lenMin !== null || f.lenMax !== null
                        ? () => removed("len", {lenMin: null, lenMax: null}) : undefined}
                      removeLabel="Remove the length filter">{lengthLabel(f)}</Chip>}
      {r.clr && <Chip on={f.clrMin !== null} onClick={() => toggle("clr")} expanded={editing === "clr"}
                      onRemove={f.clrMin !== null ? () => removed("clr", {clrMin: null}) : undefined}
                      removeLabel="Remove the clearance filter">
        {f.clrMin !== null ? `Clearance ≥ ${num(f.clrMin, 1)} m` : "Clearance"}</Chip>}
      {r.hmax && <Chip on={f.heightMin !== null} onClick={() => toggle("height")} expanded={editing === "height"}
                       onRemove={f.heightMin !== null ? () => removed("height", {heightMin: null}) : undefined}
                       removeLabel="Remove the height filter">
        {f.heightMin !== null ? `Height ≥ ${num(f.heightMin)} m` : "Height"}</Chip>}
      {model.nOver > 0 && <Chip on={onlyClear} onClick={() => model.setState({...s, showClean: true, showOver: onlyClear})}>
        Only clear</Chip>}
      <Chip add icon="filter" on={more || moreOpen || extra > 0}
            onClick={() => { if (onMore) onMore(); else setMore(!more); }}>
        More filters{extra > 0 && <span class="u-badge">{extra}</span>}</Chip>
      {anything && <button type="button" class="u-link r-link" onClick={() => {
        model.setState({...s, showClean: true, showOver: true});
        model.clearFilters();
        setEditing(null);
      }}>Clear all</button>}
      <IntroLink state={intro} class="r-link r-intro-link">{t("intro.result.link")}</IntroLink>
    </Chips>
    {editing && <div class="r-editor" role="group" aria-label="Filter"
                     onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeEditor(); } }}>
      <MainEditor model={model} which={editing} />
      <CloseButton label="Close the filter" class="r-note-x r-editor-x" onClick={closeEditor} /></div>}
    {more && !onMore && <MoreFilters model={model} onClose={() => setMore(false)} />}
  </div>;
}

/** The grouping distance: the label shows the value while dragging, the groups change when released. */
function Distance({value, max, onChange}: {value: number; max: number; onChange(v: number): void}) {
  const [draft, setDraft] = useState<number | null>(null);
  const shown = draft ?? value;
  const fill = `${Math.max(0, Math.min(100, (shown - 5) / (max - 5) * 100))}%`;
  const id = useRef("r-dist-" + Math.random().toString(36).slice(2)).current;
  return <div class="r-limit r-set">
    <div class="r-limit-head"><label for={id}>{t("ui.filter.within")}</label><b class="r-mono">{shown} m</b></div>
    <input type="range" id={id} class="u-range r-distance" min={5} max={max} step={1} value={shown}
           style={{"--u-fill": fill}}
           onInput={(e) => setDraft(+e.currentTarget.value)}
           onChange={(e) => { setDraft(null); onChange(+e.currentTarget.value); }} />
  </div>;
}

const LIFT_BIN = 0.5;  // m: the bars of the filter "A-frame needed at most"

/** The filter "A-frame needed at most" of a run with a no-fall zone or A-frames: its choices from 0 to the run's
 *  A-frame height, the switch "without the no-fall zone" (on lift_no_zone), how many of the run's lines pass and
 *  their distribution in bars of LIFT_BIN. */
function LiftFilter({model}: {model: ResultModel}) {
  const f = model.filters, r = model.ranges.lift!;
  const max = f.liftMax ?? r.lift, choices = liftChoices(r.lift);
  const value = choices.find((c) => Math.abs(c - max) < 1e-9) ?? r.lift;
  const top = f.liftNoZone ? Math.max(r.lift, Math.ceil(r.noZone / LIFT_BIN) * LIFT_BIN) : Math.max(r.lift, LIFT_BIN);
  const bins = Math.min(16, Math.max(1, Math.ceil(top / LIFT_BIN))), binWidth = top / bins;
  const counts: number[] = new Array(bins).fill(0);
  model.forEachLine((l) => {  // bin k: (k, k + 1] bin widths, 0 in the first
    const need = liftNeed(l, f.liftNoZone);
    if (need !== null) counts[Math.min(bins - 1, Math.max(0, Math.ceil(need / binWidth - 1e-9) - 1))]++;
  });
  const most = Math.max(1, ...counts);
  return <div class="r-more-sec r-lift">
    <h3>{t("ui.filter.rigging")}</h3>
    <div class="r-field-lab">{t("ui.filter.lift")}</div>
    <Segmented label={t("ui.filter.lift")} value={String(value)}
               onChange={(v) => set(model, {liftMax: Math.abs(+v - r.lift) < 1e-9 ? null : +v})}
               options={choices.map((c, k) => ({value: String(c),
                                                label: k === choices.length - 1 ? t("ui.filter.lift_axis", {m: shortMetres(c)}) : shortMetres(c)}))} />
    {r.zone > 0 && <label class="r-check"><input type="checkbox" class="u-check r-lift-nozone" checked={f.liftNoZone}
                                                 onChange={(e) => set(model, {liftNoZone: e.currentTarget.checked})} />
      {t("ui.filter.lift_no_zone")}</label>}
    <div class="u-small r-lift-count">{t("ui.filter.lift_count", {shown: model.liftCount(max, f.liftNoZone),
                                                                   total: model.count})}</div>
    <div class="r-lift-bars" aria-hidden="true">{counts.map((c, k) =>
      <i class={k === 0 || k * binWidth < max - 1e-9 ? "r-on" : ""} style={{height: `${Math.round(c / most * 100)}%`}} />)}</div>
    <div class="r-lift-axis u-small" aria-hidden="true"><span>0</span>
      <span>{t("ui.filter.lift_axis", {m: shortMetres(top)})}</span></div>
  </div>;
}

export interface MoreFiltersProps {
  model: ResultModel;
  onClose?: () => void;
  /** Show the part "Grouping" (default true; the result view leaves it out: its spots are fixed). */
  grouping?: boolean;
}

/** Every filter and the grouping of the lines. */
export function MoreFilters({model, onClose, grouping = true}: MoreFiltersProps) {
  useModel(model);
  const f = model.filters, r = model.ranges, s = model.state;
  const limit = (label: string, key: keyof Filters, range: typeof r.len, step: number, kind: "min" | "max",
                 unit = "m") => range && <Limit label={label} value={f[key] as number | null} range={range}
                                                 step={step} kind={kind} unit={unit}
                                                 onChange={(v) => set(model, {[key]: v} as Partial<Filters>)} />;
  const maxDistance = Math.max(100, Math.round(3 * model.data.distance));
  const terrain = model.data.terrain;  // the percentiles' reference (each run's lines against its own area)
  return <section class="r-more" aria-label={t("ui.filter.more")}>
    <div class="r-more-head"><b class="u-h4">{t("ui.filter.title")}</b>
      <span class="u-grow" />
      <Button kind="ghost" onClick={() => { model.setState({...s, showClean: true, showOver: true}); model.clearFilters(); }}>
        {t("ui.filter.clear_all")}</Button>
      {onClose && <CloseButton label={t("ui.filter.close")} class="r-note-x" onClick={onClose} />}
    </div>

    <div class="r-more-sec">
      <h3>{t("ui.filter.shown")}</h3>
      {model.nOver > 0 && <>
        <label class="r-check"><input type="checkbox" class="u-check" checked={s.showClean}
                                      onChange={(e) => model.setState({...s, showClean: e.currentTarget.checked})} />
          <Swatch color={COLORS.clean} /> {t("ui.filter.clear_lines", {n: model.nClean})}</label>
        <label class="r-check"><input type="checkbox" class="u-check" checked={s.showOver}
                                      onChange={(e) => model.setState({...s, showOver: e.currentTarget.checked})} />
          <Swatch color={COLORS.over} /> {t("ui.filter.over_lines", {n: model.nOver})}</label>
      </>}
      {r.favourites && <label class="r-check"><input type="checkbox" class="u-check r-fav-only" checked={f.favOnly}
                                                     onChange={(e) => set(model, {favOnly: e.currentTarget.checked})} />
        {t("ui.filter.fav_only")}</label>}
      {r.water && <label class="r-check r-select">{t("ui.filter.water")}
        <select class="u-input" value={f.water}
                onChange={(e) => set(model, {water: e.currentTarget.value as Filters["water"]})}>
          <option value="all">{t("ui.filter.water_all")}</option>
          <option value="water">{t("ui.filter.water_only")}</option>
          <option value="land">{t("ui.filter.land_only")}</option>
        </select></label>}
      {r.filled && <label class="r-check"><input type="checkbox" class="u-check" checked={f.hideFilled}
                                                 onChange={(e) => set(model, {hideFilled: e.currentTarget.checked})} />
        {t("ui.filter.hide_filled")}</label>}
    </div>

    <div class="r-more-sec">
      <h3>{t("ui.filter.sec_len")}</h3>
      {limit(t("ui.filter.len_from"), "lenMin", r.len, 1, "min")}
      {limit(t("ui.filter.len_to"), "lenMax", r.len, 1, "max")}
      {limit(t("ui.filter.clr_min"), "clrMin", r.clr, 0.1, "min")}
      {limit(t("ui.filter.clrn_min"), "clrNMin", r.clrN, 0.1, "min")}
    </div>

    <div class="r-more-sec">
      <h3>{t("ui.filter.sec_anchors")}</h3>
      {limit(t("ui.filter.dh_max"), "dhMax", r.dh, 0.5, "max")}
      {limit(t("ui.filter.elev_min"), "elevMin", r.elev, 1, "min", t("ui.filter.asl"))}
      {limit(t("ui.filter.elev_max"), "elevMax", r.elevHigh, 1, "max", t("ui.filter.asl"))}
      {terrain && <div class="u-small r-terrain">
        {parts("ui.filter.terrain", {low: num(terrain.quantiles[0]), high: num(terrain.quantiles[100]), mean: num(terrain.mean)})}
        {model.others.size > 0 && <><br />{t("ui.filter.terrain_others")}</>}</div>}
      {model.data.terrain_sources && <div class="u-small r-terrain r-shares">
        {t("ui.coarse.shares", {shares: sharesText(model.data.terrain_sources)})}</div>}
      {limit(t("ui.filter.pct_min"), "pctMin", r.pct, 1, "min", "%")}
      {limit(t("ui.filter.pct_max"), "pctMax", r.pct, 1, "max", "%")}
      {limit(t("ui.filter.angle_max"), "angleMax", r.angle, 1, "max", "°")}
      {limit(t("ui.filter.prom_min"), "promMin", r.prom, 0.5, "min")}
      {limit(t("ui.filter.prom_both_min"), "promBothMin", r.prom, 0.5, "min")}
      {limit(t("ui.filter.drop_min"), "dropMin", r.drop, 1, "min")}
    </div>

    {r.lift && <LiftFilter model={model} />}

    {(r.hmax || r.hmean || r.highPct) && <div class="r-more-sec">
      <h3>{t("ui.filter.sec_height")}</h3>
      {limit(t("ui.filter.high_min"), "heightMin", r.hmax, 1, "min")}
      {limit(t("ui.filter.mean_min"), "meanMin", r.hmean, 1, "min")}
      {limit(t("ui.filter.high_pct_min", {m: r.highAbove}), "highPctMin", r.highPct, 1, "min",
             t("ui.filter.of_line"))}
    </div>}

    {grouping && <div class="r-more-sec">
      <h3>{t("ui.filter.sec_group")}</h3>
      <label class="r-check"><input type="checkbox" class="u-check r-group" checked={s.group}
                                    onChange={(e) => model.setState({...s, group: e.currentTarget.checked})} />
        {t("ui.filter.group")}</label>
      {s.group && <>
        <Distance value={s.distance} max={maxDistance} onChange={(distance) => model.setState({...s, distance})} />
        <div class="r-field-lab">{t("ui.filter.per_spot")}</div>
        {/* four choices in two rows: in one they do not fit the list's column */}
        <div class="r-by"><Segmented label={t("ui.filter.per_spot")} value={s.by} onChange={(by) => model.setState({...s, by})}
          options={[{value: BY_MEAN, label: t("ui.filter.by_mean")}, {value: "clearance", label: t("ui.filter.by_clearance")},
                    {value: "longest", label: t("ui.filter.by_longest")}, {value: "height", label: t("ui.filter.by_height")}]} /></div>
        {limit(t("ui.filter.group_min"), "groupMin", r.group, 1, "min", "")}
      </>}
    </div>}
  </section>;
}
