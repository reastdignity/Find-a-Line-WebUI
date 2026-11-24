// A run's data for the app and a run's map.html over http(s): its store, lines.arrow and profiles.arrow (store
// wave 2: run.json's block `store`, which runs.js lists), downloaded together (download.ts: XMLHttpRequest, as
// bytes) and their bytes counted for the progress bar (against SIZE_HEADER, the size web.RunFiles gives before nginx
// compresses it, or Content-Length when nothing compressed it), read with apache-arrow (readStore) into columns
// without a copy (types.ts storedColumns: docs/line-volume/spec-store.md 1.2), the head from the schema's metadata
// `findaline`. The page keeps the run's lines as typed arrays (RunData.columns). Since store wave 4's item 5 a run is
// read only from its store: the reader of data.js and lines.js ended with the runs that held them (removed by
// `findaline.py runs remove-old` on each host first), and a page from disk (file://) loads no run (map/main.tsx shows
// the disk notice).
//
// The run is named by its folder (`<base><id>/`); which store is read is decided by the run's entry in the list of
// runs the page has (storeOf: window.FINDALINE_RUNS, or runs.js beside the run's folder loaded once): its block
// `store`. A run the list does not name (a share link, whose runs.js lists no runs; another user's run an
// administrator opens; a run saved since the list was read) or names without the block asks for its store's files
// directly (STORE_PROBE). A store of a newer format is refused (NewerStore: run.json's block or the file's metadata
// says so); a store that cannot be fetched (404 or another status, a network error) or read is a StoreFailed, whose
// words the page shows (ui.result.store_failed). A body the browser could not hold (a null ArrayBuffer) is TooLarge.
// Only answers of 200 report the download's progress (an error's short body is no part of the run). The lines of
// other runs (Compare) and of Home's mini maps come from their lines.arrow alone (loadOtherRun, loadRunLines).
// A download cut while the page was hidden (a phone's screen off: iOS suspends the page and its requests fail; the
// user's iPhone test of 2026-11-22) is started again, whole, once the page is visible again, with its progress from
// nought: one try per visible spell (watchHidden); the other file's request is ended at the cut (stop), and the try
// after it has a deadline, STALL_MS without an answer or a byte while visible (a request iOS left hanging; time hidden
// or frozen does not count). The retry waits for the browser to be online, at most ONLINE_WAIT_MS. A download that
// fails while the page stays visible is a StoreFailed at once, as before.

import { RecordBatchReader, Type, type Data, type RecordBatch, type Schema } from "apache-arrow";
import { download, type Answer } from "../download";
import { t } from "../i18n";
import { measure, timed } from "../perf";
import { nextPaint } from "../paint";
import { storedColumns, type LineColumns, type Ortho, type Profile, type ProfileSource, type RunData, type RunHead,
         type RunInfo, type StoredColumn, type StoreInfo, type ViewColumns } from "../types";

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

/** A run too large for this browser: the body of its store's file could not be held (a null ArrayBuffer). */
export class TooLarge extends Error {
  constructor() {
    super(t("ui.result.too_large"));
    this.name = "TooLarge";
  }
}

/** A run's store that could not be downloaded (a 404 among them: a run without a store) or read: its message the
 *  catalogue's words the page shows (ui.result.store_failed), `detail` what went wrong, written to the console once
 *  here for every failed load (a run's own, Compare's other run, a mini map), so no caller needs to. */
export class StoreFailed extends Error {
  readonly detail: string;
  constructor(key: string, why: string) {
    super(t("ui.result.store_failed"));
    this.name = "StoreFailed";
    this.detail = `could not load the store of the run ${key} (${why})`;
    console.warn(this.detail);
  }
}

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
  data: RunData | null;  // the run once it is loaded (renamedRun writes its new name there)
}

const loaded = new Map<string, Loading>();

/** The data of run `id` (its store in `<base><id>/`), loaded once; rejects when it cannot be loaded (a failed load
 *  is tried again on the next call). `onProgress` hears the load's phases until it ends. */
