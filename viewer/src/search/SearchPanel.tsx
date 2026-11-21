// The search panel: the switch "Basic · Advanced" (docs/line-volume/spec-search.md 1.2). Basic (BasicPane.tsx):
// the goals, Where, "Reaching the anchors" (the access mark, on in Basic), the rig in use. Advanced: Where, the run's name, the goals as cards with "Custom", the key
// fields and "More settings" by topic, a dot on every value that differs from Basic's ("reset" puts Basic's back)
// and, in "Clearance model", the rigging saved as a rig. Where (Point · Area · Along cliffs · File) is one block
// shown in either tab. The bar with the size word, the receipt and the start is a bar of its own (EstimateBar),
// which the page places under the panel (NewSearch's bottom bar). UsageMeters shows the user's quotas;
// SearchIntro, "How a search works", opens from its link. Styles in search.css (s-*), under the kit's .ui root.

import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { Field as SchemaField, Usage, UsageItem } from "../app/api";
import { parseValue, withValue } from "../app/request";
import { errorText, label, parts as textParts, t } from "../i18n";
import { Button, Field, Hint, Progress, Range, RangePair, Segmented, TOUCH, useMedia, type Option } from "../ui/components";
import { Icon } from "../ui/icons";
import { IntroLink, useIntro } from "../ui/Intro";
import { useAccessHelp } from "../access";
import { accessSkipped, BASIC_ACCESS, differing, receiptParts, receiptShort, rigOf, rigProblem, sameRig, sizeOf, withBasicValue } from "./basic";
import { BasicBottom, BasicTop, GoalCards, ReturnDialog, RigWindow, type RigAsk } from "./BasicPane";
import { PlaceBox } from "./PlaceBox";
import { SearchIntro } from "./SearchIntro";
import { fmt, KEY_FIELDS, withinLimits, type ReturnAsk, type SearchMode, type SearchState } from "./useSearch";
import "./search.css";

const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");

/** The modes of Where; on a phone "Along cliffs" is "Cliffs". */
const modes = (phone?: boolean): Option<SearchMode>[] => [
  {value: "point", label: t("ui.search.mode_point"), icon: "pin"}, {value: "area", label: t("ui.search.mode_area"), icon: "poly"},
  {value: "cliffs", label: t(phone ? "ui.search.mode_cliffs_short" : "intro.search.mode_cliffs"), icon: "cliff"},
  {value: "file", label: t("ui.search.mode_file"), icon: "file"},
];

let ids = 0;
const useId = (prefix: string) => useState(() => `${prefix}-${++ids}`)[0];

const unitOf = (name: string) => t(`field.${name}.unit`);

/** A value with its unit as the hints write it ("30°", "5 %", "200 m"). */
const withUnit = (value: number, unit: string) => unit === "°" ? `${value}°` : unit ? `${value} ${unit}` : String(value);

/** The site's bounds in words (hint.bounds.*), "" without any; `factor`: at least this many times
 *  the grid size (--group-distance). */
function boundsText(low: number | null | undefined, high: number | null | undefined, unit: string,
                    factor?: number | null): string {
  if (factor) return t("hint.bounds.factor", {factor});
  const min = low ?? null, max = high ?? null;
  if (min !== null && max !== null) return t("hint.bounds.both", {min: withUnit(min, unit), max: withUnit(max, unit)});
  if (min !== null) return t("hint.bounds.min", {min: withUnit(min, unit)});
  if (max !== null) return t("hint.bounds.max", {max: withUnit(max, unit)});
  return "";
}

/** The "?" text of a field: its hint from the catalogue (or `key`'s) and the site's bounds. */
const hintOf = (field: SchemaField, key = `field.${field.name}.help`) =>
  [t(key), boundsText(field.min, field.max, unitOf(field.name), field.min_factor)].filter(Boolean).join(" ");

// ---- where -----------------------------------------------------------------------------------

function BufferField({s}: {s: SearchState}) {
  const field = s.byName.buffer;
  const id = useId("s-buffer");
  if (!field) return null;
  const max = Math.max(field.max ?? 1000, s.buffer);
  return <Field label={label("buffer")} value={`${s.buffer} m`} htmlFor={id} hint={hintOf(field)}>
    <Range id={id} label={label("buffer")} value={s.buffer} min={10} max={max} step={10} onInput={s.setBuffer} />
  </Field>;
}

