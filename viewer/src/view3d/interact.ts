// The pure parts of the 3D view's interaction (docs/3d-view-contract.md, "Wave 3", V3a; tested in Node:
// tests/test_viewer.py): a pointer's place along the span, the walk's start, when the pin shows, the line of
// moved anchors for /api/profile and the queue of its requests (one in flight, the newest wins).

/** A point or direction in the scene's axes. */
export type Vec3 = [number, number, number];

/** The fraction t ∈ [0, 1] of the segment p → q nearest to the ray from `origin` along `dir` (the pointer's ray):
 *  where the walker goes when dragged. A ray parallel to the segment gives the end nearer its origin. */
export function nearestOnSegment(origin: Vec3, dir: Vec3, p: Vec3, q: Vec3): number {
  const u: Vec3 = [q[0] - p[0], q[1] - p[1], q[2] - p[2]];
  const w: Vec3 = [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]];
  const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const a = dot(u, u), b = dot(u, dir), c = dot(dir, dir), d = dot(u, w), e = dot(dir, w);
  if (!(a > 0) || !(c > 0)) return 0;
  const den = a * c - b * b;
  // the closest points of the two lines: s along the segment, r along the ray; parallel, or the point behind the
  // camera (r < 0): the point of the segment nearest the ray's origin
  let s = -d / a;
  if (den > 1e-12 * a * c) {
    const sl = (b * e - c * d) / den;
    if ((e + sl * b) / c >= 0) s = sl;
  }
  return Math.min(1, Math.max(0, s));
}

/** Where a walk starts: from the walker's place, or from the first anchor when it stands at the second. */
export function walkFrom(s: number, span: number): number {
  return s >= span - 1e-6 ? 0 : Math.max(0, s);
}

/** The walker's height on the screen below which the pin shows above it (CSS pixels). */
export const PIN_BELOW_PX = 20;

export function pinShown(px: number): boolean {
  return px < PIN_BELOW_PX;
}

/** /api/profile's `line` of two points given as [lon, lat]: "lat1,lon1,lat2,lon2", 7 decimals. */
export function lineParam(a: [number, number], b: [number, number]): string {
  return [a[1], a[0], b[1], b[0]].map((v) => v.toFixed(7)).join(",");
}

/** The pause after a release before the profile is asked for (ms). */
export const PROFILE_DELAY = 300;

export type Outcome<T> = {key: string; value: T} | {key: string; error: unknown};

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface ProfileQueue {
  /** A release: `key` is asked for after `delay` ms without another push (and once nothing is in flight). */
  push(key: string): void;
  /** Forget what is waiting and ignore the answer in flight (a drag started, or back to the found line). */
  cancel(): void;
  /** Requests sent so far (for tests). */
  readonly sent: number;
}

/** The requests of the moved anchors' profile: debounced, at most one in flight; a push during it waits, and
 *  only the newest waiting key is sent after it; `done` gets an answer only while its key is still the newest
 *  wanted one (not after `cancel` or a later push). */
export function profileQueue<T>(fetch: (key: string) => Promise<T>, done: (outcome: Outcome<T>) => void,
                                delay = PROFILE_DELAY, timers: Timers = globalThis): ProfileQueue {
  let wanted: string | null = null;   // the newest key asked for, null once answered or cancelled
  let waiting: string | null = null;  // pushed, its delay over, waiting for the one in flight
  let timer: unknown = null, inFlight = false, sent = 0;
  const send = (key: string) => {
    inFlight = true;
    sent++;
    const finish = (outcome: Outcome<T>) => {
      inFlight = false;
      if (wanted === key && waiting === null) { wanted = null; done(outcome); }
      if (waiting !== null) { const next = waiting; waiting = null; send(next); }
    };
    fetch(key).then((value) => finish({key, value}), (error) => finish({key, error}));
  };
  const clear = () => { if (timer !== null) { timers.clearTimeout(timer); timer = null; } };
  return {
    push(key) {
      clear();
      wanted = key;
      waiting = null;
      timer = timers.setTimeout(() => {
        timer = null;
        if (wanted !== key) return;
        if (inFlight) waiting = key; else send(key);
      }, delay);
    },
    cancel() { clear(); wanted = null; waiting = null; },
    get sent() { return sent; },
  };
}
