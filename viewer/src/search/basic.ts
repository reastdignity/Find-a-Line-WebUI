// The Basic search form's rules (docs/line-volume/spec-search.md 1.2), pure functions for useSearch and the
// panel: what a goal and a rig set, what Basic sends, whether values fit a goal and the rig in use
// (matchGoal, notInBasic, basicGoalOf), the line above Start (receiptParts), the size word (sizeOf), the rig's
// words and checks, and where "Sea cliffs" moves the search. The goals' values come from the server
// (params.PRESETS through /api/schema's presets), the defaults from the schema's fields.

import type { Field, Preset } from "../app/api";
import { PLACE_FIELDS } from "../app/request";
import { label, quantity, t } from "../i18n";

/** The fields a goal sets (params.GOAL_FIELDS): values "fit a goal" when all of them equal it. */
export const GOAL_FIELDS = ["min_length", "max_length", "max_anchor_diff_m", "max_anchor_diff", "nmpt", "high_above",
                            "min_height", "min_mean_height", "min_high_share", "max_wall_angle", "min_drop"];
/** The seven values of a rig (params.RIG_FIELDS). */
export const RIG_FIELDS = ["pretension", "stretch", "webbing_weight", "athlete_mass", "fall_zone", "end_zone",
                           "anchor_lift"] as const;
export type RigField = typeof RIG_FIELDS[number];
export type RigValues = Record<RigField, number>;

/** The rig Basic uses until one is saved (never stored): sag, a no-fall zone of 5 m, no A-frames, a leash fall
 *  space of 6 m, 2.5 kN, 5 %, 70 g/m, 80 kg. */
export const STARTING_RIG: RigValues = {pretension: 2.5, stretch: 5, webbing_weight: 70, athlete_mass: 80, fall_zone: 6,
                                        end_zone: 5, anchor_lift: 0};
export const BASIC_SQUARE = 5;   // the square rule of every Basic search (same_line_square)
export const BASIC_RADIUS = 500; // the radius a new search starts with, in both tabs (SearchParams.radius stays 1000)
/** The access mark (SearchParams.access; the command line's default is off): on in every Basic search where the
 *  site's schema has the field, and so in an Advanced filled from Basic (the web form's default, U-8). */
export const BASIC_ACCESS = "access";
export const FIRST_GOAL = "best";
/** What every Basic request carries explicitly, also at the default: a stored request keeps its meaning when a
 *  default moves. */
export const EXPLICIT = ["model", ...RIG_FIELDS, "same_line_square"];

/** A saved rig (/api/rigs). */
export interface Rig { id: number; name: string; values: RigValues }

export type Values = Record<string, unknown>;

/** Two values of a field alike (null and undefined: no value). */
export const same = (a: unknown, b: unknown) => a === b || (a == null && b == null);

/** The default of every field but Where's (the schema's): the fields Basic and Advanced compare. */
export function defaultsOf(byName: Record<string, Field>): Values {
  return Object.fromEntries(Object.values(byName).filter((f) => !PLACE_FIELDS.has(f.name)).map((f) => [f.name, f.default]));
}

/** The values a goal sets, for every field of GOAL_FIELDS (its value, else the default); {} for "custom". */
export function goalValues(preset: Preset | undefined, defaults: Values): Values {
  if (!preset?.values) return {};
  return Object.fromEntries(GOAL_FIELDS.map((k) => [k, k in preset.values! ? preset.values![k] : defaults[k]]));
}

export const rigOf = (values: Values): RigValues =>
  Object.fromEntries(RIG_FIELDS.map((k) => [k, values[k]])) as RigValues;
export const sameRig = (a: RigValues, b: RigValues) => RIG_FIELDS.every((k) => same(a[k], b[k]));

/** The values (changed from the defaults) of the highline layer's "Search a cell" as the form opens them: the
 *  cell's, with the access mark on where the site's schema has the field (the form's default: the layer's request
 *  carries none; the user's word of 2026-11-16: "open in advanced with mark on"). */
