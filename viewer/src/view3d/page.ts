// What the 3D view's page is asked for: the run and line of its hash (#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>,
// as /api/profile's line) and the level (?level=phone|full, else a coarse pointer is a phone). Pure but for
// `currentPage`, so tests can give their own location.

export type Level = "phone" | "full";

/** The most other lines the address hands over and the view draws (docs/3d-view-contract.md, round 2, point 7). */
export const OTHERS_MAX = 20;

export interface PageRequest {
  run: string;
  /** "lat1,lon1,lat2,lon2" as it came, or null when it is not four finite numbers. */
  line: string | null;
  level: Level;
  /** The other lines of the address (`&also=<line>;<line>…`, the 2D result's spot of the line): each a line key as
   *  `canonicalKey` writes it, bad entries, repeats and the line itself dropped, at most OTHERS_MAX. */
  also: string[];
}

/** Four finite numbers separated by commas. */
const isKey = (key: string) => {
  const numbers = key.split(",");
  return numbers.length === 4 && numbers.every((v) => v.trim() !== "" && isFinite(Number(v)));
};

/** A line's key as the 2D result writes it (JavaScript's numbers, keys.ts lineCoords): "50.1234500,19.5" is
 *  "50.12345,19.5". Every comparison of keys goes through it (save.ts re-exports it). */
export function canonicalKey(key: string): string {
  return key.split(",").map(Number).join(",");
}

/** The lines of `&also=`'s value: entries separated by ";", the bad ones dropped, each in its canonical form, a
 *  repeat and `line` itself left out, at most `max` kept. */
export function parseAlso(value: string | null, line: string | null = null, max = OTHERS_MAX): string[] {
  const out: string[] = [], skip = line && isKey(line) ? canonicalKey(line) : null;
  for (const entry of (value || "").split(";")) {
    if (out.length >= max) break;
    if (!isKey(entry)) continue;
    const key = canonicalKey(entry);
    if (key !== skip && !out.includes(key)) out.push(key);
  }
  return out;
}

/** The address' part for other lines (`&also=…`, the keys joined by ";"), empty for none: the 2D result's link
 *  for a line alone in its spot stays what it was. */
export function alsoParam(keys: readonly string[], max = OTHERS_MAX): string {
  const kept = keys.slice(0, max);
  return kept.length ? "&also=" + encodeURIComponent(kept.join(";")) : "";
}

/** The request of a page at `search` and `hash`; `coarse`: the device's pointer is coarse. */
export function parsePage(search: string, hash: string, coarse: boolean): PageRequest {
  const query = new URLSearchParams(search), params = new URLSearchParams(hash.replace(/^#/, ""));
  const asked = query.get("level");
  const level: Level = asked === "phone" || asked === "full" ? asked : coarse ? "phone" : "full";
  const line = params.get("line") || "";
  const valid = isKey(line);
  return {run: params.get("run") || "", line: valid ? line : null, level,
          also: parseAlso(params.get("also"), valid ? line : null)};
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
 *  own, and the other lines (`also`, by default the address's own; never the line itself). Relative to the origin. */
export function viewUrl(p: PageRequest, line: string | null, search: string, also: readonly string[] = p.also): string {
  const asked = new URLSearchParams(search).get("level");
  const level = asked === "phone" || asked === "full" ? `?level=${asked}` : "";
  const self = line && isKey(line) ? canonicalKey(line) : null;
  return `/view3d${level}#run=${encodeURIComponent(p.run)}` + (line ? `&line=${encodeURIComponent(line)}` : "") +
         (line ? alsoParam(also.filter((k) => k !== self)) : "");
}
