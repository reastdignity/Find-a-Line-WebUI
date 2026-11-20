// The state of a new search in the new interfaces: where (four modes), the two tabs (Basic: a goal and the
// rig in use; Advanced: every parameter, its goal cards and the dots of the values that differ from Basic's),
// the live estimate and the start. useSearch() holds it, so a shell can show the panel (SearchPanel) and the
// estimate with the start (EstimateBar) in different places; useUsage() is the user's use of the quotas
// (/api/usage). The request is built by app/request.ts, Basic's values by basic.ts.

import type { FeatureCollection } from "geojson";
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { api, ApiError, type Estimate, type Field, type Preset, type Schema, type SearchRequest, type Usage } from "../app/api";
import { countAreas } from "../app/areas";
import { COUNTRY_EVENT } from "../app/timeZone";
import { readAreaFile } from "../app/files";
import type { Mode, PlaceMap } from "../app/PlaceMap";
import { buildRequest, fromRequest, valueProblem, withValue, type AreaFile, type Place } from "../app/request";
import { t } from "../i18n";
import {
  basicGoalOf, basicProblem, basicRequestValues, basicValues, BASIC_RADIUS, cellValues, changedOf, defaultsOf, GOAL_FIELDS,
  matchGoal,
  notInBasic, openingTab, same, whereForGoal, type CoastKind, type Tab, type Values, type WhereMode, type WhereState,
} from "./basic";
import type { RigsState } from "./useRigs";

export type SearchMode = WhereMode;
export type AreaKind = "draw" | "osm";       // the Area mode: drawn on the map, or a named OSM area
export type { CoastKind, Tab };               // the Along cliffs mode; the form's tabs

/** The key fields under the presets (the presets set the first three). */
export const KEY_FIELDS = ["min_length", "max_length", "max_anchor_diff_m", "source"];

export const DEBOUNCE_MS = 800;   // the estimate is asked for this long after the last change
export const RETRY_MS = 20_000;   // an estimate refused by the rate (429) is asked again once, after this

export type EstimateStatus =
  | "incomplete"   // the place is not complete yet (message: what is missing)
  | "waiting"      // a change; asked for after DEBOUNCE_MS
  | "loading"      // asked for
  | "ready"        // estimate
  | "paused"       // too many estimates (429): asked again once after RETRY_MS
  | "refused"      // the server refused the request (a value over the limits, a bad area): no start
  | "unavailable"; // no answer (no worker, busy, offline): the search can still be started

export interface EstimateState {
  status: EstimateStatus;
  estimate: Estimate | null;
  message: string;
  retrying: boolean;  // paused, and the one retry is still to come
  retry(): void;      // ask again now (a button)
}

/** The estimate of a request, asked for DEBOUNCE_MS after its last change; an answer to an older
 *  request is dropped (and its fetch aborted, so the server forgets its task). The area it will
 *  search is drawn on `place` (the preview) while the estimate is current. */
export function useEstimate(request: SearchRequest | string, place: PlaceMap | null): EstimateState {
  const key = typeof request === "string" ? "" : JSON.stringify(request);
  const [state, setState] = useState<Omit<EstimateState, "retry">>(
    {status: "incomplete", estimate: null, message: "", retrying: false});
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const current = useRef(request);
  current.current = request;

  const load = useCallback((asked: number, retried: boolean) => {
    const r = current.current;
    if (asked !== generation.current || typeof r === "string") return;
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    setState({status: "loading", estimate: null, message: "", retrying: false});
    api.estimate(r, mine.signal).then((estimate) => {
      if (asked !== generation.current) return;
      setState({status: "ready", estimate, message: "", retrying: false});
      place?.showPreview(estimate.area);
    }, (e: Error) => {
      if (asked !== generation.current || mine.signal.aborted) return;
      const code = e instanceof ApiError ? e.status : 0;
      if (code === 429) {
        setState({status: "paused", estimate: null, message: e.message, retrying: !retried});
        if (!retried) timer.current = setTimeout(() => load(asked, true), RETRY_MS);
      } else if (code >= 400 && code < 500) {
        setState({status: "refused", estimate: null, message: e.message, retrying: false});
      } else {
        setState({status: "unavailable", estimate: null, message: e.message, retrying: false});
      }
    });
  }, [place]);

  useEffect(() => {
    const asked = ++generation.current;
    controller.current?.abort();
    controller.current = null;
    place?.showPreview(null);
    if (!key) {
      setState({status: "incomplete", estimate: null, message: "", retrying: false});
      return;
    }
    setState({status: "waiting", estimate: null, message: "", retrying: false});
    timer.current = setTimeout(() => load(asked, false), DEBOUNCE_MS);
    return () => clearTimeout(timer.current);
  }, [key, place]);

  useEffect(() => () => { generation.current++; controller.current?.abort(); }, []);

  const retry = () => {
    clearTimeout(timer.current);
    load(generation.current, true);
  };
  return {...state, message: typeof request === "string" ? request : state.message, retry};
}