export function cellValues(changed: Values, defaults: Values): Values {
  return BASIC_ACCESS in defaults && changed[BASIC_ACCESS] === undefined ? {...changed, [BASIC_ACCESS]: true} : changed;
}

/** Basic's values: every field, at its default except the goal's eleven, the rig's seven, the sag model, the
 *  square rule of 5 and the access mark on (where the site has the field: `defaults` are the schema's). */
export function basicValues(goal: Preset | undefined, rig: RigValues, defaults: Values): Values {
  return {...defaults, ...goalValues(goal, defaults), ...rig, model: "sag", same_line_square: BASIC_SQUARE,
          ...(BASIC_ACCESS in defaults ? {[BASIC_ACCESS]: true} : {})};
}

/** The values that differ from the defaults (what the form keeps and an ordinary request sends). */
export function changedOf(values: Values, defaults: Values): Values {
  return Object.fromEntries(Object.entries(values).filter(([k, v]) => k in defaults && !same(v, defaults[k])));
}

/** The parameters of a Basic request without the place, every one explicit, so a stored request keeps its meaning
 *  when a default moves: the goal's eleven fields (its value or the default; one without a value, a None default,
 *  stays out, as a field the site does not allow, which `defaults`, the schema's fields, leave out), the model, the
 *  rig's seven values and the square rule; and `access: true` where the site has the field (it differs from the
 *  field's default, off, so it is sent as any changed value; a site whose limits leave the field out gets none
 *  and Basic still starts). */
export function basicRequestValues(goal: Preset | undefined, rig: RigValues, defaults: Values): Values {
  const all = basicValues(goal, rig, defaults);
  const goalFields = GOAL_FIELDS.filter((k) => k in defaults && all[k] != null);
  return {...changedOf(all, defaults), ...Object.fromEntries([...goalFields, ...EXPLICIT].map((k) => [k, all[k]]))};
}

/** Why a site cannot take Basic's request `sent` (basicRequestValues), in the words of the server's refusal, or "":
 *  its limits leave out a field Basic must send (the model, the rig's seven values and the square rule are sent
 *  always), or a choice it sends is not among the schema's choices (the sag model, a goal's choice: also a
 *  default's, which Basic sends explicitly: "nmpt=mark"). */
export function basicProblem(byName: Record<string, Field>, sent: Values = {model: "sag"}): string {
  for (const k of EXPLICIT) {
    if (!byName[k]) return t("error.not_allowed", {label: label(k)});
  }
  for (const [k, value] of Object.entries(sent)) {
    const choices = byName[k]?.choices;
    if (typeof value === "string" && choices && k !== "source" && !choices.includes(value)) {
      return t("error.not_allowed_value", {label: label(k), value: t(`choice.${k}.${value}`)});
    }
  }
  return "";
}

/** The goal whose eleven values these are (every field resolved), or null. */
export function matchGoal(values: Values, presets: Preset[], defaults: Values): string | null {
  for (const p of presets) {
    if (!p.values) continue;
    const goal = goalValues(p, defaults);
    if (GOAL_FIELDS.every((k) => same(values[k], goal[k]))) return p.id;
  }
  return null;
}

/** The fields whose value Basic cannot show with this goal and rig (every field resolved): those that differ
 *  from Basic's values. */
export function notInBasic(values: Values, goal: Preset | undefined, rig: RigValues, defaults: Values): string[] {
  const base = basicValues(goal, rig, defaults);
  return Object.keys(defaults).filter((k) => !same(values[k], base[k]));
}

/** The goal Basic shows these values with (they fit a goal and the rig in use), or null: Advanced. */
export function basicGoalOf(values: Values, presets: Preset[], rig: RigValues, defaults: Values): string | null {
  const goal = matchGoal(values, presets, defaults);
  if (!goal) return null;
  return notInBasic(values, presets.find((p) => p.id === goal), rig, defaults).length ? null : goal;
}