/** Where a search goes: one block, shown in Basic and in Advanced. */
function Where({s, phone}: {s: SearchState; phone?: boolean}) {
  const radiusField = s.byName.radius;
  const id = useId("s-where");
  const touch = useMedia(TOUCH);  // a tap, not a click, on a touch screen
  const placed = !!(s.point || s.shapes > 0 || s.file || s.osmName || s.within || s.name);  // what clear() empties
  const where = useRef<HTMLDivElement>(null);
  // The button goes with what it cleared, so the focus moves within the block, never to the page: where the pointer
  // is fine to its first control (the place box); on a touch screen to the chosen "Where" mode however the button was
  // pressed (a tap, a key, a screen reader's activation, which Chromium sends as a click of detail 0 like a key), as a
  // focused text field would open the on-screen keyboard
  const clear = () => {
    s.clear();
    where.current?.querySelector<HTMLElement>(touch ? "[role=radio][aria-checked=true]" : "input, button")?.focus();
  };
  const areas = s.shapes > 0 && <p class="s-hint s-areas">
    {t("ui.search.areas", {count: s.areas})}
    {s.shapes !== s.areas && ` ${t("ui.search.shapes", {count: s.shapes})}`}</p>;
  return <div class="s-where" ref={where}>
    {s.mode !== "file" && <PlaceBox place={s.place} />}
    <Segmented label={t("basic.where")} options={modes(phone)} value={s.mode} onChange={s.setMode} />
    {s.mode === "point" && <>
      <p class="s-hint s-point">{s.point ? <><Icon name="pin" />{textParts("ui.search.centre", {lat: s.point[0].toFixed(5), lon: s.point[1].toFixed(5)})}
        {"; "}{touch ? t("ui.search.point_move_touch") : t("ui.search.point_move")}</>
        : touch ? t("ui.search.point_hint_touch") : t("ui.search.point_hint")}</p>
      {radiusField && <Field label={label("radius")} value={`${s.radius} m`} htmlFor={id} hint={hintOf(radiusField)}>
        <Range id={id} label={label("radius")} value={s.radius} min={50} step={50}
               max={Math.max(radiusField.max ?? 5000, s.radius)} onInput={s.setRadius} />
      </Field>}
    </>}
    {s.mode === "area" && <>
      <Segmented label={t("ui.search.mode_area")} value={s.areaKind} onChange={s.setAreaKind}
                 options={[{value: "draw", label: t("ui.search.area_draw")}, {value: "osm", label: t("ui.search.area_osm")}]} />
      {s.areaKind === "draw" ? <>
        <p class="s-hint">{t("ui.search.draw_hint")}</p>
        {areas}
        <BufferField s={s} />
      </> : <Field label={t("hint.area_name.label")} htmlFor={id} hint={t("hint.area_name.help")}>
        <input id={id} class="u-input" type="text" value={s.osmName} placeholder={t("ui.search.osm_placeholder")}
               onInput={(e) => s.setOsmName(e.currentTarget.value)} />
      </Field>}
    </>}
    {s.mode === "cliffs" && <>
      <Segmented label={t("ui.search.along")} value={s.coastKind} onChange={s.setCoastKind}
                 options={[{value: "cliffs", label: t("ui.search.cliffs")}, {value: "coast", label: t("intro.search.coast")}]} />
      <Field label={label("within")} htmlFor={id}
             hint={s.byName.within ? hintOf(s.byName.within) : t("field.within.help")}>
        <div class="s-within">
          <input id={id} class="u-input" type="text" value={s.within} placeholder={t("ui.search.within_placeholder")}
                 onInput={(e) => s.setWithin(e.currentTarget.value)} />
          <Button onClick={() => s.setWithin(s.place.viewBox())}>{t("ui.search.map_view")}</Button>
        </div>
      </Field>
      <BufferField s={s} />
    </>}
    {s.mode === "file" && <>
      <Field label={t("hint.area_file.label")} htmlFor={id} hint={t("hint.area_file.help")}
             help={s.file && t("ui.search.file_shapes", {file: s.file.name, n: s.file.areas.features.length})}>
        <input id={id} key={s.fileKey} class="s-file" type="file" accept=".geojson,.json,.kml,.gpx"
               onChange={(e) => s.readFile(e.currentTarget)} />
      </Field>
      {areas}
      <BufferField s={s} />
    </>}
    {placed && <div class="s-row-end">
      <Button kind="ghost" icon="close" onClick={clear}>{t("ui.search.clear")}</Button>
    </div>}
  </div>;
}

// ---- Advanced: the goal cards, the key fields, the dots ---------------------------------------

