// The Basic tab of the search panel (docs/line-volume/spec-search.md 1.2, the accepted mock-up 1, version 3):
// above Where (BasicTop: the goals, the sea hint) and under it (BasicBottom: "Reaching the anchors", the rig in use
// with the list of the saved rigs, "Show every setting"; Where itself is the panel's, kept between the tabs); the rig's window
// (RigWindow, also opened from Advanced's "Save as a new rig") and the dialog of going back to Basic
// (ReturnDialog). Styles in search.css (s-*), the dialogs' look in app/notices.css (u-dialog).

import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { ApiError, user } from "../app/api";
import { errorText, label, t } from "../i18n";
import { Button } from "../ui/components";
import { Icon } from "../ui/icons";
import { useAccessHelp } from "../access";
import {
  BASIC_ACCESS, cleanName, nameTaken, nextRigName, RIG_FIELDS, rigDetail, rigMax, rigProblem, rigSummary, STARTING_RIG,
  valueText, type Rig, type RigField, type RigValues,
} from "./basic";
import type { ReturnAsk, SearchState } from "./useSearch";

const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");

let ids = 0;
const useId = (prefix: string) => useState(() => `${prefix}-${++ids}`)[0];

// ---- the goals ---------------------------------------------------------------------------------------

/** The goal cards: Basic's five ("Everything" across the row, with its warning) or Advanced's five and "Custom". */
export function GoalCards({s, basic}: {s: SearchState; basic?: boolean}) {
  const title = basic ? t("basic.goals") : t("hint.presets.label");
  const chosen = basic ? s.goal : s.preset;
  const cards = s.schema.presets.filter((p) => !basic || p.values);
  return <div class="s-cards" role="radiogroup" aria-label={title}>
    {cards.map((p) => {
      const everything = p.id === "everything";
      const text = !p.available ? p.reason : t(`goal.${p.id}.text`);
      return <button type="button" key={p.id} role="radio" aria-checked={p.id === chosen} data-goal={p.id}
                     class={cx("s-card", p.id === chosen && "u-on", basic && everything && "s-wide")} disabled={!p.available}
                     title={p.reason ?? undefined} onClick={() => basic ? s.chooseGoal(p.id) : s.applyPreset(p.id)}>
        <b>{p.label}{everything && <i class="s-heavy">{t("goal.heavy")}</i>}</b>
        <span>{text}{basic && everything && p.available && ` ${t("goal.everything.warning")}`}</span>
      </button>;
    })}
  </div>;
}

/** The hint under Basic's goals with "Sea cliffs": where it searches, and that another goal brings the place back. */
function SeaHint({s}: {s: SearchState}) {
  if (s.goal !== "sea") return null;
  const coast = s.mode === "cliffs" && s.coastKind === "coast";
  const before = s.seaBefore;
  return <p class="s-hint s-sea-hint">{coast ? [t("basic.sea_hint"),
    before ? t(before.mode === "point" ? "basic.sea_back_point" : "basic.sea_back_place") : ""].filter(Boolean).join(" ")
    : t("basic.sea_elsewhere")}</p>;
}

// ---- the rig in use ------------------------------------------------------------------------------------

export type RigMode = "first" | "edit" | "new";
/** What the rig's window opens with: its kind, the values it is filled with (null: the rig in use's) and whether
 *  Advanced opened it (the focus goes back there). */
export interface RigAsk { mode: RigMode; values: RigValues | null; from?: "advanced" }