export interface UsageState {
  usage: Usage | null;
  error: string;
  refresh(): void;
}

/** The user's use of the quotas and the quotas (/api/usage), asked for once, on refresh() and when the
 *  server has taken the browser's time zone (the account's country, app/timeZone.ts). */
export function useUsage(): UsageState {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(() => {
    api.usage().then((u) => { setUsage(u); setError(""); }, (e) => setError(e.message));
  }, []);
  useEffect(() => {
    refresh();
    window.addEventListener(COUNTRY_EVENT, refresh);
    return () => window.removeEventListener(COUNTRY_EVENT, refresh);
  }, [refresh]);
  return {usage, error, refresh};
}

/** Whether an estimate fits the user's daily quotas (Mpx, km², downloads): null without quotas or estimate.
 *  `area`: the km² of the search (the estimate's, or a circle's), null when not known before it runs.
 *  The Mpx quota (km² / resolution²) is shown as km² at the search's resolution. */
export function withinLimits(usage: Usage | null, estimate: Estimate | null,
                             area: number | null = estimate?.km2 ?? null): {ok: boolean; text: string} | null {
  if (!usage || !estimate || !usage.limited) return null;
  const {mpx, km2, download_mb} = usage.usage;
  const scale = estimate.resolution ** 2;  // km² of one Mpx at this resolution
  const atRes = ` ${t("ui.usage.at_res", {res: fmt(estimate.resolution)})}`;
  const pixels = mpx?.limit != null && mpx.used !== null && area !== null
    ? {used: mpx.used * scale, limit: mpx.limit * scale, area} : null;
  if (pixels && pixels.used + pixels.area > pixels.limit) {
    return {ok: false, text: t("ui.usage.over", {used: fmt(pixels.used), limit: fmt(pixels.limit), unit: atRes,
                                                  needs: fmt(pixels.area)})};
  }
  if (km2.limit !== null && km2.used !== null && area !== null) {
    if (km2.used + area > km2.limit) {
      return {ok: false, text: t("ui.usage.over", {used: fmt(km2.used), limit: fmt(km2.limit), unit: " km²",
                                                    needs: fmt(area)})};
    }
  }
  if (download_mb.limit !== null && download_mb.used !== null &&
      download_mb.used + estimate.download_mb > download_mb.limit) {
    return {ok: false, text: t("ui.usage.over_download", {used: fmt(download_mb.used), limit: fmt(download_mb.limit)})};
  }
  if (pixels) {
    return {ok: true, text: t("ui.usage.within", {used: fmt(pixels.used + pixels.area), limit: fmt(pixels.limit), unit: atRes})};
  }
  if (km2.limit !== null && km2.used !== null && area !== null) {
    return {ok: true, text: t("ui.usage.within", {used: fmt(km2.used + area), limit: fmt(km2.limit), unit: " km²"})};
  }
  return {ok: true, text: t("ui.usage.within_all")};
}

/** A number for the panel: two significant decimals below 10, one below 100, none above. */
export function fmt(value: number): string {
  const digits = Math.abs(value) < 10 ? 2 : Math.abs(value) < 100 ? 1 : 0;
  return String(+value.toFixed(digits));
}

export interface SearchOptions {
  place: PlaceMap;
  schema: Schema;
  rigs: RigsState;                 // the saved rigs and the rig in use (loaded: the tab of a request to edit needs it)
  onStarted(jobId: string): void;
  initial?: SearchRequest | null;  // a search to edit and run again (or a cell's of the highline layer)
  cell?: boolean;                  // `initial` is a cell's of the highline layer: the form's access mark on (cellValues)
}

/** What going back to Basic would lose: the dialog's list (fields, in Advanced's values) and the goal it resets to. */
export interface ReturnAsk { fields: string[]; goal: string }

