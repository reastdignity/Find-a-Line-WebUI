// The terrain profile of the selected line (or of two points measured on the map) in a dock: the
// ProfilePanel (Profile.tsx) with the profile from model.profile (saved, computed before or
// asked from the server), a loading and an error state; the point under the cursor or the finger is
// shown on the map (ProfileMap.hoverAt: ResultMap's). In a card (ProfileCard) it fills the card's height (`fill`: the
// chart takes what the bar and the controls leave) and has a fold button beside its × (`onFold`); the card's
// profile is compact: the line's facts in the bar (the full title for screen readers and tests in
// .fal-profile-title, visually hidden), the legend and the 1:1 scale under "Rigging and layers".

import { useEffect, useLayoutEffect, useState } from "preact/hooks";
import { useMedia } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { ProfilePanel } from "../../Profile";
import type { Line } from "../../types";
import type { ResultModel } from "../model";
import { cx, num, useModel } from "./common";

/** What the dock and its card need of the map: the profile's point under the cursor or the finger (null: none). */
export interface ProfileMap { hoverAt(at: [number, number] | null): void }

export interface ProfileDockProps {
  model: ResultModel;
  /** The map layer, for the point under the cursor. */
  view?: ProfileMap | null;
  /** The line whose profile is shown (default: the selected one). */
  line?: Line | null;
  /** Two points measured on the map (RunActions' onMeasured): shown instead of the line while set. */
  measured?: Line | null;
  /** The measured profile was closed (the shell clears it and ResultMap.clearMeasure). */
  onCloseMeasured?(): void;
  /** The line's profile was closed (model.closeProfile: it opens again when a line is selected). */
  onClose?(): void;
  /** The dock fills its box (a card): the chart takes the height the bar and the controls leave. */
  fill?: boolean;
  /** The compact profile (default: `fill`, the card's; the result view gives it to a phone's docks, the mock-up's 4 d):
   *  no head row in the chart, the line's title for screen readers (.fal-profile-title) and its close in the bar (in
   *  the column of the other closes: the mock-up's polish 10), the legend and the 1:1 scale under "Rigging and layers".
   *  Outside a card the facts stand in the bar only for a measured line (a line's are the details' tiles above), and
   *  the need row ("no A-frame needed" ...) and the words on reading the chart stand under the chart (polish 13; the
   *  design review's F1: the chart nearer its bar). */
  compact?: boolean;
  /** Folded to its bar (with `onFold`). */
  folded?: boolean;
  /** Given: a fold button (▾/▴) beside the ×, which then stays in the bar (the panel's own is hidden). */
  onFold?(folded: boolean): void;
  /** The dock's own state changed its content's height ("Rigging and layers", the chart replacing "Computing…"),
   *  told in a layout effect: a card measures its height again without a frame (no ResizeObserver report there);
   *  a change inside ProfilePanel (Profile.tsx) is not told. */
  onContent?(): void;
  class?: string;
}

type State = {line: Line; status: "loading"} | {line: Line; status: "error"; error: string} |
  {line: Line; status: "ready"};

/** Whether ProfileDock shows anything: two measured points, or the line (the selected one unless the
 *  profile was closed, see model.profileClosed). */
export function profileShown(model: ResultModel, measured?: Line | null, line?: Line | null): boolean {
  const target = line === undefined ? model.selected?.line || null : line;
  return !!(measured || (target && !(line === undefined && model.profileClosed)));
}