/** A field's label with Advanced's dot when its value differs from Basic's. */
const Dotted = ({on, children}: {on: boolean; children: string}) => <span class={cx(on && "s-changed")}>{children}</span>;

/** "reset": Basic's value back, the focus to the field. */
function ResetButton({s, names, focusId}: {s: SearchState; names: string[]; focusId?: string}) {
  if (!names.some((n) => s.differs(n))) return null;
  return <button type="button" class="s-reset" title={t("basic.reset_title")}
                 onClick={() => {
                   s.setValues(names.reduce((v, n) => withBasicValue(v, n, s.base, s.defaults), s.values));
                   // the button goes with the change: the focus to the field
                   if (focusId) setTimeout(() => document.getElementById(focusId)?.focus());
                 }}>{t("basic.reset")}</button>;
}

function KeyFields({s}: {s: SearchState}) {
  const {byName} = s;
  const low = Number(s.value("min_length")), high = Number(s.value("max_length"));
  const diff = Number(s.value("max_anchor_diff_m"));
  const lengthMax = Math.max(byName.max_length?.max ?? 1000, high);
  const diffMax = Math.max(100, diff);
  const source = byName.source;
  const sourceId = useId("s-source");
  return <div class="s-keys">
    {byName.min_length && byName.max_length && <div data-field="min_length"><Field
      label={<Dotted on={s.differs("min_length") || s.differs("max_length")}>{t("hint.length.label")}</Dotted>}
      hintLabel={t("hint.length.label")}
      hint={[t("hint.length.help"), boundsText(byName.min_length.min, byName.max_length.max, "m")].filter(Boolean).join(" ")}
      value={<>{`${low} – ${high} m`} <ResetButton s={s} names={["min_length", "max_length"]} /></>}
      help={s.problems.min_length && <span class="s-problem">{s.problems.min_length}</span>}>
      <RangePair label={t("hint.length.label")} low={low} high={high} min={5} max={lengthMax} step={5}
                 onInput={(a, b) => s.setValues(withLengths(s, a, b))} />
    </Field></div>}
    {byName.max_anchor_diff_m && <div data-field="max_anchor_diff_m"><Field
      label={<Dotted on={s.differs("max_anchor_diff_m")}>{label("max_anchor_diff_m")}</Dotted>}
      hintLabel={label("max_anchor_diff_m")} hint={hintOf(byName.max_anchor_diff_m)}
      value={<>{t("basic.diff_value", {diff})} <ResetButton s={s} names={["max_anchor_diff_m"]} /></>}>
      <Range label={label("max_anchor_diff_m")} value={diff} min={0} max={diffMax} step={1}
             onInput={(v) => s.setValue("max_anchor_diff_m", v)} />
    </Field></div>}
    {source && <div data-field="source"><Field label={<Dotted on={s.differs("source")}>{label("source")}</Dotted>} htmlFor={sourceId}
                      hintLabel={label("source")} hint={hintOf(source)}
                      value={<ResetButton s={s} names={["source"]} focusId={sourceId} />}
                      help={<a class="s-help-link" href="/coverage" target="_blank" rel="noopener">{t("ui.coverage.where")}</a>}>
      <select id={sourceId} class="u-input" value={String(s.value("source"))}
              onChange={(e) => s.setValue("source", e.currentTarget.value)}>
        {source.choices!.map((c) => <option value={c}>{source.choice_labels?.[c] ?? c}</option>)}
      </select>
    </Field></div>}
  </div>;
}

/** The changed values with a new length range (a value equal to the default is not kept). */
function withLengths(s: SearchState, low: number, high: number): Record<string, unknown> {
  return withValue(withValue(s.values, s.byName.min_length, low), s.byName.max_length, high);
}

// ---- more settings ---------------------------------------------------------------------------