export interface SearchState {
  place: PlaceMap;
  schema: Schema;
  byName: Record<string, Field>;
  tab: Tab;
  filled: boolean;                     // Advanced's values came from Basic ("Filled from Basic"), not from a request
  /** To Advanced, filled with Basic's values when it comes from Basic; `field`: open and focus it ("more": More
   *  settings, "name": the search's name). */
  toAdvanced(field?: string): void;
  /** To Basic: silently when the values fit a goal and the rig in use (null), else what the dialog lists. */
  toBasic(): ReturnAsk | null;
  /** Back to Basic with Basic's values of `goal` (the dialog's "Reset them to Basic's values"). */
  resetToBasic(goal: string): void;
  focus: {field: string; n: number} | null;  // a field Advanced is asked to open and focus
  goal: string;                        // Basic's goal (Advanced's dots compare with it)
  goalOf(id: string): Preset | undefined;
  chooseGoal(id: string): void;        // a goal card of Basic
  rigs: RigsState;
  defaults: Values;                    // every field's default (but Where's)
  base: Values;                        // Basic's values now (the goal and the rig in use), every field
  resolved: Values;                    // every field's value now
  differs(name: string): boolean;      // Advanced's dot: the value differs from Basic's
  mode: SearchMode;
  setMode(mode: SearchMode): void;
  seaBefore: WhereState["before"];     // the mode "Sea cliffs" replaced (another goal brings it back)
  areaKind: AreaKind;
  setAreaKind(kind: AreaKind): void;
  coastKind: CoastKind;
  setCoastKind(kind: CoastKind): void;
  point: [number, number] | null;
  radius: number;
  setRadius(radius: number): void;
  buffer: number;
  setBuffer(buffer: number): void;
  osmName: string;
  setOsmName(name: string): void;
  within: string;
  setWithin(within: string): void;
  name: string;
  setName(name: string): void;
  file: AreaFile | null;
  fileKey: number;                     // a new (empty) file input after clearing
  readFile(input: HTMLInputElement): Promise<void>;
  shapes: number;                      // drawn shapes or shapes of the file
  areas: number;                       // separate areas of them (overlapping or touching shapes are one)
  values: Record<string, unknown>;     // the parameters changed from their defaults (Basic's: the goal's and the rig's)
  value(name: string): unknown;        // a parameter's value (its default when unchanged)
  setValue(name: string, value: unknown): void;     // Advanced's
  setValues(values: Record<string, unknown>): void; // Advanced's
  problems: Record<string, string>;    // values outside the site's bounds, by field
  preset: string;                      // the goal card of Advanced the values match ("custom" if none)
  applyPreset(id: string): void;       // a goal card of Advanced: its eleven fields and Basic's goal
  request: SearchRequest | string;     // the request, or what is missing
  estimate: EstimateState;
  km2: number | null;                  // the area of the search: the estimate's, or a circle's (π r²)
  canStart: boolean;
  busy: boolean;
  error: string;                       // of the start
  start(): Promise<void>;
  clear(): void;                       // the place (point, drawn areas, file, names); the parameters stay
}

/** The place mode of the map (PlaceMap) for a mode of the panel. */
function mapMode(mode: SearchMode, areaKind: AreaKind): Mode {
  return mode === "point" ? "point" : mode === "file" ? "file" : mode === "area" && areaKind === "draw" ? "draw"
    : "preset";
}

