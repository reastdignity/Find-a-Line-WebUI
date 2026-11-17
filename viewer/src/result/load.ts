// A run's data for the app and a run's map.html: its data.js (window.FINDALINE_RUN = {...};). Over http(s) it
// is downloaded (download.ts: XMLHttpRequest) and its bytes counted for the progress bar (against SIZE_HEADER,
// the size web.RunFiles gives before nginx gzips it, or Content-Length when nothing compressed it), then read by
// JSON.parse (measured 2026-11-04: about 30 % faster than the script; tools/perf_run_load.py). A file JSON.parse refuses (NaN,
// Infinity: runs.column_texts writes them) is loaded as a script instead, from the HTTP cache, so every value
// stays as the script gives it. From disk (file://: no fetch) it is a script, which the CSP (script-src
// 'self') allows and web.RunFiles serves only to who may open the run. The lines of other runs (Compare) and of
// Home's mini maps come from their store or their lines.js (loadOtherRun, loadRunLines, others.loadLines).
//
// The rows are then read into columns (types.ts runData: docs/line-volume/spec-store.md 1.2, store wave 1) and
// dropped: the page keeps the run's lines as typed arrays (RunData.columns). A body that arrives empty although its
// bytes came is longer than the browser's longest string (Chromium: 536 870 888 characters, about 2.3 M lines of
// today's data.js; the XHR's text is then "" with no error): the load fails with TooLarge, whose message the page
// shows, and is not tried as a script (which crashed the tab: part E2 of the line-volume study).
//
// A run with a store (store wave 2: run.json's block `store`, which runs.js lists) is read from it instead over
// http(s): lines.arrow and profiles.arrow downloaded together (download.ts, as bytes), read with apache-arrow
// (readStore) into the same columns without a copy, the head from the schema's metadata `findaline`. Which file is
// read is decided by the run's entry in the list of runs the page has (storeOf: window.FINDALINE_RUNS, or runs.js
// beside the run's folder loaded once): a run listed without the block `store` (saved before 2026-11-15, its store
// failed, or a save stopped before it wrote run.json) reads data.js, and so does a page from disk. A run the list
// does not name (a share link, whose runs.js lists no runs; another user's run an administrator opens; a run saved
// since the list was read) asks for its store's files directly (STORE_PROBE): a run without them answers 404 and
// reads data.js, and so does a probe whose files could not be fetched (another status, a network error: the probe
// is a guess, and an old run must not fail on it). A store whose file is missing (404) falls back to data.js while
// runs keep it (until store wave 4); a store of a newer format never does (NewerStore: its file's metadata says so),
// and a store that fails otherwise (a listed one not fetched, any one fetched but unreadable) is a StoreFailed. A
// body the browser could not hold (a null ArrayBuffer) is TooLarge, as data.js's empty text is. Only answers of 200
// report the download's progress (a 404's short body is no part of the run).

import { RecordBatchReader, Type, type Data, type RecordBatch, type Schema } from "apache-arrow";
import { download } from "../download";
import { t } from "../i18n";
import { measure, timed } from "../perf";
import { nextPaint } from "../paint";
import { runData, storedColumns, type LineColumns, type Ortho, type Profile, type ProfileSource, type RunData, type RunHead,
         type RunInfo, type RunScript, type StoredColumn, type StoreInfo, type ViewColumns } from "../types";

const PREFIX = "window.FINDALINE_RUN = ";  // mapping._script_head of data.js
/** The store's format this page reads (linestore.FORMAT): a store of a higher one is refused (NewerStore). */
export const STORE_FORMAT = 1;
export const STORE_FILES = ["lines.arrow", "profiles.arrow"];  // linestore.FILES
const META_KEY = "findaline";  // linestore.META_KEY: the schema metadata of both files

/** Where loading a run is: downloading (`done` of `total` bytes, `total` null when unknown), reading its
 *  lines, grouping them (buildModel). `fraction` 0..1, or null when the amount is unknown. */
export interface LoadProgress {
  phase: "download" | "parse" | "groups";
  fraction: number | null;
  done?: number;
  total?: number | null;
}

export type OnProgress = (progress: LoadProgress) => void;

/** A run too large for this browser: its data.js arrived as an empty text (the browser's string limit). */
export class TooLarge extends Error {
  constructor() {
    super(t("ui.result.too_large"));
    this.name = "TooLarge";
  }
}