function ParamInput({field, value, onChange, id, invalid}:
                    {field: SchemaField; value: unknown; onChange(v: unknown): void; id: string; invalid: boolean}) {
  const shown = value === undefined ? field.default : value;
  if (field.type === "boolean") {
    return <input id={id} type="checkbox" class="s-check" checked={!!shown} onChange={(e) => onChange(e.currentTarget.checked)} />;
  }
  if (field.type === "choice") {
    return <select id={id} class="u-input" value={shown === null || shown === undefined ? "" : String(shown)}
                   onChange={(e) => onChange(e.currentTarget.value === "" ? null : e.currentTarget.value)}>
      {field.optional && <option value="">{t("ui.search.default_option")}</option>}
      {field.choices!.map((c) => <option value={c}>{field.choice_labels?.[c] ?? c}</option>)}
    </select>;
  }
  const text = shown === null || shown === undefined ? "" : String(shown);
  const changed = (e: Event) => onChange(parseValue(field, (e.currentTarget as HTMLInputElement).value));
  // A number field keeps what is being typed (defaultValue, read when it is left: the page is drawn
  // again on every event of the queue); a new value from elsewhere (reset) gives it a new key
  const unit = unitOf(field.name);
  const unitId = unit ? `${id}-unit` : undefined;
  const input = field.type === "number" || field.type === "integer"
    ? <input id={id} key={`${field.name}:${text}`} class={cx("u-input", invalid && "s-invalid")} type="number"
             step={field.type === "integer" ? 1 : "any"} defaultValue={text} min={field.min ?? undefined}
             max={field.max ?? undefined} placeholder={field.optional ? t("ui.search.default_placeholder") : ""} onChange={changed}
             aria-invalid={invalid || undefined} aria-describedby={unitId} />
    : <input id={id} class="u-input" type="text" value={text} placeholder={field.optional ? t("ui.search.default_placeholder") : ""}
             onInput={changed}
             aria-describedby={unitId} />;
  if (!unit) return input;
  // The unit at the right end of the box (not in the label); the text stays clear of it (--s-unit: its width)
  return <span class="s-unit-box" style={{"--s-unit": `${[...unit].length}ch`}}>
    {input}<span class="s-unit" id={unitId}>{unit}</span>
  </span>;
}

function Setting({s, field}: {s: SearchState; field: SchemaField}) {
  const id = useId("s-f");
  const changed = s.differs(field.name);
  const problem = s.problems[field.name];
  // The access mark's "?" opens the help it shares with Basic's row and the result page (the key of the three
  // states), in place under the field, not the bubble of the field's own hint
  const access = field.name === BASIC_ACCESS;
  const help = useAccessHelp(t("hint.about", {label: label(field.name)}));
  return <div class={cx("s-setting", changed && "s-is-changed")} data-field={field.name}>
    <Field htmlFor={id} label={<Dotted on={changed}>{label(field.name)}</Dotted>}
           hintLabel={label(field.name)} hint={access ? undefined : hintOf(field)}
           hintButton={access ? help.button : undefined}
           value={<ResetButton s={s} names={[field.name]} focusId={id} />}
           help={problem && <span class="s-problem">{problem}</span>}>
      <ParamInput id={id} field={field} value={s.values[field.name]} invalid={!!problem}
                  onChange={(v) => s.setValue(field.name, v)} />
    </Field>
    {access && help.panel}
  </div>;
}

/** "Clearance model" ends with the rigging shown saved as a rig: into the rig in use (at once), or as a new rig
 *  (the rig's window, filled). */
function SaveRig({s, onRig}: {s: SearchState; onRig(ask: RigAsk): void}) {
  const r = s.rigs;
  const shown = rigOf(s.resolved);
  const same = r.inUse ? sameRig(shown, r.inUse.values) : false;
  const full = r.rigs.length >= r.max;
  const [message, setMessage] = useState("");
  const key = JSON.stringify(shown);
  useEffect(() => setMessage(""), [key]);  // a new value: the last save's words go (not when the rig in use changes)
  const into = async () => {
    const problem = rigProblem(shown, s.byName);
    if (problem) { setMessage(problem); return; }
    const target = r.inUse!;
    try {
      await r.change(target.id, {values: shown});
      setMessage(t("basic.saved_into", {name: target.name}));
    } catch (e) {
      setMessage((e as Error).message);  // a coded answer: its text from the catalogue (ApiError, i18n.detailMessage)
    }
  };
  // The rig in use gone (deleted on another device: "rig_missing" reloads the list, or found so when the page
  // loaded): another rig stands in for Basic, but "Save into" stays off until the user chooses a rig in Basic, so a
  // save never moves to a rig the user did not pick
  const lost = r.lost;
  const asNew = () => {
    const problem = rigProblem(shown, s.byName);
    if (problem) { setMessage(problem); return; }
    onRig({mode: r.inUse ? "new" : "first", values: shown, from: "advanced"});
  };
  const note = message || (lost ? t("error.rig_missing")
    : full && !same && r.inUse ? t("basic.full_save_into", {max: r.max, name: r.inUse.name})
    : r.inUse && same ? t("basic.same_values", {name: r.inUse.name}) : t("basic.rig_keeps"));
  return <div class="s-rig-save">
    <div class="s-rig-ask">
      {r.inUse && <Button disabled={same || lost} onClick={into}>{t("basic.save_into", {name: r.inUse.name})}</Button>}
      <Button disabled={full} onClick={asNew}>{t(r.inUse ? "basic.save_new" : "basic.save_mine")}</Button>
    </div>
    <p class="u-small" aria-live="polite">{note}</p>
  </div>;
}

