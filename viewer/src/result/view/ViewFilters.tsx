// The filters of the result view (docs/line-volume/spec-view.md B.2 item 14): the chips Length (a range),
// Clearance (at least), Height (the highest point at least), "Top level only" (the view's own state, pressed at
// every run's start: SpotView.topOnly; it hides every line that hangs lower on the same face) with its info button
// held to it (step 3c: its help opens under the chips), "More filters" (today's other filters, without the grouping:
// the view's spots are fixed) and "Clear all" (which leaves "Top level only": clearAll, also the empty list's);
// under the chips the editor of a main filter (today's MainEditor) and the sentence that says what "Top level only"
// hides or shows. "Only clear" is in More filters only, and "How to read the result" is not in the view. The
// filters themselves are the ResultModel's (filters, state, ranges): the view follows them.

import { useEffect, useRef, useState } from "preact/hooks";
import { Chip, Chips, IconButton } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { active, NEED_FILTERS, NO_FILTERS, type Filters } from "../../filters";
import { t } from "../../i18n";
import type { SpotView } from "../spots";
import { count, cx, num } from "./common";
import { MainEditor, MoreFilters } from "./FilterBar";
import { FOCUS_REST, keepFocus } from "./SpotList";  // used at a press only (SpotList imports this file)
import { changePanels, panelState, type PanelState } from "./viewstate";

type Main = "len" | "clr" | "height";
const MAIN_KEYS: (keyof Filters)[] = ["lenMin", "lenMax", "clrMin", "heightMin"];

/** The filters set, without the group size (a value kept from today's page does nothing here: the spots are
 *  fixed). */
const set = (f: Filters): number => active({...f, groupMin: NO_FILTERS.groupMin});

/** The sentence under the chips: what "Top level only" hides (on) or shows too (off), of the lines that pass the
 *  other filters. */
export function topSentence(view: SpotView): string {
  const c = view.counts, one = c.topHidden === 1;  // exactly one such line: the sentence's own singular
  return view.topOnly ? t(one ? "ui.view.top_on_one" : "ui.view.top_on", {n: count(c.topHidden), m: count(c.lines + c.topHidden)})
    : t(one ? "ui.view.top_off_one" : "ui.view.top_off", {n: count(c.topHidden)});
}

/** The Length chip's words: the range, one limit, or the plain name. */
export function lengthLabel(f: Pick<Filters, "lenMin" | "lenMax">): string {
  if (f.lenMin !== null && f.lenMax !== null) return t("ui.view.chip.length_range", {a: num(f.lenMin), b: num(f.lenMax)});
  if (f.lenMin !== null) return t("ui.view.chip.length_min", {a: num(f.lenMin)});
  if (f.lenMax !== null) return t("ui.view.chip.length_max", {b: num(f.lenMax)});
  return t("ui.view.chip.length");
}

/** "Clear all": every filter of the model and both kinds of lines, each a change of the model (a pass over every line)
 *  only where it changes something, and the chip's editor closed; "Top level only" is not a filter of the model: it
 *  stays. The chips' and the empty list's (SpotList's NonePass). */
export function clearAll(view: SpotView) {
  const model = view.model, s = model.state;
  if (!s.showClean || !s.showOver) model.setState({...s, showClean: true, showOver: true});
  if (active(model.filters) > 0) model.clearFilters();
  changePanels(view, (p) => { p.editing = null; });
}

const TOP_HELP = "vl-help-top";  // the id of "Top level only"'s help text

/** The chips, the editor and the sentence; "Top level only" with its info button beside it (the two wrap together),
 *  whose help opens in place under the chips. The caller follows the view (SpotList's useViewPanels). */