export function ProfileDock({model, view, line, measured, onCloseMeasured, onClose, fill, compact, folded, onFold, onContent,
                             class: cls}: ProfileDockProps) {
  useModel(model);
  const tight = compact ?? !!fill, docked = tight && !fill;  // compact; compact outside a card
  const target = line === undefined ? model.selected?.line || null : line;
  const [state, setState] = useState<State | null>(null);
  const [rigging, setRigging] = useState(false);
  const [title, setTitle] = useState({title: "", facts: ""});  // the compact profile's (fill)
  const touch = useMedia("(pointer: coarse)");

  useEffect(() => {
    if (!target) { setState(null); return; }
    if (target.prof) { setState({line: target, status: "ready"}); return; }
    let live = true;
    setState({line: target, status: "loading"});
    model.profile(target).then(() => { if (live) setState({line: target, status: "ready"}); },
                               (e) => { if (live) setState({line: target, status: "error", error: e.message}); });
    return () => { live = false; };
  }, [target]);
  useLayoutEffect(() => { onContent?.(); }, [rigging, state?.status]);
  useEffect(() => () => view?.hoverAt(null), [view]);
  // The point of the chart goes with its line (a new line, none, closed)
  useEffect(() => { view?.hoverAt(null); }, [target, measured, model.profileClosed]);

  // The selected line's profile follows model.profileClosed; a line given by the shell is always shown
  const shown = measured || (target && !(line === undefined && model.profileClosed) ? target : null);
  if (!shown) return null;
  const hover = (at: [number, number] | null) => view?.hoverAt(at);
  const close = () => {
    view?.hoverAt(null);
    if (measured) onCloseMeasured?.();
    else { if (line === undefined) model.closeProfile(); onClose?.(); }
    // The focus was on the profile's ×, which is gone: to the details' "Profile", which shows it again
    setTimeout(() => document.querySelector<HTMLElement>(".r-reprofile")?.focus());
  };
  const ready = measured || (state && state.line === target && state.status === "ready");
  const fold = onFold && <button type="button" class={cx("r-note-x r-fold", folded && "r-on")}
                                 aria-label={folded ? "Unfold the profile" : "Fold the profile"}
                                 title={folded ? "Unfold the profile" : "Fold the profile"} aria-expanded={!folded}
                                 onClick={() => onFold(!folded)}><Icon name="down" /></button>;
  const hint = touch ? "tap or drag along the chart" : "move the mouse along the chart";
  return <section class={cx("r-dock", rigging && "r-rigging", fill && "r-dock-fill", docked && "r-dock-compact",
                            onFold && "r-foldable", onFold && folded && "r-folded", cls)} aria-label="Profile">
    <div class="r-dock-bar">
      <b>{measured ? "Measured profile" : `Profile · ${num(shown.len)} m`}</b>
      {tight && ready && title.title && <>
        {(fill || measured) && <span class="u-small r-facts" title={title.title} aria-hidden="true">{title.facts}</span>}
        <span class="u-sr fal-profile-title">{title.title}</span></>}
      {!docked && <span class="u-small r-hint">{hint}</span>}
      <span class="u-grow" />
      {ready && <button type="button" class={cx("u-chip", rigging && "u-on")} aria-expanded={rigging}
                        onClick={() => setRigging(!rigging)}>Rigging and layers<Icon name="down" /></button>}
      {fold}
      {(!ready || onFold || tight) && <button type="button" class="r-note-x" aria-label="Close the profile" onClick={close}>
        <Icon name="close" /></button>}
    </div>
    {ready ? <div class="r-profile">
      <ProfilePanel line={shown} measured={!!measured} model={model.data.model} slope={model.data.slope}
                    leashFall={model.data.leash_fall} rigging={model.data.rigging} endZone={model.data.end_zone}
                    lift={model.data.lift} onHover={hover} onClose={close}
                    fill={fill} compact={tight} needBelow={docked}
                    onTitle={tight ? (t, facts) => setTitle((o) => o.title === t && o.facts === facts ? o
                      : {title: t, facts}) : undefined} />
    </div> : state && state.status === "error"
      ? <p class="r-dock-msg r-error"><Icon name="warn" />No profile: {state.error}</p>
      : <p class="r-dock-msg" aria-busy="true"><span class="r-spin" />Computing the terrain profile…</p>}
    {docked && ready && <p class="u-small r-hint r-hint-under">{hint}</p>}
  </section>;
}
