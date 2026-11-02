// The credits of the 3D view, pure (tested in Node: tests/test_view3d_tiles.py): the run's data credits as
// the 2D map shows them (layers.ts creditsHtml, with the run's ATTRIBUTION.txt), and the imagery's: the
// orthophoto's attribution with its link, or "Powered by Esri" and the sources of its imagery. Trusted HTML for
// Scene3D.credits: escaped text and links to http(s) only, built by layers.ts.

import { creditsHtml, esriHtml, orthoHtml } from "../layers";
import type { Credit, Ortho } from "../types";

/** The ids and order of the entries in the page's credits box (low first). */
export const DATA_CREDITS = "data", IMAGERY_CREDITS = "imagery";
export const DATA_ORDER = 1, IMAGERY_ORDER = 2;

/** The run's ATTRIBUTION.txt (web.RUN_FILES), the full notices. */
export function noticesUrl(runId: string, base = "/runs/"): string {
  return base + encodeURIComponent(runId) + "/ATTRIBUTION.txt";
}

function isCredit(c: unknown): c is Credit {
  const v = c as Credit;
  return !!v && typeof v === "object" && typeof v.attribution === "string" && typeof v.licence === "string";
}

/** The data credits of the meta's `attribution` (data.js's), null when it holds none. */
export function dataCredits(attribution: unknown, runId: string): string | null {
  const credits = Array.isArray(attribution) ? attribution.filter(isCredit) : [];
  return credits.length ? creditsHtml(credits.map((c) => ({...c, url: typeof c.url === "string" ? c.url : ""})),
                                      noticesUrl(runId)) : null;
}

/** The credits of the imagery shown, null for the shaded terrain. */
export function imageryCredits(kind: "ortho" | "esri" | "shaded", ortho: Ortho | null): string | null {
  if (kind === "ortho" && ortho) return orthoHtml(ortho);
  if (kind === "esri") return esriHtml();
  return null;
}