/** A run's store that could not be downloaded or read (not a missing file: that falls back to data.js). */
export class StoreFailed extends Error {
  constructor(key: string, why: string) {
    super(`could not load the store of the run ${key} (${why})`);
    this.name = "StoreFailed";
  }
}

/** A store's file answered 404: the run is read from data.js (or lines.js) instead while runs keep them. */
class StoreMissing extends Error {}

/** A store's file that could not be fetched (a status other than 200 or 404, a network error): a StoreFailed, but
 *  the probe (STORE_PROBE) reads data.js instead. */
class StoreNotFetched extends StoreFailed {}

/** A run whose store is of a higher format than STORE_FORMAT: made by a newer Find-a-Line. */
export class NewerStore extends Error {
  constructor() {
    super(t("ui.result.newer_store"));
    this.name = "NewerStore";
  }
}

interface Loading {
  promise: Promise<RunData>;
  listeners: Set<OnProgress>;
  last: LoadProgress | null;
}

const loaded = new Map<string, Loading>();

/** The data of run `id` (`<base><id>/data.js`), loaded once; rejects when it cannot be loaded (a failed load
 *  is tried again on the next call). `onProgress` hears the load's phases until it ends. */
export function loadRun(id: string, base = "/runs/", onProgress?: OnProgress): Promise<RunData> {
  return loadRunFrom(base + encodeURIComponent(id) + "/data.js", id, onProgress);
}

/** The run data of the script at `url`, kept under `key` (loadRun's run id). */
export function loadRunFrom(url: string, key: string, onProgress?: OnProgress): Promise<RunData> {
  let loading = loaded.get(key);
  if (!loading) {
    const entry: Loading = {listeners: new Set(), last: null, promise: Promise.resolve(null as unknown as RunData)};
    const report = (p: LoadProgress) => { entry.last = p; entry.listeners.forEach((f) => f(p)); };
    entry.promise = overHttp() ? fromServer(url, key, report) : scriptRun(url, key, report);
    loaded.set(key, entry);
    entry.promise.catch(() => { if (loaded.get(key) === entry) loaded.delete(key); });
    entry.promise.finally(() => entry.listeners.clear()).catch(() => undefined);
    loading = entry;
  }
  if (onProgress) {
    loading.listeners.add(onProgress);
    if (loading.last) onProgress(loading.last);
  }
  return loading.promise;
}

function overHttp(): boolean {
  return location.protocol === "http:" || location.protocol === "https:";
}

/** A data.js's text as its value, or null when it is not one JSON.parse reads (NaN or Infinity in it). */
export function parseRunScript(text: string): RunScript | null {
  const end = text.lastIndexOf(";");
  if (!text.startsWith(PREFIX) || end < PREFIX.length) return null;
  try {
    const data = JSON.parse(text.slice(PREFIX.length, end));
    return data && Array.isArray(data.lines) ? data as RunScript : null;
  } catch {
    return null;
  }
}

/** Was a downloaded body cut to nothing by the browser's string limit: empty although `bytes` of it came. */
export function tooLarge(body: string, bytes: number): boolean {
  return body === "" && bytes > 0;
}

/** data.js's value with its rows read into columns (the rows are dropped with the value). */
export function columnsOf(script: RunScript): RunData {
  return timed("fal:run:lines", () => runData(script), {count: script.lines.length});
}

async function downloadRun(url: string, key: string, report: OnProgress): Promise<RunData> {
  const start = performance.now();
  report({phase: "download", fraction: null});
  const answer = await download(url, "text", {
    onHeaders: (total) => report({phase: "download", fraction: total ? 0 : null, done: 0, total}),
    onBytes: (done, total) => report({phase: "download", fraction: total ? Math.min(1, done / total) : null, done, total}),
  }).catch(() => { throw new Error("could not load the run " + key); });
  if (answer.status !== 200) throw new Error(`could not load the run ${key} (${answer.status})`);
  measure("fal:run:download", start, {bytes: answer.bytes});
  if (tooLarge(answer.body, answer.bytes)) throw new TooLarge();
  report({phase: "parse", fraction: null});
  await nextPaint();
  const parseStart = performance.now();
  const script = parseRunScript(answer.body);
  measure("fal:run:parse", parseStart, {json: script !== null});
  if (script) return columnsOf(script);
  return scriptRun(url, key, report);
}