export type Tab = "basic" | "advanced";

/** The tab and Basic's goal a form opens with: a new search (`changed` null) Basic with the first goal; a request
 *  to edit (its values changed from the defaults) Basic when it fits a goal and the rig in use (spec-search 1.2:
 *  all eleven goal fields, the seven rig values, the square rule of 5, every other field at its default), else
 *  Advanced with the goal its values match (or the first): a request made before the form has no square rule, so
 *  it never fits. */
export function openingTab(changed: Values | null, presets: Preset[], rig: RigValues, defaults: Values): {tab: Tab; goal: string} {
  if (!changed) return {tab: "basic", goal: FIRST_GOAL};
  const resolved = {...defaults, ...changed};
  const goal = basicGoalOf(resolved, presets, rig, defaults);
  return goal ? {tab: "basic", goal} : {tab: "advanced", goal: matchGoal(resolved, presets, defaults) ?? FIRST_GOAL};
}

/** Advanced's dots: the fields whose value (every field resolved) differs from Basic's. */
export const differing = (values: Values, base: Values) => Object.keys(base).filter((k) => !same(values[k], base[k]));

/** Advanced's "reset": the changed values with `name` at Basic's value (left out when that is its default). */
export function withBasicValue(changed: Values, name: string, base: Values, defaults: Values): Values {
  const next = {...changed};
  if (same(base[name], defaults[name])) delete next[name]; else next[name] = base[name];
  return next;
}

// ---- the rig in use, kept per browser (spec-search 1.3, U-5) ------------------------------------------------

export const RIG_KEY = "findaline.rig";

/** The id of the rig in use this browser keeps, or null (none, or no storage). */
export function storedRigId(): number | null {
  try {
    const text = globalThis.localStorage.getItem(RIG_KEY);
    return text && /^\d+$/.test(text) ? Number(text) : null;
  } catch {
    return null;
  }
}

/** Keep the rig in use (null: forget it); a browser that refuses keeps nothing. */
export function storeRigId(id: number | null) {
  try {
    if (id === null) globalThis.localStorage.removeItem(RIG_KEY);
    else globalThis.localStorage.setItem(RIG_KEY, String(id));
  } catch { /* a private window, blocked storage: the first rig next time */ }
}

/** The rig in use: the stored id's, else the first; null without rigs (the starting rig). */
export function rigInUse(rigs: Rig[], stored: number | null): Rig | null {
  return rigs.find((r) => r.id === stored) ?? rigs[0] ?? null;
}

// ---- words -------------------------------------------------------------------------------------------

/** A number as the form writes it: at most two decimals ("2.5", "6"). */
export const num = (v: unknown) => String(+(+(v as number)).toFixed(2));

/** "sag, no-fall zone 5 m, A-frames 2 m" (`sep` between the parts). */
export function rigSummary(rig: RigValues, sag = true, sep = ", "): string {
  return [sag ? t("rig.sum.sag") : t("rig.sum.formula"),
          rig.end_zone > 0 ? t("rig.sum.zone", {value: num(rig.end_zone)}) : t("rig.sum.no_zone"),
          rig.anchor_lift > 0 ? t("rig.sum.lift", {value: num(rig.anchor_lift)}) : t("rig.sum.no_lift")].join(sep);
}

/** "2.5 kN pretension, 5 % stretch at 10 kN, 70 g/m webbing, athlete 80 kg, 6 m leash fall space". */
export function rigDetail(rig: RigValues): string {
  return t("rig.detail", {pretension: num(rig.pretension), stretch: num(rig.stretch), weight: num(rig.webbing_weight),
                          mass: num(rig.athlete_mass), fall: num(rig.fall_zone)});
}

/** The name the rigging of these values goes by: the rig in use's name when they are its values, "Rig" (the
 *  starting rig, no rig saved), else "Rig for this search". */