export function loadRun(id: string, base = "/runs/", onProgress?: OnProgress): Promise<RunData> {
  return loadRunFrom(base + encodeURIComponent(id) + "/", id, onProgress);
}

/** The run whose folder is `folder` (a URL ending in "/", relative to the page: "./" for a run's own map.html),
 *  kept under `key` (loadRun's run id). Over http(s) only: from disk it rejects (no run is read from disk). */
export function loadRunFrom(folder: string, key: string, onProgress?: OnProgress): Promise<RunData> {
  let loading = loaded.get(key);
  if (!loading) {
    const entry: Loading = {listeners: new Set(), last: null, data: null,
                            promise: Promise.resolve(null as unknown as RunData)};
    const report = (p: LoadProgress) => { entry.last = p; entry.listeners.forEach((f) => f(p)); };
    entry.promise = overHttp() ? fromServer(new URL(folder, location.href).href, key, report)
      : Promise.reject(new StoreFailed(key, "a page from disk reads no run"));
    loaded.set(key, entry);
    entry.promise.then((data) => { entry.data = data; },
                       () => { if (loaded.get(key) === entry) loaded.delete(key); });
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

/** A run over http(s) from its store in `folder` (an absolute URL ending in "/"), with its profiles. Its name is
 *  the list's where the list of runs names the run (listedOf): the store's head keeps the name of the saving, a
 *  rename (runs.rename_run) changes run.json's, which the list gives. The one place where the listed name meets
 *  the loaded run; a page the list does not serve (a share link) names the run itself (map/main.tsx: its title). */
async function fromServer(folder: string, key: string, report: OnProgress): Promise<RunData> {
  report({phase: "download", fraction: null});
  const listed = await listedOf(folder);
  const data = Object.assign(await downloadStore(folder, key, report, listed?.store ?? STORE_PROBE, true), {fromStore: true});
  if (listed && typeof listed.name === "string") data.run.name = listed.name;
  return data;
}

/** The store asked for when no list names the run, or names it without its block (storeOf): its files are fetched
 *  as a listed store's, and a newer format is refused by the file's own metadata (readStore), whatever this says. */
export const STORE_PROBE: Readonly<StoreInfo> = Object.freeze({format: STORE_FORMAT, lines: 0, bytes: 0, sha256: ""});

/** The store to read for the run in `folder` (a URL ending in "/<id>/"): its block `store` in the list of runs the
 *  page has (window.FINDALINE_RUNS: a map.html's own runs.js, or the list loaded before), else in `../runs.js`
 *  beside its folder, loaded once. A run that list does not name or names without the block, and a share link
 *  (/s/<token>/: its runs.js lists no runs, so none is asked for), get STORE_PROBE: the store's files asked for
 *  directly, no list read again. */
export async function storeOf(folder: string): Promise<StoreInfo> {
  return (await listedOf(folder))?.store ?? STORE_PROBE;
}

/** The entry of the run in `folder` (a URL ending in "/<id>/") in the list of runs the page has (storeOf's list);
 *  undefined for a run that list does not name, and on a share link (no list is asked for). */
async function listedOf(folder: string): Promise<RunInfo | undefined> {
  const at = new URL(folder, location.href), parts = at.pathname.split("/");
  if (at.pathname.startsWith("/s/") || parts.length < 3) return undefined;
  const id = decodeURIComponent(parts[parts.length - 2]);
  const runs = window.FINDALINE_RUNS ?? await loadRunList(new URL("../runs.js", at).href);
  return runs.find((r) => r.id === id);
}

/** A run's store in `folder` (an absolute URL ending in "/"): lines.arrow and, with `profiles`, profiles.arrow,
 *  downloaded together with one progress, read into columns (readStore). Without profiles (Compare's other runs,
 *  Home's mini maps) the lines have none. */
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
  let answers: Answer<ArrayBuffer>[], retry = false;
  for (;;) {
    totals.fill(undefined);
    done.fill(0);
    refused = false;
    report({phase: "download", fraction: null});
    const hidden = watchHidden(), stop = new AbortController();
    let heard = performance.now();  // the last answer or byte of this try
    const loads = names.map((name, k) => download(folder + name, "arraybuffer", {
      signal: stop.signal,
      onHeaders: (total, status) => { heard = performance.now(); refused ||= status !== 200; totals[k] = total; progress(); },
      onBytes: (bytes) => { heard = performance.now(); done[k] = bytes; progress(); },
    }));
    // a try after a cut has a deadline: STALL_MS without an answer or a byte while the page is visible
    const stall = retry ? stalled(() => heard, (now) => { heard = now; }) : null;
    try {
      answers = await (stall ? Promise.race([Promise.all(loads), stall.promise]) : Promise.all(loads));
      hidden();
      break;
    } catch (e) {
      const cut = hidden();
      stop.abort();  // the other file's request ends now (iOS may leave one hanging)
      if (e === STALLED) throw new StoreFailed(key, `no answer for ${STALL_MS / 1000} s after the page was hidden`);
      if (!cut) throw new StoreFailed(key, "the download failed");
      // cut while the page was hidden: the whole store again once it is visible (and online, or ONLINE_WAIT_MS on)
      await whenVisible();
      await whenOnline(ONLINE_WAIT_MS);
      retry = true;
    } finally {
      stall?.stop();
    }
  }
  for (const answer of answers) {
    if (answer.status !== 200) throw new StoreFailed(key, String(answer.status));
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
/** How long a try of the store after a cut while hidden may go without an answer or a byte while the page is visible
 *  (the time hidden does not count); then it ends as a StoreFailed (today's message): a request iOS left hanging
 *  must not keep the page waiting. The loader has no other timeout (the browser's own). */
export const STALL_MS = 30000;
const STALLED = new Error("stalled");

/** A tick this much later than the one before it found timers held: the page was frozen (iOS suspends a hidden page,
 *  a browser throttles a hidden tab), so the gap is time hidden. */
const TICK_GAP_MS = 2500;

/** A deadline of STALL_MS after the last answer or byte (`heard`), checked every second: `promise` rejects with
 *  STALLED; `stop` ends the checks. Only time while the page is visible counts: `reset` sets `heard` to now while the
 *  page is hidden, when it becomes visible, and after a tick that came late (TICK_GAP_MS: the page was frozen, its
 *  overdue tick runs once on its return). */
function stalled(heard: () => number, reset: (now: number) => void): {promise: Promise<never>; stop(): void} {
  let timer = 0, last = performance.now();
  const shown = () => { if (document.visibilityState !== "hidden") reset(performance.now()); };
  if (watchable()) document.addEventListener("visibilitychange", shown);
  const stop = () => {
    clearInterval(timer);
    if (watchable()) document.removeEventListener("visibilitychange", shown);
  };
  const promise = new Promise<never>((_, reject) => {
    timer = setInterval(() => {
      const now = performance.now(), late = now - last > TICK_GAP_MS;
      last = now;
      if (late || (watchable() && document.visibilityState === "hidden")) reset(now);
      else if (now - heard() > STALL_MS) { stop(); reject(STALLED); }
    }, 1000) as unknown as number;
  });
  promise.catch(() => undefined);  // a rejection after the race was decided is no error
  return {promise, stop};
}

/** How long a retry waits for the network after the page is visible again: a phone unlocked after a cut may take a
 *  moment to join its network; the retry starts once `navigator.onLine`, at most this late. */
export const ONLINE_WAIT_MS = 2000;

/** Resolves once the browser says it is online, at once when it does, else at the latest after `ms`. */
function whenOnline(ms: number): Promise<void> {
  if (typeof navigator === "undefined" || navigator.onLine !== false || typeof addEventListener !== "function") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const done = () => { clearTimeout(timer); removeEventListener("online", done); resolve(); };
    const timer = setTimeout(done, ms);
    addEventListener("online", done);
  });
}

/** Has the page a document whose visibility can be watched (Node's units run this file with a stand-in or none). */
const watchable = () => typeof document !== "undefined" && typeof document.addEventListener === "function";

/** Watch whether the page is hidden from now on; the function returned ends the watch and tells whether it was hidden
 *  at any time since (a page without a document: never). */
function watchHidden(): () => boolean {
  if (!watchable()) return () => false;
  let hidden = document.visibilityState === "hidden";
  const seen = () => { if (document.visibilityState === "hidden") hidden = true; };
  document.addEventListener("visibilitychange", seen);
  return () => {
    document.removeEventListener("visibilitychange", seen);
    return hidden || document.visibilityState === "hidden";
  };
}

/** Resolves once the page is visible (at once when it is). */
function whenVisible(): Promise<void> {
  if (!watchable() || document.visibilityState !== "hidden") return Promise.resolve();
  return new Promise((resolve) => {
    const seen = () => {
      if (document.visibilityState === "hidden") return;
      document.removeEventListener("visibilitychange", seen);
      resolve();
    };
    document.addEventListener("visibilitychange", seen);
  });
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
 *  be one: the store's metadata is json.dumps'), which JSON.parse refuses: each such token becomes a marked string
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
 *  dict that data.js held (NaN of the terrain and surface as null, `s`, `w`, `g`, `min_nmpt` null when absent,
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

/** Another run's lines for Compare (RunActions): from its lines.arrow only (no profiles), its entry's store or, for
 *  an entry without the block, STORE_PROBE; any failure rejects (StoreFailed, NewerStore). */
export async function loadOtherRun(run: RunInfo, base: string): Promise<RunData> {
  const folder = new URL(base + encodeURIComponent(run.id) + "/", location.href).href;
  return downloadStore(folder, run.id, () => undefined, run.store ?? STORE_PROBE, false);
}

/** A run's lines for Home's mini map (app/c/Thumb.tsx): lines.arrow only (no profiles.arrow), as Compare's.
 *  `listed` is the run's entry in the list of runs (loadRunList), undefined when the list does not name it (saved
 *  since the list was read: it is loaded once): its lines.arrow is asked for directly, as storeOf's STORE_PROBE, and
 *  a store of a newer format is refused by the file's own metadata. Any failure rejects (the card's placeholder). */
export async function loadRunLines(id: string, listed: RunInfo | undefined, base: string): Promise<RunData> {
  if (listed) return loadOtherRun(listed, base);
  const folder = new URL(base + encodeURIComponent(id) + "/", location.href).href;
  return downloadStore(folder, id, () => undefined, STORE_PROBE, false);
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

/** A run was renamed on this page (Home's card, the result view's head; `name` as the server stored it): its
 *  loaded data takes the name, so every reader of the page shows it (the head, the phone's pill, a report's
 *  "about") without a new download, and the list of runs is read again by its next reader (Compare's rows, the
 *  next run opened). */
export function renamedRun(id: string, name: string) {
  const entry = loaded.get(id);
  if (entry?.data) entry.data.run.name = name;
  else entry?.promise.then((data) => { data.run.name = name; }, () => undefined);  // still loading: once it is in
  forgetRunList();
}

let runList: Promise<RunInfo[]> | null = null;

/** Forget the list of runs: its next reader loads it again (loadRunList). For the page that knows the list
 *  changed: a search saved its run, a run was renamed or deleted (AppC, Home). Both copies go, the loaded one and
 *  the script's own window.FINDALINE_RUNS (storeOf reads that one first). */
export function forgetRunList() {
  runList = null;
  if (typeof window !== "undefined") delete window.FINDALINE_RUNS;
}

/** The runs the user may open as the maps list them (`/runs/runs.js`: window.FINDALINE_RUNS, with their
 * boxes for "other runs nearby"), loaded once until forgetRunList; empty when it cannot be loaded. Its
 * FINDALINE_APP (the public site's flags) is set as for a map. */
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
