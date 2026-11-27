// What the 3D view's page is asked for: the run and line of its hash (#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>,
// as /api/profile's line) and the level (?level=phone|full, else a coarse pointer is a phone). Pure but for
// `currentPage`, so tests can give their own location. The page has two addresses: the app's /view3d and a share
// link's /s/<token>/view3d (sharelink.ts shareToken: link mode), whose way back is the link's map.html.

import type { Line } from "../types";
import type { ResultModel } from "../result/model";
import { runHash } from "../app/c/route";
import { lineHash } from "../sharelink";

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
 *  line's key) instead of the page's own. With `link` (a share link's 3D view) the link's own map instead, relative:
 *  map.html with its hash of the line (map/main.tsx, sharelink.ts lineHash). */
export function backUrl(p: PageRequest, line: string | null = p.line, link = false): string {
  return link ? "map.html" + lineHash(line) : "/" + runHash(p.run, line);
}

/** The 3D view's address for the line now shown (the "Copy link" button): this page's path (`path`: the app's
 *  /view3d, or a share link's /s/<token>/view3d) and the hash of the request, the level kept only when the address
 *  asked for one (`search`), so a link opened on a phone chooses its own, and the other lines (`also`, by default the
 *  address's own; never the line itself). Relative to the origin. */
export function viewUrl(p: PageRequest, line: string | null, search: string, also: readonly string[] = p.also,
                        path = "/view3d"): string {
  const asked = new URLSearchParams(search).get("level");
  const level = asked === "phone" || asked === "full" ? `?level=${asked}` : "";
  const self = line && isKey(line) ? canonicalKey(line) : null;
  return `${path}${level}` + runHash(p.run, line) + (line ? alsoParam(also.filter((k) => k !== self)) : "");
}

/** The 2D result's link to a line's 3D view (the button "3D view", LineDetails and SpotActions): `base` and the hash
 *  of the run's page with the line and, for a spot of several lines, the others of the spot in the model's order
 *  (`&also=`, at most OTHERS_MAX); a line alone in its spot gets the link it always had. `base`: the app's "/view3d"
 *  (app/c/ResultPage.tsx), a share link's map "view3d" (relative: /s/<token>/view3d, map/main.tsx). */
export function view3dLink(base: string) {
  return (model: Pick<ResultModel, "runOf" | "lineLink" | "alsoOf">, l: Line): string =>
    base + runHash(model.runOf(l), model.lineLink(l)) + alsoParam(model.alsoOf(l, OTHERS_MAX).map((m) => model.lineLink(m)));
}
