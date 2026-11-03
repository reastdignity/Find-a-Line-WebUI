// What the 3D view's page is asked for: the run and line of its hash (#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>,
// as /api/profile's line) and the level (?level=phone|full, else a coarse pointer is a phone). Pure but for
// `currentPage`, so tests can give their own location.

export type Level = "phone" | "full";

export interface PageRequest {
  run: string;
  /** "lat1,lon1,lat2,lon2" as it came, or null when it is not four finite numbers. */
  line: string | null;
  level: Level;
}

/** The request of a page at `search` and `hash`; `coarse`: the device's pointer is coarse. */
export function parsePage(search: string, hash: string, coarse: boolean): PageRequest {
  const query = new URLSearchParams(search), params = new URLSearchParams(hash.replace(/^#/, ""));
  const asked = query.get("level");
  const level: Level = asked === "phone" || asked === "full" ? asked : coarse ? "phone" : "full";
  const line = params.get("line") || "";
  const numbers = line.split(",");
  const valid = numbers.length === 4 && numbers.every((v) => v.trim() !== "" && isFinite(Number(v)));
  return {run: params.get("run") || "", line: valid ? line : null, level};
}

/** The page's own request. */
export function currentPage(): PageRequest {
  const coarse = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  return parsePage(location.search, location.hash, coarse);
}

/** /api/patch's address for a request: phones take every second sample (step 2). */
export function patchUrl(p: PageRequest): string {
  return `/api/patch?run=${encodeURIComponent(p.run)}&line=${encodeURIComponent(p.line || "")}` +
         `&step=${p.level === "phone" ? 2 : 1}`;
}

/** The app's page of the run with the line selected (app/c/route.ts runHash). */
export function backUrl(p: PageRequest): string {
  return `/#run=${encodeURIComponent(p.run)}` + (p.line ? `&line=${encodeURIComponent(p.line)}` : "");
}
