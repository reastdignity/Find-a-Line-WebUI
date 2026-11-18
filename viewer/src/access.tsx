// The access mark (docs/line-volume/spec-search.md 3; the search's --access, access.py): whether a person can walk
// to an anchor, one of three states per anchor (types.ts ACCESS_HARD 0, ACCESS_CANNOT_TELL 1, ACCESS_EASY 2; null:
// a run made without the mark). Shown as a dot in the state's colour with its sign (ui/icons.tsx ACCESS_SIGNS): in
// the rows of the result's list (two dots: anchor 1, anchor 2), a line's details, the legend, on the map at the
// selected line's two anchors (accessMarkSvg), and in the key of the one help text that the result page and the
// search form share (AccessKey; useAccessHelp: its "?" and the panel it opens in place). The mark hides and sorts
// nothing. Styles in access.css (ac-*), the colours in ui/tokens.css (--acc-*).

import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import { t } from "./i18n";
import { ACCESS_CANNOT_TELL, ACCESS_EASY, ACCESS_HARD, type Line } from "./types";
import { ACCESS_SIGNS, Icon } from "./ui/icons";
import "./access.css";

/** The mark's values, the best first: the order of the legend and the key. */
export const ACCESS_STATES = [ACCESS_EASY, ACCESS_CANNOT_TELL, ACCESS_HARD] as const;
const WORDS: Record<number, string> = {[ACCESS_EASY]: "ui.access.easy", [ACCESS_CANNOT_TELL]: "ui.access.cannot_tell",
                                       [ACCESS_HARD]: "ui.access.hard"};
const MEANS: Record<number, string> = {[ACCESS_EASY]: "ui.access.easy_means",
                                       [ACCESS_CANNOT_TELL]: "ui.access.cannot_tell_means",
                                       [ACCESS_HARD]: "ui.access.hard_means"};

/** A line's value of the mark as a state, or null: no mark (a run made without it, a value this page does not know). */
export function accessState(value: number | null | undefined): number | null {
  return value === ACCESS_EASY || value === ACCESS_CANNOT_TELL || value === ACCESS_HARD ? value : null;
}

/** Does a line carry the mark at an anchor. */
export const hasAccess = (l: Pick<Line, "access1" | "access2">): boolean =>
  accessState(l.access1) !== null || accessState(l.access2) !== null;

/** A state's words: "easy access", "cannot tell", "hard access". */
export const accessWord = (state: number): string => t(WORDS[state]);

const escape = (text: string) => text.replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]!));

/** The dot's content: its title, its circle and the state's sign (static markup: safe as innerHTML under the CSP). */
function dotMarkup(state: number, label: string, r = 7.5): string {
  return `<title>${escape(label)}</title><circle class="ac-f" cx="8" cy="8" r="${r}"/>${ACCESS_SIGNS[state] ?? ""}`;
}

/** The mark as a dot of 20 px (a row, the details, the legend, the key); `label`: what a screen reader hears and the
 *  mouse shows (default: the state's words). */
export function AccessMark({state, label}: {state: number; label?: string}) {
  const text = label ?? accessWord(state);
  return <svg class={`ac ac-${state}`} viewBox="0 0 16 16" role="img" aria-label={text}
              dangerouslySetInnerHTML={{__html: dotMarkup(state, text)}} />;
}

/** The two dots of a line (anchor 1, anchor 2); "–" for a line without the mark (a list that mixes runs made with
 *  and without it). */
export function AccessPair({line: l}: {line: Pick<Line, "access1" | "access2">}) {
  const states = [accessState(l.access1), accessState(l.access2)];
  // "–" has a name of its own for a screen reader (a title alone is not read out)
  if (states[0] === null && states[1] === null) {
    return <span class="ac-none" role="img" aria-label={t("ui.access.none")} title={t("ui.access.none")}>–</span>;
  }
  return <span class="ac-pair">{states.map((state, k) => state === null
    ? <span class="ac-none" key={k} role="img" aria-label={t("ui.access.anchor_none", {n: k + 1})}>–</span>
    : <AccessMark key={k} state={state} label={t("ui.access.anchor_state", {n: k + 1, state: accessWord(state)})} />)}</span>;
}

/** The mark on the map (ResultMap: a marker's icon of MAP_MARK px at an anchor of the selected line) as markup: a
 *  thin dark edge, a white ring and the dot, in the map's colours (the tiles stay light in the dark theme). */
export const MAP_MARK = 24;
export function accessMarkSvg(state: number, label: string): string {
  return `<svg class="ac-map ac-${state}" viewBox="-1.6 -1.6 19.2 19.2" width="${MAP_MARK}" height="${MAP_MARK}" ` +
    `role="img" aria-label="${escape(label)}"><circle class="ac-edge" cx="8" cy="8" r="9.6"/>` +
    `<circle class="ac-ring" cx="8" cy="8" r="8.9"/>${dotMarkup(state, label, 7.7)}</svg>`;
}

/** The help's content: what each state means (the key), then what the site judges from and what it cannot see. */
export function AccessKey() {
  return <>
    <div class="ac-key">{ACCESS_STATES.map((state) => <div class="ac-key-row" key={state}>
      <AccessMark state={state} /><span><b>{accessWord(state)}:</b> {t(MEANS[state])}</span></div>)}</div>
    <p>{t("ui.access.help")}</p>
  </>;
}

let ids = 0;

/** The "?" of the mark and the help it opens in place (a panel under the row that holds the button, not a bubble:
 *  the text is long, and its key shows the dots on the panel's own surface): `button` goes into the row, `panel`
 *  (null while closed) where the text should stand. Esc closes it while the focus is on the button. */
export function useAccessHelp(label = t("ui.access.about"), icon = false): {button: ComponentChildren; panel: ComponentChildren} {
  const [id] = useState(() => `ac-help-${++ids}`);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || (document.activeElement as HTMLElement | null)?.getAttribute("aria-controls") !== id) return;
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    };
    document.addEventListener("keydown", key, true);
    return () => document.removeEventListener("keydown", key, true);
  }, [open]);
  const toggle = (e: Event) => { e.stopPropagation(); setOpen(!open); };
  return {
    // `icon`: the kit's "info" icon in a button of the kit (the result view's, where "?" is the mark's "cannot tell")
    button: icon
      ? <button type="button" class="u-ib u-plain ac-hint ac-info" aria-label={label} title={label} aria-expanded={open} aria-controls={id}
                onClick={toggle}><Icon name="info" /></button>
      : <button type="button" class="u-hint ac-hint" aria-label={label} aria-expanded={open} aria-controls={id}
                onClick={toggle}>?</button>,
    panel: open ? <div class="ac-help" id={id} role="note"><AccessKey /></div> : null,
  };
}