/** A run over http(s): its store when its entry in runs.js has one, else (or when a store's file is missing) its
 *  data.js (`url`). */
async function fromServer(url: string, key: string, report: OnProgress): Promise<RunData> {
  report({phase: "download", fraction: null});
  const store = await storeOf(url);
  if (!store) return downloadRun(url, key, report);
  try {
    return Object.assign(await downloadStore(new URL(".", new URL(url, location.href)).href, key, report, store, true), {fromStore: true});
  } catch (e) {
    if (e instanceof StoreMissing || (store === STORE_PROBE && e instanceof StoreNotFetched)) {
      return downloadRun(url, key, report);
    }
    throw e;
  }
}

/** The store asked for when no list names the run (storeOf): its files are fetched as a listed store's, a 404
 *  reads data.js, and a newer format is refused by the file's own metadata (readStore), whatever this says. */
export const STORE_PROBE: Readonly<StoreInfo> = Object.freeze({format: STORE_FORMAT, lines: 0, bytes: 0, sha256: ""});

/** The store to read for the run whose data.js is at `url` (its folder's name is the run's id): its block `store`
 *  in the list of runs the page has (window.FINDALINE_RUNS: a map.html's own runs.js, or the list loaded before),
 *  else in `../runs.js` beside its folder, loaded once; null for a run listed without one (data.js). A run that list
 *  does not name, and a share link (/s/<token>/: its runs.js lists no runs, so none is asked for), get STORE_PROBE:
 *  the store's files asked for directly, no list read again. */
export async function storeOf(url: string): Promise<StoreInfo | null> {
  const at = new URL(url, location.href), parts = at.pathname.split("/");
  if (parts.length < 3 || parts[parts.length - 1] !== "data.js") return null;
  if (at.pathname.startsWith("/s/")) return STORE_PROBE;
  const id = decodeURIComponent(parts[parts.length - 2]);
  const runs = window.FINDALINE_RUNS ?? await loadRunList(new URL("../runs.js", at).href);
  const run = runs.find((r) => r.id === id);
  return run ? run.store ?? null : STORE_PROBE;
}

/** A run's store in `folder` (an absolute URL ending in "/"): lines.arrow and, with `profiles`, profiles.arrow,
 *  downloaded together with one progress, read into columns (readStore). Without profiles (Compare's other runs, as
 *  their lines.js) the lines have none. */
async function downloadStore(folder: string, key: string, report: OnProgress, store: StoreInfo,
                             profiles: boolean): Promise<RunData> {
  if (!(store.format <= STORE_FORMAT)) throw new NewerStore();
  const start = performance.now(), names = profiles ? STORE_FILES : STORE_FILES.slice(0, 1);
  const totals: (number | null | undefined)[] = names.map(() => undefined), done = names.map(() => 0);
  let refused = false;  // an answer other than 200: its body is no part of the run, no progress from it
  const sum = (values: (number | null | undefined)[]) => values.every((v) => typeof v === "number")
    ? (values as number[]).reduce((a, b) => a + b, 0) : null;
  const progress = () => {
    if (refused || !totals.every((v) => v !== undefined)) return;
    const total = sum(totals), got = done.reduce((a, b) => a + b, 0);
    report({phase: "download", fraction: total ? Math.min(1, got / total) : null, done: got, total});
  };
  report({phase: "download", fraction: null});
  const answers = await Promise.all(names.map((name, k) => download(folder + name, "arraybuffer", {
    onHeaders: (total, status) => { refused ||= status !== 200; totals[k] = total; progress(); },
    onBytes: (bytes) => { done[k] = bytes; progress(); },
  }))).catch(() => { throw new StoreNotFetched(key, "the download failed"); });
  if (answers.some((a) => a.status === 404)) throw new StoreMissing();
  for (const answer of answers) {
    if (answer.status !== 200) throw new StoreNotFetched(key, String(answer.status));
    // The XHR gives null when it could not allocate the body's ArrayBuffer (XMLHttpRequest standard, "response")
    if (!answer.body && answer.bytes > 0) throw new TooLarge();
  }
  measure("fal:run:download", start, {bytes: sum(answers.map((a) => a.bytes)), store: true});
  report({phase: "parse", fraction: null});
  await nextPaint();
  try {
    return readStore(answers[0].body, profiles ? answers[1].body : null);
  } catch (e) {
    throw e instanceof NewerStore ? e : new StoreFailed(key, e instanceof Error ? e.message : String(e));
  }
}