export function rigNameOf(values: Values, inUse: Rig | null): string {
  const rig = rigOf(values);
  if (inUse) return sameRig(rig, inUse.values) ? inUse.name : t("rig.name.search");
  return sameRig(rig, STARTING_RIG) ? t("rig.name.starting") : t("rig.name.search");
}

/** A rig's name as the server keeps it (rig_name): composed (NFC), whitespace collapsed, stripped. */
export const cleanName = (name: string) => name.normalize("NFC").replace(/\s+/g, " ").trim();
/** The key names are compared by (the server's casefold, near enough: the server decides). */
export const nameKey = (name: string) => cleanName(name).toLowerCase().normalize("NFC");

/** Whether another rig than `except` has this name. */
export const nameTaken = (rigs: Rig[], name: string, except: number | null = null) =>
  rigs.some((r) => r.id !== except && nameKey(r.name) === nameKey(name));

/** The name a new rig is offered: "My rig" for the first, then the first free "Rig 2", "Rig 3" …. */
export function nextRigName(rigs: Rig[]): string {
  if (!rigs.length) return t("rig.name.first");
  for (let n = 2; ; n++) if (!nameTaken(rigs, t("rig.name.next", {n}))) return t("rig.name.next", {n});
}

/** What is wrong with a rig's values, in the words of the search's own errors (params._check_rigging's order and
 *  bounds, then the site's bounds of the schema's fields `byName`, as web.rig_within refuses them), or "". */
export function rigProblem(rig: Record<string, number>, byName?: Record<string, Field>): string {
  const own = rigBounds(rig);
  if (own) return own;
  for (const k of RIG_FIELDS) {
    const f = byName?.[k];
    if (f?.max != null && rig[k] > f.max) return t("error.at_most", {label: label(k), max: quantity(k, f.max)});
    if (f?.min != null && rig[k] < f.min) return t("error.at_least", {label: label(k), min: quantity(k, f.min)});
  }
  return "";
}

/** The highest value a rig's field may take: the site's (the schema's) or SearchParams' (end_zone 20 m,
 *  anchor_lift 3 m); undefined for the others (no upper bound). */
export function rigMax(k: RigField, byName?: Record<string, Field>): number | undefined {
  const own = k === "end_zone" ? 20 : k === "anchor_lift" ? 3 : undefined;
  const site = byName?.[k]?.max ?? undefined;
  return own === undefined ? site : site === undefined ? own : Math.min(own, site);
}

/** params._check_rigging: SearchParams' bounds of the rig's values. */
function rigBounds(rig: Record<string, number>): string {
  for (const k of RIG_FIELDS) {
    if (typeof rig[k] !== "number" || !Number.isFinite(rig[k])) return t("error.not_a_number", {label: label(k)});
  }
  for (const k of ["pretension", "stretch", "webbing_weight", "athlete_mass", "fall_zone"] as const) {
    const positive = k === "pretension" || k === "stretch";
    if (rig[k] < 0 || (positive && rig[k] === 0)) {
      return t(positive ? "error.positive" : "error.not_negative", {label: label(k)});
    }
  }
  if (!(rig.end_zone >= 0 && rig.end_zone <= 20)) return t("error.end_zone_range", {max: 20});
  if (!(rig.anchor_lift >= 0 && rig.anchor_lift <= 3)) return t("error.anchor_lift_range", {max: 3});
  return "";
}

/** A field's value in words for the list of what Basic cannot show: "Pretension 4 kN", "Drop below both
 *  anchors 50 m", "Trees and buildings: Do not check", "Skip the interactive map: yes", "…: default". */
