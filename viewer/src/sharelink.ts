// A share link's pages (/s/<token>/map.html and the link's 3D view /s/<token>/view3d) and the computed requests of
// every page (docs/3d-view-contract.md, "Share links (2026-11-26)"): the token of the page's own address, which every
// request of /api/profile (also Measure), /api/patch (also its canopy part) and /api/reach carries in the header
// X-Findaline-Share (never in an address: the server knows the link's run by it); and the wait after a 429 of such a
// request (users' pages and links' alike): no request of that kind until the answer's Retry-After has passed (60 s
// when it has none), the server's text given again meanwhile. No imports: the 2D bundles and the 3D view's (without
// Leaflet) take it, and the Node units run it with their own address and clock.

/** web.py: the header of a share link's computed requests. */
export const SHARE_HEADER = "X-Findaline-Share";

/** A share link's page: /s/<token>/<page> (token_urlsafe's alphabet; /s/runs.js and the like are no link's page). */
const LINK_PAGE = /^\/s\/([A-Za-z0-9_-]+)\/[^/]*$/;
/** web.VIEWER: the viewer's own folder (/s/_viewer/viewer.js), no link's. */
const VIEWER = "_viewer";

const here = (): string => typeof location !== "undefined" ? location.pathname : "";

/** The share token of a link's page at `path` (default: this page's), null for every other page. */
export function shareToken(path: string = here()): string | null {
  const found = LINK_PAGE.exec(path);
  return found && found[1] !== VIEWER ? found[1] : null;
}

/** The headers of a computed request: `headers` and, on a share link's page, SHARE_HEADER with its token. */
export function computedHeaders(headers: Record<string, string>, path: string = here()): Record<string, string> {
  const token = shareToken(path);
  return token === null ? headers : {...headers, [SHARE_HEADER]: token};
}

/** The 2D page's hash of a line (map/main.tsx: #line=lat1,lon1,lat2,lon2, keys.ts lineCoords), empty for none. */
export function lineHash(line: string | null): string {
  return line ? "#line=" + encodeURIComponent(line) : "";
}

/** The kinds of computed requests, each waited for on its own after a 429 (canopy is a patch: one endpoint). */
export type Kind = "profile" | "patch" | "reach";

/** The wait after a 429 whose answer names none (the contract: 60 s). */
export const RETRY_DEFAULT_S = 60;

/** Seconds of a Retry-After header: a whole number of at least 1, else RETRY_DEFAULT_S (missing, a date, junk). */
export function retrySeconds(header: string | null | undefined): number {
  const text = (header ?? "").trim();
  if (!/^\d+$/.test(text)) return RETRY_DEFAULT_S;
  const seconds = Number(text);
  return seconds >= 1 ? seconds : RETRY_DEFAULT_S;
}

/** The waits after a 429, per kind: `refused` starts one (the answer's Retry-After and the text shown), `blocked`
 *  gives the text while it lasts, else null. No timer: the deadline is compared when a request is about to go. */
export class Backoff {
  private readonly until = new Map<Kind, {at: number; text: string}>();

  constructor(private readonly now: () => number = () => Date.now()) {}

  refused(kind: Kind, retryAfter: string | null | undefined, text: string): void {
    this.until.set(kind, {at: this.now() + retrySeconds(retryAfter) * 1000, text});
  }

  blocked(kind: Kind): string | null {
    const wait = this.until.get(kind);
    if (!wait) return null;
    if (this.now() < wait.at) return wait.text;
    this.until.delete(kind);
    return null;
  }
}

/** The page's waits (one per bundle: a page loads one of them). */
export const BACKOFF = new Backoff();

/** Before a computed request of `kind`: throws the server's text while a 429's wait lasts. */
export function checkBackoff(kind: Kind, backoff: Backoff = BACKOFF): void {
  const text = backoff.blocked(kind);
  if (text !== null) throw new Error(text);
}

/** After an answer of a computed request of `kind` that was not ok: a 429 starts the wait (`retryAfter`: its
 *  Retry-After header; `text`: what the page shows, the server's message). */
export function noteRefusal(kind: Kind, status: number, retryAfter: string | null | undefined, text: string,
                            backoff: Backoff = BACKOFF): void {
  if (status === 429) backoff.refused(kind, retryAfter, text);
}