/** A store's Arrow file (`bytes`, the whole file) as its one record batch and its metadata `findaline`; a store of
 *  a higher format is refused before its batch is read. */
function storeBatch(bytes: ArrayBuffer): {batch: RecordBatch; meta: StoreMeta} {
  const reader = RecordBatchReader.from(new Uint8Array(bytes));
  reader.open();
  const meta = metaOf(reader.schema);
  if (!reader.isFile() || reader.numRecordBatches !== 1) throw new Error("a store of more than one batch");
  const batch = reader.readRecordBatch(0);
  if (!batch) throw new Error("a store without its batch");
  return {batch, meta};
}

interface StoreMeta {
  format: number;
  head?: RunHead;
  negative_zero?: Record<string, number[]>;
}

function metaOf(schema: Schema): StoreMeta {
  const raw = schema.metadata.get(META_KEY);
  if (raw === undefined) throw new Error("not a store of Find-a-Line");
  const meta = parseLoose(raw) as StoreMeta;
  if (typeof meta.format !== "number" || !(meta.format <= STORE_FORMAT)) throw new NewerStore();
  return meta;
}

/** JSON as Python's json.dumps writes it, also with NaN, Infinity and -Infinity outside strings (a head's value may
 *  be one: data.js is then read as a script), which JSON.parse refuses: each such token becomes a marked string
 *  first and its number again. */
export function parseLoose(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    const MARK = "\u0000fal:";
    const marked = text.replace(/"(?:[^"\\]|\\.)*"|-?Infinity|NaN/g, (m) => m[0] === "\"" ? m : JSON.stringify(MARK + m));
    return JSON.parse(marked, (_, v) => typeof v === "string" && v.startsWith(MARK) ? Number(v.slice(MARK.length)) : v);
  }
}

/** The validity bits of a column's data: null when no value misses. */
function validOf(data: Data): Uint8Array | null {
  if (data.offset !== 0) throw new Error("a store's column with an offset");
  return data.nullCount > 0 ? data.nullBitmap ?? null : null;
}

/** Bit i of validity bits (null: every value valid). */
const isValid = (valid: Uint8Array | null, i: number) => valid === null || (valid[i >> 3] & (1 << (i & 7))) !== 0;

/** The one Data of a batch's column `name`, or null when the store does not hold it. */
function dataOf(batch: RecordBatch, name: string): Data | null {
  const vector = batch.getChild(name);
  if (!vector) return null;
  if (vector.data.length !== 1) throw new Error("a store's column of several parts");
  return vector.data[0];
}

/** A store's lines.arrow (and profiles.arrow, or null: no profiles) as the run the page keeps: the head from the
 *  metadata, the lines as columns over the files' own buffers (types.ts storedColumns). An integer column of a
 *  scaled value (the field's `decimals`) and a count keep their arrays, a float64 one too (a value no integer held
 *  exactly); only int64 and uint64 ones (values beyond int32 once scaled, counts beyond uint32: rare) are copied
 *  into doubles, which hold them exactly below 2^53 (linestore never writes larger). */
export function readStore(lines: ArrayBuffer, profiles: ArrayBuffer | null): RunData {
  const parseStart = performance.now();
  const {batch, meta} = storeBatch(lines);
  if (!meta.head) throw new Error("a store without its head");
  const zeros = meta.negative_zero ?? {}, n = batch.numRows, stored = new Map<string, StoredColumn>();
  let over: Uint8Array | null = null;
  for (const field of batch.schema.fields) {
    const data = dataOf(batch, field.name)!, valid = validOf(data), type = data.type;
    if (field.name === "over") {
      over = data.values as Uint8Array;
      continue;
    }
    const decimals = field.metadata.get("decimals");
    const scale = decimals !== undefined ? 10 ** Number(decimals) : type.typeId === Type.Int ? 1 : 0;
    const negZero = zeros[field.name] ?? [];
    let values = data.values as StoredColumn["values"] | BigInt64Array | BigUint64Array;
    if (values instanceof BigInt64Array || values instanceof BigUint64Array) {
      const wide = values, doubles = new Float64Array(n);
      for (let i = 0; i < n; i++) doubles[i] = isValid(valid, i) ? Number(wide[i]) / scale : NaN;
      for (const i of negZero) doubles[i] = -0;
      stored.set(field.name, {values: doubles, scale: 0, valid, negZero: []});
      continue;
    }
    stored.set(field.name, {values, scale, valid, negZero});
  }
  if (!over) throw new Error("the run's store has no column over");
  const head = meta.head;
  const profileSource: ProfileSource = profiles ? storedProfiles(profiles) : new Map<number, Profile>();
  measure("fal:run:parse", parseStart, {store: true});
  const columns: LineColumns = timed("fal:run:lines", () => storedColumns(n, stored, over!, head.terrain, profileSource),
                                     {count: n, store: true});
  const view = viewColumns(stored, n);
  return view ? {...head, columns, view} : {...head, columns};
}