export function valueText(field: Field, value: unknown): string {
  const name = field.label.replace(/, at (least|most)$/, "");
  if (field.type === "boolean") return `${field.label}: ${t(value ? "basic.value_yes" : "basic.value_no")}`;
  if (field.name === "same_line_square" && value === 0) return `${name}: ${t("basic.value_off")}`;  // 0: the rule off
  if (value == null || value === "") return `${name}: ${t("basic.value_default")}`;
  if (field.type === "choice") {
    return `${field.label}: ${(field.choice_labels?.[String(value)] ?? String(value)).replace(/ \(.*\)$/, "")}`;
  }
  if (typeof value !== "number") return `${name} ${value}`;
  return `${name} ${field.unit === "°" ? `${num(value)}°` : field.unit ? `${num(value)} ${field.unit}` : num(value)}`;
}

// ---- the line above Start (the receipt) and the phone's short line -----------------------------------

/** A part of the receipt: its words and the field it opens in Advanced ("more": More settings, "name": the
 *  search's name); `wide`: shown on a desktop only; `tail`: more words of the same part on a desktop only. */
export interface ReceiptPart { text: string; field: string; wide?: boolean; tail?: string }

/** The code of the estimate's note for a search too wide for the access grid (search.py: the search runs without
 *  the mark), and the run's key that says so (RunHead.access_skipped). */
export const ACCESS_SKIPPED = "access_skipped";

/** Do an estimate's messages ([kind, text, {code, params}?]) say the search's access mark will be left out. */
export function accessSkipped(messages: readonly (readonly unknown[])[] | undefined): boolean {
  return !!messages && messages.some((m) => (m[2] as {code?: unknown} | undefined)?.code === ACCESS_SKIPPED);
}

/** The receipt of these values (every field resolved): lengths, anchors, trees, the goal's other limits, the
 *  rig, "access marked" (on a desktop ", no line filtered out" after it) when the search marks the anchors'
 *  access, or "access not marked" (": area too wide") when the estimate says the search is too wide for it
 *  (`skipped`), "+ N more settings" (other fields off the default, the square rule at Basic's 5 counting as
 *  covered) and the search's name. */
export function receiptParts(values: Values, defaults: Values, inUse: Rig | null, name: string, skipped = false): ReceiptPart[] {
  const v = values;
  const covered = new Set<string>(["min_length", "max_length", "max_anchor_diff_m", "nmpt", "model", ...RIG_FIELDS,
                                   BASIC_ACCESS]);
  if (same(v.same_line_square, BASIC_SQUARE)) covered.add("same_line_square");
  const parts: ReceiptPart[] = [
    {text: t("basic.receipt.lengths", {min: num(v.min_length), max: num(v.max_length)}), field: "min_length"},
    {text: t("basic.receipt.anchors", {value: num(v.max_anchor_diff_m)}), field: "max_anchor_diff_m"},
  ];
  parts.push(v.nmpt === "mark" ? {text: t("basic.receipt.trees_mark"), field: "nmpt", wide: true}
    : {text: t(v.nmpt === "reject" ? "basic.receipt.trees_reject" : "basic.receipt.trees_off"), field: "nmpt"});
  if (v.min_height != null) {
    parts.push({text: t("basic.receipt.min_height", {value: num(v.min_height)}), field: "min_height"});
    covered.add("min_height");
  }
  if (v.min_high_share != null) {
    parts.push({text: t("basic.receipt.high_share", {share: num(v.min_high_share), above: num(v.high_above)}),
                field: "min_high_share"});
    covered.add("min_high_share").add("high_above");
  }
  if (v.max_wall_angle != null) {
    parts.push({text: t("basic.receipt.wall_angle", {value: num(v.max_wall_angle)}), field: "max_wall_angle"});
    covered.add("max_wall_angle");
  }
  if (v.min_drop != null) {
    parts.push({text: t("basic.receipt.drop", {value: num(v.min_drop)}), field: "min_drop"});
    covered.add("min_drop");
  }
  const sag = v.model === "sag";
  parts.push({text: t("basic.receipt.rig", {name: rigNameOf(v, inUse), summary: rigSummary(rigOf(v), sag, ", ")}),
              field: sag ? "end_zone" : "model"});
  if (v[BASIC_ACCESS] === true) {
    parts.push(skipped ? {text: t("basic.receipt.access_skipped"), tail: t("basic.receipt.access_skipped_wide"), field: BASIC_ACCESS}
      : {text: t("basic.receipt.access"), tail: t("basic.receipt.access_wide"), field: BASIC_ACCESS});
  }
  const more = Object.keys(defaults).filter((k) => !covered.has(k) && !same(v[k], defaults[k])).length;
  if (more) parts.push({text: t("basic.receipt.more", {count: more}), field: "more"});
  if (name.trim()) parts.push({text: t("basic.receipt.named", {name: name.trim()}), field: "name"});
  return parts;
}

