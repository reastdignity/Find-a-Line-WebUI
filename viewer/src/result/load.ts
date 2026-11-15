// A run's data for the app and a run's map.html: its data.js (window.FINDALINE_RUN = {...};). Over http(s) it
// is downloaded (download.ts: XMLHttpRequest) and its bytes counted for the progress bar (against SIZE_HEADER,
// the size web.RunFiles gives before nginx gzips it, or Content-Length when nothing compressed it), then read by
// JSON.parse (measured 2026-11-04: about 30 % faster than the script; tools/perf_run_load.py). A file JSON.parse refuses (NaN,
// Infinity: runs.column_texts writes them) is loaded as a script instead, from the HTTP cache, so every value
// stays as the script gives it. From disk (file://: no fetch) it is a script, which the CSP (script-src
// 'self') allows and web.RunFiles serves only to who may open the run. The lines of other runs still come
// from their lines.js (others.loadLines).
//
// The rows are then read into columns (types.ts runData: docs/line-volume/spec-store.md 1.2, store wave 1) and
// dropped: the page keeps the run's lines as typed arrays (RunData.columns). A body that arrives empty although its
// bytes came is longer than the browser's longest string (Chromium: 536 870 888 characters, about 2.3 M lines of
// today's data.js; the XHR's text is then "" with no error): the load fails with TooLarge, whose message the page
// shows, and is not tried as a script (which crashed the tab: part E2 of the line-volume study).

import { download } from "../download";
import { t } from "../i18n";
import { measure, timed } from "../perf";
import { nextPaint } from "../paint";
import { runData, type Ortho, type RunData, type RunInfo, type RunScript } from "../types";

const PREFIX = "window.FINDALINE_RUN = ";  // mapping._script_head of data.js

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
    entry.promise = overHttp() ? downloadRun(url, key, report) : scriptRun(url, key, report);
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