/** The result view's columns of a store (linestore.VIEW: `spot` uint32, `top` uint8, `by_spot` uint32, none
 *  missing), as the file's own arrays; null for a store without them (a run saved before the view's columns) or
 *  whose three are not of these types and of one value per line. */
function viewColumns(stored: Map<string, StoredColumn>, n: number): ViewColumns | null {
  const of = (name: string) => { const c = stored.get(name); return c && c.valid === null ? c.values : null; };
  const spot = of("spot"), top = of("top"), bySpot = of("by_spot");
  if (!(spot instanceof Uint32Array) || !(top instanceof Uint8Array) || !(bySpot instanceof Uint32Array)) return null;
  if (spot.length !== n || top.length !== n || bySpot.length !== n) return null;
  return {spot, top, bySpot};
}

/** profiles.arrow as the run's profiles by row: each made when it is asked for (lineAt), as helpers.line_profile's
 *  dict that data.js holds (NaN of the terrain and surface as null, `s`, `w`, `g`, `min_nmpt` null when absent,
 *  `zone` and `lift` only for a profile with them); the file's arrays are kept, not copied. */
export function storedProfiles(bytes: ArrayBuffer): ProfileSource {
  const {batch} = storeBatch(bytes);
  const rowData = dataOf(batch, "row");
  if (!rowData) throw new Error("a store's profiles without their rows");
  const rows = rowData.values as Uint32Array, count = batch.numRows;
  const list = (name: string) => {
    const data = dataOf(batch, name);
    return data && {at: data.valueOffsets as Int32Array, values: data.children[0].values as Float64Array | Uint8Array,
                    valid: validOf(data)};
  };
  const pairs = (name: string) => {
    const data = dataOf(batch, name)!;
    return {values: data.children[0].values as Float64Array, valid: validOf(data)};
  };
  const numbers = (name: string) => {
    const data = dataOf(batch, name);
    return data && {values: data.values as Float64Array, valid: validOf(data)};
  };
  const d = list("d")!, z = list("z")!, s = list("s"), w = list("w"), g = list("g");
  const least = pairs("min"), nmpt = pairs("min_nmpt"), highest = pairs("max_height");
  const water = numbers("water_m")!, filled = numbers("filled_m")!, zone = numbers("zone"), lift = numbers("lift");
  type List = NonNullable<ReturnType<typeof list>>;
  const points = (l: List, k: number) => Array.from(l.values.subarray(l.at[k], l.at[k + 1]),
                                                    (v) => v === v ? v : null);  // NaN: no data there (null)
  const flags = (l: List | null, k: number) => l && isValid(l.valid, k)
    ? Array.from(l.values.subarray(l.at[k], l.at[k + 1])) : null;
  const pair = (p: ReturnType<typeof pairs>, k: number): [number, number] | null =>
    isValid(p.valid, k) ? [p.values[2 * k], p.values[2 * k + 1]] : null;
  return {
    get(row: number): Profile | undefined {
      let lo = 0, hi = count - 1;  // the rows in their order (linestore.profiles_table)
      while (lo <= hi) {
        const mid = (lo + hi) >> 1, r = rows[mid];
        if (r === row) {
          const k = mid, profile: Profile = {
            min: pair(least, k)!, min_nmpt: pair(nmpt, k), max_height: pair(highest, k)!,
            d: Array.from(d.values.subarray(d.at[k], d.at[k + 1])), z: points(z, k),
            s: s && isValid(s.valid, k) ? points(s, k) : null, w: flags(w, k), water_m: water.values[k],
            g: flags(g, k), filled_m: filled.values[k]};
          if (zone && lift && isValid(zone.valid, k)) {  // with the run's end zone or A-frames (both, or neither)
            profile.zone = zone.values[k];
            profile.lift = lift.values[k];
          }
          return profile;
        }
        if (r < row) lo = mid + 1; else hi = mid - 1;
      }
      return undefined;
    },
  };
}

