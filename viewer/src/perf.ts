// The loading phases of a run's result and of the 3D view as User Timing measures named "fal:<page>:<phase>"
// (performance.getEntriesByType("measure")), which tools/perf_run_load.py reads from the page. Cheap, and
// nothing reads them in the page itself.

/** A measure `name` from `start` (a performance.now()) until now, with `detail` (e.g. a count). */
export function measure(name: string, start: number, detail?: unknown) {
  try {
    performance.measure(name, {start, end: performance.now(), detail});
  } catch { /* a browser without User Timing Level 3: no measure */ }
}

/** `f()` measured as `name`. */
export function timed<T>(name: string, f: () => T, detail?: unknown): T {
  const start = performance.now();
  try {
    return f();
  } finally {
    measure(name, start, detail);
  }
}