/** A topic of More settings: open at first when it is "lines" or has values that differ from Basic's, then as the
 *  user leaves it (a reset does not fold it under the pointer); opened when a field of it is asked for. */
function Topic({s, topic, title, fields, onRig}:
               {s: SearchState; topic: string; title: string; fields: SchemaField[]; onRig(ask: RigAsk): void}) {
  const count = fields.filter((f) => s.differs(f.name)).length;
  const asked = () => !!s.focus && fields.some((f) => f.name === s.focus!.field);
  const [open, setOpen] = useState(() => topic === "lines" || count > 0 || asked());
  useLayoutEffect(() => { if (asked()) setOpen(true); }, [s.focus?.n]);  // before AdvancedPane focuses the field
  return <details class="s-topic" open={open} data-topic={topic}
                  onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
    <summary><Icon name="next" class="s-topic-mark" /><span class="u-grow">{title}</span>
      {count > 0 && <span class="u-badge">{count}</span>}</summary>
    <div class="s-topic-body">
      {fields.map((f) => <Setting key={f.name} s={s} field={f} />)}
      {topic === "rigging" && <SaveRig s={s} onRig={onRig} />}
    </div>
  </details>;
}

function MoreSettings({s, onRig}: {s: SearchState; onRig(ask: RigAsk): void}) {
  const topics = Object.entries(s.schema.topics).filter(([t]) => t !== "where");
  const fields = s.schema.fields.filter((f) => f.topic && f.topic !== "where" && !KEY_FIELDS.includes(f.name));
  const changed = fields.filter((f) => s.differs(f.name)).length;
  const asked = () => !!s.focus && (s.focus.field === "more" || fields.some((f) => f.name === s.focus!.field));
  const [open, setOpen] = useState(asked);
  useLayoutEffect(() => { if (asked()) setOpen(true); }, [s.focus?.n]);
  return <div class="s-more" data-field="more">
    <button type="button" class="s-more-head" aria-expanded={open} onClick={() => setOpen(!open)}>
      <Icon name="filter" /><span class="u-grow">{t("ui.search.more")}</span>
      {changed > 0 && <span class="u-badge">{t("basic.changed", {count: changed})}</span>}
      <span class="u-badge u-n">{fields.length}</span><Icon name={open ? "down" : "next"} />
    </button>
    {open && <div class="s-topics">
      {topics.map(([topic, title]) => {
        const these = fields.filter((f) => f.topic === topic);
        if (!these.length) return null;
        return <Topic key={topic} s={s} topic={topic} title={title} fields={these} onRig={onRig} />;
      })}
    </div>}
  </div>;
}

/** The Advanced tab above Where: "Filled from Basic: <goal>, <rig>." (only when its values came from Basic, not from
 *  a request opened in Advanced) and how many values differ from Basic's. */
function AdvancedTop({s}: {s: SearchState}) {
  const dots = differing(s.resolved, s.base).length;
  const goal = s.goalOf(s.goal);
  const rig = s.rigs.inUse ? s.rigs.inUse.name : t("basic.from_starting");
  return <p class="s-from">{s.filled && <>{t("basic.from", {goal: goal?.label ?? s.goal, rig})}{" "}</>}
    {dots ? t("basic.differ", {count: dots}) : t("basic.differ_none")}</p>;
}