/** Another run's lines for Compare (RunActions): from its store when its entry has one and the page is served
 *  (lines.arrow only: no profiles, as its lines.js), else, or when lines.arrow is missing, its lines.js (`lines`:
 *  others.loadLines). */
export async function loadOtherRun<T>(run: RunInfo, base: string, lines: (id: string, base: string) => Promise<T>):
    Promise<RunData | T> {
  if (!run.store || !overHttp()) return lines(run.id, base);
  const folder = new URL(base + encodeURIComponent(run.id) + "/", location.href).href;
  try {
    return await downloadStore(folder, run.id, () => undefined, run.store, false);
  } catch (e) {
    if (e instanceof StoreMissing) return lines(run.id, base);
    throw e;
  }
}

/** A run's lines for Home's mini map (app/c/Thumb.tsx): lines.arrow only (no profiles.arrow), as Compare's. `listed`
 *  is the run's entry in the list of runs (loadRunList), undefined when the list does not name it: a listed run is
 *  read as loadOtherRun reads it (its store, a 404 reading its lines.js while runs keep it; without a store its
 *  lines.js). A run the list does not name (saved since the list was read: it is loaded once) asks for its
 *  lines.arrow directly, as storeOf's STORE_PROBE: a 404 or a file not fetched reads its lines.js (`lines`:
 *  others.loadLines), and a store of a newer format is refused by the file's own metadata, never read as an old run. */
export async function loadRunLines<T>(id: string, listed: RunInfo | undefined, base: string,
                                      lines: (id: string, base: string) => Promise<T>): Promise<RunData | T> {
  if (listed) return loadOtherRun(listed, base, lines);
  if (!overHttp()) return lines(id, base);
  const folder = new URL(base + encodeURIComponent(id) + "/", location.href).href;
  try {
    return await downloadStore(folder, id, () => undefined, STORE_PROBE, false);
  } catch (e) {
    if (e instanceof StoreMissing || e instanceof StoreNotFetched) return lines(id, base);
    throw e;
  }
}

function scriptRun(url: string, key: string, report: OnProgress): Promise<RunData> {
  return scriptValue(url, key, report).then(columnsOf);
}

/** data.js's value loaded as a script. */
function scriptValue(url: string, key: string, report: OnProgress): Promise<RunScript> {
  report({phase: "download", fraction: null});
  return new Promise<RunScript>((resolve, reject) => {
    const script = document.createElement("script"), start = performance.now();
    script.src = url;
    // A script's load event comes right after it ran, before any other script: FINDALINE_RUN is its own
    script.onload = () => {
      measure("fal:run:script", start);
      const data = window.FINDALINE_RUN;
      delete window.FINDALINE_RUN;
      script.remove();
      if (data) resolve(data); else reject(new Error("no run data in " + url));
    };
    script.onerror = () => {
      script.remove();
      reject(new Error("could not load the run " + key));
    };
    document.head.appendChild(script);
  });
}

/** The run's orthophoto for the app's page: its cache folder is relative to the run's map.html
 * (`<base><id>/map.html`), the app's page is elsewhere. */
export function orthoForApp(ortho: Ortho | null, runId: string, base = "/runs/"): Ortho | null {
  if (!ortho || !ortho.cache) return ortho;
  const map = `${location.origin}${base}${encodeURIComponent(runId)}/map.html`;
  return {...ortho, cache: new URL(ortho.cache, map).pathname};
}

/** Forget a loaded run (e.g. after it was deleted). */
export function forgetRun(id: string) {
  loaded.delete(id);
}

let runList: Promise<RunInfo[]> | null = null;

/** The runs the user may open as the maps list them (`/runs/runs.js`: window.FINDALINE_RUNS, with their
 * boxes for "other runs nearby"), loaded once; empty when it cannot be loaded. Its FINDALINE_APP (the
 * public site's flags) is set as for a map. */
export function loadRunList(src = "/runs/runs.js"): Promise<RunInfo[]> {
  if (runList) return runList;
  runList = new Promise<RunInfo[]>((resolve) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => { script.remove(); resolve(window.FINDALINE_RUNS || []); };
    script.onerror = () => { script.remove(); runList = null; resolve([]); };
    document.head.appendChild(script);
  });
  return runList;
}