/** A new search: the state of the panel, its request, the live estimate and the start. */
export function useSearch({place, schema, rigs, onStarted, initial, cell}: SearchOptions): SearchState {
  const byName = useMemo(() => Object.fromEntries(schema.fields.map((f) => [f.name, f])), [schema]);
  const defaults = useMemo(() => defaultsOf(byName), [byName]);
  const presets = schema.presets;
  const goalOf = (id: string) => presets.find((p) => p.id === id);
  const start0 = useMemo(() => {
    const found = fromRequest(initial, byName);
    const values = initial && cell ? cellValues(found.values, defaults) : found.values;
    return {...found, values, radius: initial ? found.radius : BASIC_RADIUS,
            ...openingTab(initial ? values : null, presets, rigs.values, defaults)};
  }, []);
  const [tab, setTab] = useState<Tab>(start0.tab);
  const [filled, setFilled] = useState(false);  // Advanced's values came from Basic (not a request opened there)
  const [goal, setGoal] = useState(start0.goal);
  const [focus, setFocus] = useState<{field: string; n: number} | null>(null);
  const [where, setWhere] = useState<WhereState>({
    mode: start0.mode === "point" ? "point" : start0.mode === "file" ? "file"
      : start0.mode === "draw" || start0.preset === "osm" ? "area" : "cliffs",
    coastKind: start0.preset === "coast" ? "coast" : "cliffs", buffer: start0.buffer, within: start0.within,
    before: null});
  const {mode, coastKind, buffer, within} = where;
  // A mode or kind chosen by hand forgets what "Sea cliffs" replaced (choosing the coast keeps it)
  const setMode = (m: SearchMode) => setWhere((w) => ({...w, mode: m, before: null}));
  const setCoastKind = (k: CoastKind) => setWhere((w) => ({...w, coastKind: k, before: k === "coast" ? w.before : null}));
  const setBuffer = (b: number) => setWhere((w) => ({...w, buffer: b}));
  const setWithin = (text: string) => setWhere((w) => ({...w, within: text}));
  const [areaKind, setAreaKind] = useState<AreaKind>(start0.mode === "preset" && start0.preset === "osm" ? "osm" : "draw");
  const [point, setPoint] = useState(start0.point);
  const [radius, setRadius] = useState(start0.radius);
  const [osmName, setOsmName] = useState(start0.osmName);
  const [name, setName] = useState(start0.name);
  const [file, setFile] = useState<AreaFile | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [drawn, setDrawn] = useState(0);  // changes when the drawn areas change
  // Advanced's values (changed from the defaults); Basic's follow from its goal and the rig in use
  const [advValues, setAdvValues] = useState<Record<string, unknown>>(start0.tab === "advanced" ? start0.values : {});
  const [custom, setCustom] = useState(false);  // "Custom" chosen while the values match a goal
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const base = useMemo(() => basicValues(goalOf(goal), rigs.values, defaults), [goal, rigs.values, defaults, presets]);
  const basicChanged = useMemo(() => changedOf(base, defaults), [base, defaults]);
  const values = tab === "basic" ? basicChanged : advValues;
  const resolved = useMemo(() => ({...defaults, ...values}), [defaults, values]);

  useEffect(() => {
    place.onPoint = (lat, lon) => setPoint([lat, lon]);
    place.onDrawn = () => setDrawn((n) => n + 1);
  }, [place]);
  useEffect(() => place.setMode(mapMode(mode, areaKind)), [place, mode, areaKind]);
  useEffect(() => {  // a search to edit: its drawn or uploaded area becomes editable on the map
    if (initial?.geometry) place.loadDrawn(initial.geometry);
    if (start0.point) place.map.setView(start0.point, Math.max(place.map.getZoom(), 14));
  }, [place, initial]);
  useEffect(() => { if (point) place.setPoint(point[0], point[1], radius); }, [place, point, radius]);
  useEffect(() => setError(""), [mode, areaKind, coastKind, point, radius, buffer, osmName, within, file, drawn, values]);

  const drawnAreas = useMemo((): FeatureCollection | null => place.drawnAreas(), [place, drawn]);
  const collection = mode === "area" && areaKind === "draw" ? drawnAreas : mode === "file" ? file?.areas ?? null : null;
  const areas = useMemo(() => countAreas(collection, buffer), [collection, buffer]);
  const shapes = collection?.features.length || 0;

  const value = (key: string) => key in values ? values[key] : byName[key]?.default;
  const problems = useMemo(() => {
    const found: Record<string, string> = {};
    for (const [key, v] of Object.entries(values)) {
      const problem = byName[key] ? valueProblem(byName[key], v) : "";
      if (problem) found[key] = problem;
    }
    const low = Number(value("min_length")), high = Number(value("max_length"));
    if (!(low > 0 && low < high)) found.min_length = t("error.length_range");
    return found;
  }, [values, byName]);

  const matching = matchGoal(resolved, presets, defaults);
  const preset = custom || !matching ? (presets.some((p) => p.id === "custom") ? "custom" : "") : matching;
  /** A goal moves Where for "Sea cliffs" (and back for another goal). */
  const whereFor = (id: string) => { const view = place.viewBox(); setWhere((w) => whereForGoal(id, w, view)); };
  const applyPreset = (id: string) => {
    const chosen = goalOf(id);
    if (!chosen || !chosen.available) return;
    if (!chosen.values) { setCustom(true); return; }
    setCustom(false);
    setGoal(id);
    setAdvValues((now) => {
      let next = now;
      for (const key of GOAL_FIELDS) {
        if (byName[key]) next = withValue(next, byName[key], key in chosen.values! ? chosen.values![key] : byName[key].default);
      }
      return next;
    });
    whereFor(id);
  };
  const chooseGoal = (id: string) => {
    const chosen = goalOf(id);
    if (!chosen?.values || !chosen.available) return;
    setGoal(id);
    setCustom(false);
    whereFor(id);
  };

  const toAdvanced = (field?: string) => {
    if (tab === "basic") { setAdvValues(basicChanged); setCustom(false); setFilled(true); }
    setTab("advanced");
    if (field) setFocus((f) => ({field, n: (f?.n ?? 0) + 1}));
  };
  const toBasic = (): ReturnAsk | null => {
    if (tab === "basic") return null;
    const fits = basicGoalOf(resolved, presets, rigs.values, defaults);
    if (fits) {
      setGoal(fits);
      setCustom(false);
      setTab("basic");
      return null;
    }
    const at = matching ?? goal;
    return {goal: at, fields: notInBasic(resolved, goalOf(at), rigs.values, defaults)};
  };
  const resetToBasic = (id: string) => {
    setGoal(id);
    setCustom(false);
    setTab("basic");
  };

  const request = useMemo((): SearchRequest | string => {
    const placed: Place = {mode: mapMode(mode, areaKind), point, radius, buffer,
                           preset: mode === "area" ? "osm" : coastKind, osmName,
                           within: mode === "cliffs" ? within : "", name};
    // Basic sends the goal's fields, the model, the rig's seven values and the square rule also at their defaults;
    // a site whose limits leave one of the last out cannot take it
    const sent = tab === "basic" ? basicRequestValues(goalOf(goal), rigs.values, defaults) : values;
    const blocked = tab === "basic" ? basicProblem(byName, sent) : "";
    if (blocked) return blocked;
    const built = buildRequest(placed, sent, drawnAreas, file);
    if (typeof built === "string") return built;
    const wrong = Object.entries(problems);
    if (wrong.length) {
      return [t("error.check_settings"), ...wrong.map(([, p]) => p)].join(" ");
    }
    return built;
  }, [mode, areaKind, coastKind, point, radius, buffer, osmName, within, name, values, drawnAreas, file, problems,
      tab, goal, rigs.values, defaults, byName]);

  const estimate = useEstimate(request, place);
  const canStart = typeof request !== "string" && estimate.status !== "refused" && !busy;
  // The worker charges a circle as π r² (jobs.charge_area); the estimate gives km² for areas only
  const km2 = estimate.estimate?.km2 ?? (mode === "point" && point ? Math.PI * radius * radius / 1e6 : null);

  const clear = () => {
    place.clear();
    setPoint(null);
    setFile(null);
    setFileKey((k) => k + 1);
    setOsmName("");
    setWithin("");
    setName("");
  };

  const start = async () => {
    if (typeof request === "string" || busy) return;
    setBusy(true);
    setError("");
    try {
      const {id} = await api.start(request);
      onStarted(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const readFile = async (input: HTMLInputElement) => {
    const chosen = input.files?.[0];
    if (!chosen) return;
    try {
      const read = await readAreaFile(chosen);
      setFile({name: chosen.name, areas: read});
      place.showFile(read);
    } catch (e) {
      setError((e as Error).message);
      setFile(null);
      place.showFile(null);
    }
  };

  return {
    place, schema, byName, tab, filled, toAdvanced, toBasic, resetToBasic, focus, goal, goalOf, chooseGoal, rigs, defaults,
    base, resolved,
    differs: (key) => key in base && !same(resolved[key], base[key]),  // basic.differing, per field
    mode, setMode, seaBefore: where.before, areaKind, setAreaKind, coastKind, setCoastKind, point, radius, setRadius,
    buffer, setBuffer, osmName, setOsmName, within, setWithin, name, setName, file, fileKey, readFile, shapes, areas,
    values, value, setValue: (key, v) => { if (byName[key]) setAdvValues((now) => withValue(now, byName[key], v)); },
    setValues: setAdvValues, problems, preset, applyPreset, request, estimate, km2, canStart, busy, error, start, clear,
  };
}