/** The Advanced tab under Where: the run's name, the goal cards, the key fields, More settings. */
function AdvancedBottom({s, onRig}: {s: SearchState; onRig(ask: RigAsk): void}) {
  const nameField = s.byName.name;
  const nameId = useId("s-name");
  // A field asked for (the receipt, "Lighter"): MoreSettings and its Topic open it (their layout effects), then it
  // is focused once it is drawn (a few frames at most)
  useEffect(() => {
    if (!s.focus) return;
    const field = s.focus.field;
    let timer: ReturnType<typeof setTimeout> | undefined, tries = 10;
    const focus = () => {
      const box = field === "name" ? document.getElementById(nameId)?.parentElement
        : document.querySelector(`.s-pane [data-field="${field}"]`);
      const target = field === "more" ? box?.querySelector<HTMLElement>(".s-more-head")
        : box?.querySelector<HTMLElement>("input, select, button.s-more-head");
      if (target && target.getClientRects().length) {
        box?.scrollIntoView?.({block: "center"});
        target.focus();
      } else if (tries-- > 0) timer = setTimeout(focus, 50);
    };
    timer = setTimeout(focus);
    return () => clearTimeout(timer);
  }, [s.focus?.n]);
  return <>
    {nameField && <Field label={label("name")} htmlFor={nameId} hint={hintOf(nameField)}>
      <input id={nameId} class="u-input" type="text" value={s.name} placeholder={t("ui.search.name_placeholder")}
             onInput={(e) => s.setName(e.currentTarget.value)} />
    </Field>}
    <h2 class="u-h s-gap">{t("topic.lines")}</h2>
    <Field label={t("hint.presets.label")} hint={t("hint.presets.help")}><GoalCards s={s} /></Field>
    <KeyFields s={s} />
    <MoreSettings s={s} onRig={onRig} />
  </>;
}

// ---- the bar: the size word, the receipt and the start -----------------------------------------

/** The size word with its "?": the causes, the measured factors (part M3: kept lines, a leash fall space of 6 m,
 *  the square rule), the example, "a rough guide". */
function SizeWord({s, phone}: {s: SearchState; phone?: boolean}) {
  const size = sizeOf(s.resolved, s.km2);
  const why = size.causes.length ? t("basic.size.why", {word: size.word, causes: size.causes.join(", ")})
    : t("basic.size.why_none", {word: size.word});
  return <div class="s-size">
    <span class={`sz sz-${size.level}`} data-size={size.level}>{size.word}</span>
    <Hint label={t("basic.size.label")}>
      <span class="s-tip-p">{why}</span>
      <span class="s-tip-p">{t("basic.size.factors")}</span>
      <span class="s-tip-p">{t("basic.size.example")}</span>
      <span class="s-tip-p">{t("basic.size.rough")}</span>
    </Hint>
    {!phone && size.causes.length > 0 && <span class="s-size-why">{size.causes.join(", ")}</span>}
  </div>;
}

/** The bottom bar (both tabs): the size word, km², the data source and grid of the estimate, the receipt (each part
 *  opens its field in Advanced; a Where problem or a refusal replaces it), the estimate's state when it is not
 *  simply ready, "Start search". On a phone (`phone`) the compact bar: one line "<goal or Custom> · <lengths> ·
 *  <rig>" that unfolds the receipt, the source and the grid. */