export function ViewFilters({view}: {view: SpotView}) {
  const model = view.model, f = model.filters, r = model.ranges, s = model.state, ui = panelState(view);
  const [help, setHelp] = useState(false);
  const edit = (editing: PanelState["editing"]) => changePanels(view, (p) => { p.editing = editing; });
  const change = (part: Partial<Filters>) => model.setFilters({...model.filters, ...part});
  const toggle = (which: PanelState["editing"]) => edit(ui.editing === which ? null : which);
  const removed = (which: Main, part: Partial<Filters>) => {
    // its × goes with the filter: the focus to the chip itself (a button of its own now), at the same place
    const chip = document.activeElement?.closest(".vl-filters .u-chips > *");
    const at = chip?.parentElement ? Array.prototype.indexOf.call(chip.parentElement.children, chip) : -1;
    change(part);
    if (ui.editing === which) edit(null);
    keepFocus(at >= 0 ? `.vl-filters .u-chips > :nth-child(${at + 1})` : null, ".vl-filters .vl-top", ...FOCUS_REST);
  };
  /** Close the editor; the focus back to its chip when it was in the editor (Esc, ×). */
  const closeEditor = (e: Event) => {
    const bar = (e.currentTarget as HTMLElement).closest(".vl-filters");
    const chip = bar?.querySelector<HTMLElement>("[aria-expanded=true]");
    const inside = bar?.querySelector(".r-editor")?.contains(document.activeElement);
    edit(null);
    if (inside) chip?.focus();
  };
  const main = [...MAIN_KEYS, ...NEED_FILTERS].filter((k) => f[k] !== NO_FILTERS[k]).length;
  const extra = set(f) - main + (!s.showClean || !s.showOver ? 1 : 0);  // set in More filters only
  const anything = set(f) > 0 || !s.showOver || !s.showClean;
  const editing = ui.editing === "more" ? null : ui.editing;
  return <div class="r-filters vl-filters">
    <Chips>
      {r.len && <Chip on={f.lenMin !== null || f.lenMax !== null} onClick={() => toggle("len")} expanded={ui.editing === "len"}
                      onRemove={f.lenMin !== null || f.lenMax !== null ? () => removed("len", {lenMin: null, lenMax: null}) : undefined}
                      removeLabel={t("ui.view.chip.length_remove")}>{lengthLabel(f)}</Chip>}
      {r.clr && <Chip on={f.clrMin !== null} onClick={() => toggle("clr")} expanded={ui.editing === "clr"}
                      onRemove={f.clrMin !== null ? () => removed("clr", {clrMin: null}) : undefined}
                      removeLabel={t("ui.view.chip.clearance_remove")}>
        {f.clrMin !== null ? t("ui.view.chip.clearance_min", {a: num(f.clrMin, 1)}) : t("ui.view.chip.clearance")}</Chip>}
      {r.hmax && <Chip on={f.heightMin !== null} onClick={() => toggle("height")} expanded={ui.editing === "height"}
                       onRemove={f.heightMin !== null ? () => removed("height", {heightMin: null}) : undefined}
                       removeLabel={t("ui.view.chip.height_remove")}>
        {f.heightMin !== null ? t("ui.view.chip.height_min", {a: num(f.heightMin)}) : t("ui.view.chip.height")}</Chip>}
      <span class="vl-chipi">
        <button type="button" class={cx("u-chip vl-top", view.topOnly && "u-on")} aria-pressed={view.topOnly}
                title={t("ui.view.chip.top_help")} onClick={() => view.setTopOnly(!view.topOnly)}>{t("ui.view.chip.top")}</button>
        <IconButton icon="info" label={t("ui.view.chip.top_about")} plain expanded={help} aria-controls={TOP_HELP}
                    class="vl-info vl-top-info" onClick={() => setHelp(!help)} /></span>
      <Chip add icon="filter" on={ui.editing === "more" || extra > 0} onClick={() => toggle("more")}>
        {t("ui.view.chip.more")}{extra > 0 && <span class="u-badge">{extra}</span>}</Chip>
      {anything && <button type="button" class="r-link vl-clear" onClick={() => {
        clearAll(view);
        // the link goes: the focus to the chip before it, More filters
        keepFocus(".vl-filters .u-chip.u-add", ".vl-filters .vl-top", ...FOCUS_REST);
      }}>{t("ui.view.chip.clear")}</button>}
    </Chips>
    {help && <p class="vl-helpt" id={TOP_HELP}>{t("ui.view.chip.top_help")}</p>}
    {editing && <div class="r-editor" role="group" aria-label={t("ui.view.chip.editor")}
                     onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeEditor(e); } }}>
      <MainEditor model={model} which={editing} />
      <button type="button" class="r-note-x r-editor-x" aria-label={t("ui.view.chip.editor_close")} onClick={closeEditor}>
        <Icon name="close" /></button></div>}
    <p class="u-small vl-top-text">{topSentence(view)}</p>
  </div>;
}

/** "More filters" unfolded (today's, without the grouping), while its chip is pressed. */
export function ViewMoreFilters({view}: {view: SpotView}) {
  const open = panelState(view).editing === "more", mark = useRef<HTMLSpanElement>(null);
  // in the columns they stand at the top of the list's body: it scrolls there when they open
  useEffect(() => {
    const body = open && mark.current?.closest<HTMLElement>(".vl-body");
    if (body) body.scrollTop = 0;
  }, [open]);
  if (!open) return null;
  return <><span ref={mark} hidden /><MoreFilters model={view.model} grouping={false} onClose={() => changePanels(view, (p) => { p.editing = null; })} /></>;
}