/** "Rigged as": the starting rig's box ("Is this how you rig?"), or the rig in use with the list of the saved rigs. */
function RigRow({s, onOpen}: {s: SearchState; onOpen(ask: RigAsk): void}) {
  const r = s.rigs;
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const listId = useId("s-rig-list");
  const change = useRef<HTMLButtonElement>(null);
  const full = r.rigs.length >= r.max;
  const state = !r.inUse ? t("basic.rig_not_set") : full ? t("basic.rigs_full", {max: r.max})
    : r.rigs.length > 1 ? t("basic.rigs", {count: r.rigs.length}) : "";
  const saveStarting = async () => {
    setBusy(true);
    setError("");
    try {
      await r.add(t("rig.name.first"), STARTING_RIG);
      setTimeout(() => document.querySelector<HTMLButtonElement>(".s-rig-change")?.focus());
    } catch (e) {
      // the server's codes in the page's words (a list that failed to load hid a rig of that name)
      setError(e instanceof ApiError && e.info?.code === "rig_name_taken"
        ? t("rig.error.taken", {name: t("rig.name.first")}) : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return <div class="s-rig s-gap">
    <div class="u-field-lab"><span>{t("basic.rigged_as")}</span><span class="u-small s-rig-state">{state}</span></div>
    {r.inUse ? <div class="s-rig">
      <div class="s-rig-row">
        <button type="button" class="u-btn s-rig-pick u-grow" aria-expanded={open} aria-controls={listId}
                title={t("basic.choose_rig")} onClick={() => setOpen(!open)}>
          <span>{r.inUse.name}</span><Icon name="down" /></button>
        <button type="button" ref={change} class="u-btn s-rig-change" onClick={() => onOpen({mode: "edit", values: null})}>
          {t("basic.change")}</button>
      </div>
      {open && <div class="s-rig-list" id={listId}>
        {r.rigs.map((rig) => <button type="button" key={rig.id} class="s-rig-item" aria-pressed={rig.id === r.inUse!.id}
                                     data-rig={rig.id}
                                     onClick={() => { r.choose(rig.id); setOpen(false); }}>
          <b>{rig.name}</b><span>{rigSummary(rig.values)}</span></button>)}
        <button type="button" class="s-rig-item s-rig-add" disabled={full}
                onClick={() => { setOpen(false); onOpen({mode: "new", values: null}); }}>
          {full ? t("basic.rigs_ten", {max: r.max}) : t("basic.add_rig")}</button>
      </div>}
      <div><div class="s-rig-sum">{rigSummary(r.values)}</div><div class="u-small s-rig-detail">{rigDetail(r.values)}</div></div>
    </div> : <div class="s-rig-box">
      <div><div class="u-small">{t("basic.used_until")}</div>
        <div class="s-rig-sum">{rigSummary(STARTING_RIG)}</div>
        <div class="u-small s-rig-detail">{rigDetail(STARTING_RIG)}</div></div>
      <div class="s-rig-ask"><span>{t("basic.is_this_how")}</span>
        <Button disabled={busy} onClick={saveStarting}>{t("basic.yes_save")}</Button>
        <button type="button" class="u-btn s-rig-change0" onClick={() => onOpen({mode: "first", values: null})}>
          {t("basic.change")}</button></div>
    </div>}
    {(error || r.error) && <p class="s-problem s-rig-error" role="alert">
      {error || t("basic.rigs_error", {message: r.error})}</p>}
  </div>;
}

/** The Basic tab above Where (the panel keeps Where itself between the tabs' parts, so a tab switch keeps it). */
export function BasicTop({s}: {s: SearchState}) {
  return <>
    <h2 class="u-h">{t("basic.goals")}</h2>
    <GoalCards s={s} basic />
    <SeaHint s={s} />
  </>;
}

/** "Reaching the anchors": Basic marks the access to every anchor (basic.ts BASIC_ACCESS); the row says so and its
 *  "?" opens the help the result page shares (access.tsx). Not shown where the site's limits leave the field out. */
function AccessRow({s}: {s: SearchState}) {
  const help = useAccessHelp();
  if (!s.byName[BASIC_ACCESS]) return null;
  return <div class="s-access s-gap">
    <div class="u-field-lab"><span class="u-field-name">{t("basic.access.label")}{help.button}</span></div>
    <p class="s-note">{t("basic.access.note")}</p>
    {help.panel}
  </div>;
}

/** The Basic tab under Where: "Reaching the anchors", the rig in use, "Show every setting". */
export function BasicBottom({s, onRig, onEvery}: {s: SearchState; onRig(ask: RigAsk): void; onEvery(): void}) {
  return <>
    <AccessRow s={s} />
    <RigRow s={s} onOpen={onRig} />
    <div><button type="button" class="s-link s-every" onClick={onEvery}>{t("basic.show_every")}<Icon name="next" /></button></div>
  </>;
}

// ---- dialogs -----------------------------------------------------------------------------------------------

/** A native modal <dialog> while mounted (Esc and a press outside call onClose), its own .ui root with the shell's
 *  theme (as ui/Intro.tsx). When it goes the focus goes to `focusAfter()`'s element, else back to where it was
 *  (read when it goes: the page under it is drawn by then, so a button that replaced the opener is there). */
function Modal({onClose, label: labelledBy, class: cls, focusAfter, children}:
               {onClose(): void; label: string; class?: string; focusAfter?: () => Element | null;
                children: ComponentChildren}) {
  const ref = useRef<HTMLDialogElement>(null);
  const after = useRef(focusAfter);
  after.current = focusAfter;
  useEffect(() => {
    const dialog = ref.current!;
    const back = document.activeElement as HTMLElement | null;
    const theme = dialog.parentElement?.closest(".ui[data-theme]")?.getAttribute("data-theme");
    if (theme) dialog.setAttribute("data-theme", theme);
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      const target = (after.current?.() as HTMLElement | null) ?? (back && document.contains(back) ? back : null);
      target?.focus();
      // The browser may move the focus to the page once the dialog leaves it: once more then, if it did
      setTimeout(() => { if (!document.activeElement || document.activeElement === document.body) target?.focus(); });
    };
  }, []);
  // A press outside: one that starts and ends on the backdrop (the dialog's own box, outside its rectangle); a
  // selection of a field's text let go over the backdrop is a click on the dialog too, but it started inside
  const onBackdrop = (e: MouseEvent | PointerEvent) => {
    if (e.target !== e.currentTarget) return false;
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
  };
  const pressed = useRef(false);  // the last press started on the backdrop
  return <dialog ref={ref} class={cx("ui u-dialog s-dialog", cls)} aria-labelledby={labelledBy}
                 onCancel={(e) => { e.preventDefault(); onClose(); }}
                 onPointerDown={(e) => { pressed.current = onBackdrop(e); }}
                 onClick={(e) => { if (pressed.current && onBackdrop(e)) onClose(); pressed.current = false; }}>
    {children}
  </dialog>;
}

/** A number of a field of the rig's window, read as typed (empty: not a number). */
const readNumber = (text: string) => text.trim() === "" ? NaN : Number(text);

/** The rig's window: "My rig" (no rig saved yet), "Change a rig" (the rig in use: rename, change, save as a new
 *  rig, delete) or "A new rig". Esc, Cancel or a press outside close it unsaved. */
export function RigWindow({s, ask, onClose}: {s: SearchState; ask: RigAsk; onClose(): void}) {
  const r = s.rigs;
  // the rig being changed, as it was when the window opened (the list may change under it: a rig deleted elsewhere)
  const [editing] = useState<Rig | null>(() => ask.mode === "edit" ? r.inUse : null);
  const from = ask.values ?? (editing ? editing.values : r.values);
  const titleId = useId("s-rig-title");
  const [name, setName] = useState(editing ? editing.name : nextRigName(r.rigs));
  const [draft, setDraft] = useState<Record<string, number>>({...from});
  const [problem, setProblem] = useState("");
  const [asking, setAsking] = useState(false);  // "Delete “name”?"
  const [busy, setBusy] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const zoneRef = useRef<HTMLInputElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const deleteRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (ask.mode === "new") { nameRef.current?.focus(); nameRef.current?.select(); } else zoneRef.current?.focus();
  }, []);
  useEffect(() => { if (asking) keepRef.current?.focus(); }, [asking]);

  const full = r.rigs.length >= r.max;
  const tenth = !editing && r.rigs.length === r.max - 1;
  const set = (k: string) => (e: Event) => setDraft((d) => ({...d, [k]: readNumber((e.currentTarget as HTMLInputElement).value)}));
  const save = async (copy: boolean) => {
    const clean = cleanName(name);
    const values = Object.fromEntries(RIG_FIELDS.map((k) => [k, draft[k]])) as RigValues;
    const own = editing && !copy ? editing.id : null;
    let wrong = !clean ? t("rig.error.no_name") : rigProblem(values, s.byName);
    if (!wrong && nameTaken(r.rigs, clean, own)) {
      wrong = copy ? t("rig.error.copy_taken", {name: clean}) : t("rig.error.taken", {name: clean});
    }
    if (!wrong && own === null && full) wrong = t("error.rigs_max", {max: r.max});
    if (wrong) { setProblem(wrong); return; }
    setBusy(true);
    setProblem("");
    try {
      if (own !== null) await r.change(own, {name: clean, values});
      else await r.add(clean, values);
      onClose();
    } catch (e) {
      const code = e instanceof ApiError ? e.info?.code : undefined;
      setProblem(code === "rig_name_taken" ? t(copy ? "rig.error.copy_taken" : "rig.error.taken", {name: clean})
        : code ? errorText(e instanceof ApiError && e.info ? e.info : {code}, (e as Error).message) : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      await r.remove(editing.id);
      onClose();
    } catch (e) {
      setProblem((e as Error).message);
      setAsking(false);
    } finally {
      setBusy(false);
    }
  };

  // the bounds on the inputs: 0 and the site's (or SearchParams') highest value, as the form's own fields
  const number = (k: RigField, unit: string, extra?: ComponentChildren, ref?: typeof zoneRef) => {
    const id = `${titleId}-${k}`;
    return <>
      <label for={id}>{label(k)}{extra && <span class="s-fx">{extra}</span>}</label>
      <span class="s-unit-box" style={{"--s-unit": `${[...unit].length}ch`}}>
        <input id={id} ref={ref} class="u-input" type="number" step="any" inputmode="decimal" data-rig-field={k}
               min={0} max={rigMax(k, s.byName)}
               defaultValue={Number.isFinite(from[k]) ? String(from[k]) : ""}
               onInput={set(k)} onChange={set(k)} />
        <span class="s-unit">{unit}</span></span>
    </>;
  };
  const cost = [t("rig.cost.sag"), draft.end_zone > 0 && t("rig.cost.zone"), draft.anchor_lift > 0 && t("rig.cost.lift")]
    .filter(Boolean).join(" ");
  // The focus back on Basic's "Change" (the one of the rig's row now: a first rig saved, the last deleted), or on
  // Advanced's button that opened it
  const focusAfter = () => ask.from === "advanced" ? null : document.querySelector(".s-rig-change, .s-rig-change0");
  return <Modal onClose={onClose} label={titleId} class="s-rig-dialog" focusAfter={focusAfter}>
    <form class="s-rig-form" noValidate onSubmit={(e) => { e.preventDefault(); save(false); }}>
      <h2 class="u-h" id={titleId}>{t(editing ? "rig.title.edit" : ask.mode === "new" ? "rig.title.new" : "rig.title.first")}</h2>
      <p class="s-note">{t("rig.intro")}</p>
      <div class="u-field">
        <div class="u-field-lab"><span class="u-field-name"><label for={`${titleId}-name`}>{t("rig.name")}</label></span></div>
        <input id={`${titleId}-name`} ref={nameRef} class="u-input" type="text" maxLength={30} autocomplete="off"
               value={name} onInput={(e) => setName(e.currentTarget.value)} />
      </div>
      <div class="s-rig-grid">
        {number("end_zone", "m", t("rig.fx.zone"), zoneRef)}
        {number("anchor_lift", "m", t("rig.fx.lift"))}
        {number("fall_zone", "m")}
      </div>
      <details class="s-rig-more">
        <summary>{t("rig.more")}</summary>
        <div class="s-rig-grid">
          {number("pretension", "kN")}
          {number("stretch", "%")}
          {number("webbing_weight", "g/m")}
          {number("athlete_mass", "kg")}
        </div>
      </details>
      <p class="s-rig-cost">{cost}</p>
      {problem && <p class="s-problem s-rig-problem" role="alert">{problem}</p>}
      {(full || tenth) && <p class="u-small">{t(full ? "rig.limit_full" : "rig.limit_tenth", {max: r.max})}</p>}
      <p class="u-small">{t(user.local ? "rig.stored_local" : "rig.stored_account")}</p>
      {asking ? <div class="n-actions s-rig-foot">
        <span class="u-grow s-note" role="alert" id={`${titleId}-ask`}>
          {t(r.rigs.length === 1 ? "rig.delete_ask_last" : "rig.delete_ask", {name: editing!.name})}</span>
        <button type="button" ref={keepRef} class="u-btn" aria-describedby={`${titleId}-ask`}
                onClick={() => { setAsking(false); setTimeout(() => deleteRef.current?.focus()); }}>
          {t("rig.keep")}</button>
        <Button kind="danger" disabled={busy} onClick={remove}>{t("rig.delete_yes")}</Button>
      </div> : <div class="n-actions s-rig-foot">
        {editing && <button type="button" ref={deleteRef} class="u-btn u-danger s-left" onClick={() => setAsking(true)}>
          {t("rig.delete")}</button>}
        <Button onClick={onClose}>{t("rig.cancel")}</Button>
        {editing && !full && <Button disabled={busy} onClick={() => save(true)}>{t("rig.save_copy")}</Button>}
        <Button kind="primary" type="submit" disabled={busy}>
          {busy ? t("rig.saving") : t(editing ? "rig.save" : "rig.save_first")}</Button>
      </div>}
    </form>
  </Modal>;
}

/** Going back to Basic with values it cannot show: the list in words, "Stay in Advanced" (focused) or "Reset
 *  them to Basic's values". */
export function ReturnDialog({s, ask, onClose}: {s: SearchState; ask: ReturnAsk; onClose(): void}) {
  const titleId = useId("s-return-title");
  const stay = useRef<HTMLButtonElement>(null);
  const tabAfter = useRef<string | null>(null);  // the tab whose button gets the focus: Stay's Advanced
  useEffect(() => { stay.current?.focus(); }, []);
  const goal = s.goalOf(ask.goal);
  const rig = s.rigs.inUse;
  const basic = `${goal?.label ?? ask.goal}; ${rig ? `${rig.name}: ` : ""}${rigSummary(s.rigs.values, true, ", ")}`;
  const focusAfter = () => tabAfter.current ? document.querySelector(`.s-tabs [data-tab="${tabAfter.current}"]`) : null;
  return <Modal onClose={onClose} label={titleId} class="s-return-dialog" focusAfter={focusAfter}>
    <h2 class="u-h" id={titleId}>{t("basic.return_title", {count: ask.fields.length})}</h2>
    <ul>{ask.fields.map((k) => <li key={k}>{s.byName[k] ? valueText(s.byName[k], s.resolved[k]) : k}</li>)}</ul>
    <p class="s-note">{t("basic.return_note", {basic})}</p>
    <div class="n-actions">
      <button type="button" ref={stay} class="u-btn u-pri" onClick={() => { tabAfter.current = "advanced"; onClose(); }}>
        {t("basic.return_stay")}</button>
      <Button onClick={() => { s.resetToBasic(ask.goal); onClose(); }}>{t("basic.return_reset")}</Button>
    </div>
  </Modal>;
}