export function EstimateBar({search: s, usage, phone}: {search: SearchState; usage?: Usage | null; phone?: boolean}) {
  const {status, estimate, message} = s.estimate;
  const [open, setOpen] = useState(false);
  const limit = withinLimits(usage ?? null, estimate, s.km2);
  const state = status === "ready" ? (limit && !limit.ok ? "warn" : "ok")
    : status === "refused" ? "bad" : status === "paused" || status === "unavailable" ? "warn" : "idle";
  // A Where problem (the request is a message) or a refusal of the estimate replaces the receipt
  const problem = status === "incomplete" || status === "refused" ? message : "";
  const estimating = status === "waiting" || status === "loading";
  const line = problem ? ""
    : status === "paused" ? t("ui.search.paused", {message}) + (s.estimate.retrying ? ` ${t("ui.search.retrying")}` : "")
    : status === "unavailable" ? t("ui.search.no_estimate", {message})
    : limit ? limit.text : "";
  const warnings = estimate ? [...estimate.reasons,
    ...estimate.messages.filter(([kind]) => kind === "warning")
      .map(([, text, info]) => info ? errorText(info, text) : text)] : [];
  const goal = s.tab === "basic" ? s.goalOf(s.goal)?.label ?? null
    : s.preset && s.preset !== "custom" ? s.goalOf(s.preset)?.label ?? null : null;
  // an estimate that says the area is too wide for the access grid: the receipt's part says the mark is left out
  const parts = receiptParts(s.resolved, s.defaults, s.rigs.inUse, s.name, accessSkipped(estimate?.messages));
  const unfolded = open && !problem;
  // Only the daily limit's "within" text may fold away on a phone; a warning, a refusal or an error always shows
  const quiet = state === "ok" && !warnings.length;
  return <div class={cx("s-bar", `s-${state}`, phone && "s-compact", unfolded && "s-open")} data-estimate={status}>
    {phone && <button type="button" class={cx("s-sum", problem && "s-bad")} aria-expanded={unfolded}
                      aria-disabled={problem ? true : undefined} title={t("basic.receipt.toggle")}
                      onClick={() => { if (!problem) setOpen(!open); }}>
      <span class="u-grow">{problem || receiptShort(s.resolved, goal, s.rigs.inUse)}</span>
      {/* the side panels' chevron (the tab's of ui/SidePanel.tsx, turned by search.css): it points where the receipt
          goes: up while it is folded, down when it is unfolded above this line */}
      {!problem && <Icon name="next" class="s-sum-mark" />}</button>}
    {/* On a phone the receipt may be folded away (display: none): what it says is read out from here */}
    {phone && <p class="u-sr" aria-live="polite">
      {problem || parts.filter((p) => !p.wide).map((p) => p.text).join(" · ")}</p>}
    {s.error && <p class="s-problem s-bar-error" role="alert">{s.error}</p>}
    <SizeWord s={s} phone={phone} />
    {s.km2 !== null && <div class="s-stat s-stat-area"><b>{fmt(s.km2)} km²</b>{!phone && <span>{t("ui.search.stat_area")}</span>}</div>}
    {estimate && <div class="s-stat s-stat-source"><b>{estimate.source}</b>
      <span>{textParts("ui.search.stat_grid", {res: estimate.resolution})}</span></div>}
    {estimating && <div class="s-stat s-stat-source s-estimating"><span>{t("ui.search.estimating")}</span></div>}
    {estimate && estimate.tiles > 1 && <div class="s-stat s-stat-source"><b>{estimate.tiles}</b>
      <span>{t("ui.search.stat_tiles")}</span></div>}
    <p class="s-receipt" aria-live={phone ? undefined : "polite"}>
      {problem ? <span class="s-problem">{problem}</span> : parts.map((p, i) =>
        <span key={p.field + i} class={cx(p.wide && "s-wide-only")}>{i > 0 && " · "}
          {/* a phone: plain words (one button into Advanced stands under them); a desktop: each part opens its setting */}
          {phone ? <span data-field={p.field}>{p.text}</span>
            : <button type="button" data-field={p.field} title={t("basic.receipt.open")}
                      onClick={() => s.toAdvanced(p.field)}>{p.text}{p.tail && <span class="s-wide-only">{p.tail}</span>}</button>}</span>)}
    </p>
    {phone && !problem && <button type="button" class="u-btn s-change" onClick={(e) => {
      // Advanced at its top, also when the form was scrolled (the form's column beside this bar)
      const form = e.currentTarget.closest(".c-newsearch, .s-kit")?.querySelector<HTMLElement>(".c-form, .s-c-form");
      setOpen(false);
      s.toAdvanced();
      setTimeout(() => form?.scrollTo({top: 0}));
    }}>
      {t("basic.receipt.change")}<Icon name="next" /></button>}
    {(line || warnings.length > 0) &&
      <p class={cx("s-bar-line", state === "warn" && "s-warn", quiet && "s-quiet")}>
        {line}{warnings.length > 0 && `${line ? "; " : ""}${t("ui.search.warnings", {n: warnings.length})}`}
        {(status === "paused" && !s.estimate.retrying || status === "unavailable") &&
          <>{" "}<button type="button" class="s-link" onClick={s.estimate.retry}>{t("ui.search.retry")}</button></>}</p>}
    <Button kind="primary" large disabled={!s.canStart} onClick={s.start} iconRight="next" class="s-start">
      {t(s.busy ? "ui.search.starting" : "ui.search.start")}</Button>
  </div>;
}

// ---- usage -----------------------------------------------------------------------------------

/** Each meter's number format and unit; its title is ui.usage.<key>. */
const METERS: Record<keyof Usage["usage"], [(v: number) => string, string]> = {
  mpx: [fmt, " km²"], km2: [fmt, " km²"], runs_gb: [fmt, " GB"], jobs_day: [String, ""],
  jobs_active: [String, ""], download_mb: [fmt, " MB"], nominatim: [String, ""],
};

/** The user's quotas as meters ("Area today at 1 m: 3.1 of 250 km²"); without quotas, what is used
 *  (a quota of USAGE counts nothing without it: not shown). */