/** The compact phone bar's one line: "<goal or Custom> · <lengths> · <rig>". */
export function receiptShort(values: Values, goalTitle: string | null, inUse: Rig | null): string {
  return [goalTitle ?? t("preset.custom"), t("basic.receipt.lengths", {min: num(values.min_length), max: num(values.max_length)}),
          rigNameOf(values, inUse)].join(" · ");
}

// ---- the size word ---------------------------------------------------------------------------------------

export const SIZE_WORDS = ["basic.size.light", "basic.size.heavier", "basic.size.heavy", "basic.size.very"];

/** The size word (spec-search 1.2, N-05): one step each for sag, a no-fall zone and A-frames, one for lines
 *  spanning 900 m or more, else for an area above 3.2 km²; at most "Very heavy". `causes` name the steps. */
export function sizeOf(values: Values, km2: number | null): {level: number; word: string; causes: string[]} {
  const v = values, causes: string[] = [];
  if (v.model === "sag") causes.push(t("basic.size.sag"));
  if (Number(v.end_zone) > 0) causes.push(t("basic.size.zone", {value: num(v.end_zone)}));
  if (Number(v.anchor_lift) > 0) causes.push(t("basic.size.lift", {value: num(v.anchor_lift)}));
  if (Number(v.max_length) - Number(v.min_length) >= 900) causes.push(t("basic.size.long", {value: num(v.max_length)}));
  else if (km2 !== null && km2 > 3.2) causes.push(t("basic.size.area", {value: num(km2.toFixed(1))}));
  const level = Math.min(causes.length, 3);
  return {level, word: t(SIZE_WORDS[level]), causes};
}

// ---- where "Sea cliffs" moves the search ------------------------------------------------------------------

export type WhereMode = "point" | "area" | "cliffs" | "file";
export type CoastKind = "cliffs" | "coast";
/** Where's mode, the kind of Along cliffs, the band width, the limit of Along cliffs ("Limit to": an OSM name or
 *  S,W,N,E) and what "Sea cliffs" replaced (null: nothing). */
export interface WhereState { mode: WhereMode; coastKind: CoastKind; buffer: number; within: string;
                              before: {mode: WhereMode; coastKind: CoastKind; buffer: number; within: string} | null }

/** "Sea cliffs" switches Where to Along cliffs → Coast with a band of 100 m and, when the limit is empty, the map
 *  view `view` (S,W,N,E) as the limit, so the search can start (a limit typed or chosen stays); it remembers the
 *  mode, the kind, the band and the limit before, and another goal puts them back (a mode chosen by hand meanwhile
 *  forgets them: the caller clears `before`). Already on the coast it only sets the band (no switch: the limit
 *  stays, nothing more is remembered). */
export function whereForGoal(goal: string, w: WhereState, view = ""): WhereState {
  if (goal === "sea") {
    if (w.before || (w.mode === "cliffs" && w.coastKind === "coast")) {
      return {...w, mode: "cliffs", coastKind: "coast", buffer: 100};
    }
    return {mode: "cliffs", coastKind: "coast", buffer: 100, within: w.within.trim() ? w.within : view,
            before: {mode: w.mode, coastKind: w.coastKind, buffer: w.buffer, within: w.within}};
  }
  return w.before ? {...w.before, before: null} : w;
}
