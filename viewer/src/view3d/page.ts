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

/** The app's page of the run with the line selected (app/c/route.ts runHash); `line`: the line now shown (a moved
 *  line's key) instead of the page's own. */
export function backUrl(p: PageRequest, line: string | null = p.line): string {
  return `/#run=${encodeURIComponent(p.run)}` + (line ? `&line=${encodeURIComponent(line)}` : "");
}

/** The 3D view's address for the line now shown (the "Copy link" button): this page's path and the hash of the
 *  request, the level kept only when the address asked for one (`search`), so a link opened on a phone chooses its
 *  own. Relative to the origin. */
export function viewUrl(p: PageRequest, line: string | null, search: string): string {
  const asked = new URLSearchParams(search).get("level");
  const level = asked === "phone" || asked === "full" ? `?level=${asked}` : "";
  return `/view3d${level}#run=${encodeURIComponent(p.run)}` + (line ? `&line=${encodeURIComponent(line)}` : "");
}