export function UsageMeters({usage, items = ["mpx", "km2", "runs_gb", "jobs_day", "jobs_active"]}:
                            {usage: Usage | null; items?: (keyof Usage["usage"])[]}) {
  if (!usage) return null;
  const meter = (key: keyof Usage["usage"], item: UsageItem) => {
    const [show, unit] = METERS[key], title = t(`ui.usage.${key}`);
    if (!item || item.used === null) return null;
    const text = item.limit === null ? t("ui.usage.used", {title, used: show(item.used), unit})
      : t("ui.usage.of", {title, used: show(item.used), limit: show(item.limit), unit});
    return <div class="s-meter" key={key} data-usage={key}>
      {item.limit === null ? <span>{text}</span> : <Progress value={item.limit ? item.used / item.limit : 1} label={text} />}
    </div>;
  };
  return <div class="s-meters">
    {items.map((key) => meter(key, usage.usage[key]))}
    {!usage.limited && <span class="u-small s-nolimits">{t("ui.usage.none")}</span>}
  </div>;
}

// ---- the panel -------------------------------------------------------------------------------

export interface SearchPanelProps {
  /** The state from useSearch(), shared with the page's EstimateBar. */
  search: SearchState;
  usage?: Usage | null;            // for the intro's limits
  phone?: boolean;                 // shorter mode labels
}

const TABS = ["basic", "advanced"] as const;

/** The panel of the state `search`. */
export function SearchPanel({search: s, usage, phone}: SearchPanelProps) {
  const intro = useIntro("search", false);  // from its link only (the user's answer of 2026-11-21: Q-F1 b)
  const [ask, setAsk] = useState<ReturnAsk | null>(null);
  const [rig, setRig] = useState<RigAsk | null>(null);
  const tabs = useRef<HTMLDivElement>(null);
  const ids = useId("s-tab");
  const focusTab = (tab: string) => setTimeout(() => tabs.current?.querySelector<HTMLElement>(`[data-tab="${tab}"]`)?.focus());
  const choose = (tab: typeof TABS[number]) => {
    if (tab === s.tab) return;
    if (tab === "advanced") s.toAdvanced();
    else { const asked = s.toBasic(); if (asked) setAsk(asked); }
  };
  // The tabs as WAI-ARIA's (manual activation): ←/→ (Home/End) move the focus between them, Enter or Space (a click)
  // chooses one; the tab not chosen is out of the Tab order
  const key = (e: KeyboardEvent) => {
    const at = TABS.indexOf((e.target as HTMLElement).dataset.tab as typeof TABS[number]);
    const to = e.key === "ArrowRight" ? (at + 1) % TABS.length : e.key === "ArrowLeft" ? (at + TABS.length - 1) % TABS.length
      : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : -1;
    if (at < 0 || to < 0) return;
    e.preventDefault();
    tabs.current?.querySelector<HTMLElement>(`[data-tab="${TABS[to]}"]`)?.focus();
  };
  // One panel for both tabs: its first and last parts are the tab's own, Where between them is the same element in
  // both (keyed), so a tab switch keeps the place box's text and the map's state
  return <div class="s-panel">
    <div class="u-seg s-tabs" role="tablist" aria-label={t("basic.tabs")} ref={tabs} onKeyDown={key}>
      {TABS.map((tab) => <button type="button" key={tab} role="tab" data-tab={tab} id={`${ids}-${tab}`}
                                 aria-selected={s.tab === tab} aria-controls={`${ids}-panel`} tabIndex={s.tab === tab ? 0 : -1}
                                 class={s.tab === tab ? "u-on" : ""} onClick={() => choose(tab)}>
        {t(`basic.tab.${tab}`)}</button>)}
    </div>
    <SearchIntro state={intro} usage={usage ?? null} />
    <p class="s-intro"><IntroLink state={intro}><Icon name="info" />{t("intro.search.link")}</IntroLink></p>
    <div class="s-pane" role="tabpanel" id={`${ids}-panel`} aria-labelledby={`${ids}-${s.tab}`} data-tab-panel={s.tab}>
      {s.tab === "basic" ? <BasicTop key="basic-top" s={s} /> : <AdvancedTop key="advanced-top" s={s} />}
      <h2 key="where-title" class={cx("u-h", s.tab === "basic" && "s-gap")}>{t("basic.where")}</h2>
      <Where key="where" s={s} phone={phone} />
      {s.tab === "basic"
        ? <BasicBottom key="basic-bottom" s={s} onRig={setRig} onEvery={() => { s.toAdvanced(); focusTab("advanced"); }} />
        : <AdvancedBottom key="advanced-bottom" s={s} onRig={setRig} />}
    </div>
    {rig && <RigWindow s={s} ask={rig} onClose={() => setRig(null)} />}
    {ask && <ReturnDialog s={s} ask={ask} onClose={() => setAsk(null)} />}
  </div>;
}
