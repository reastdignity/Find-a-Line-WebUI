// The background layers' keys, URLs and credits without Leaflet (the 2D maps' layers: baselayers.ts; the 3D
// view's imagery: view3d/tiles.ts, view3d/credits.ts) and the data credits of a run.

import type { Credit, Ortho } from "./types";

/** The operator's API key of ArcGIS Location Platform (settings.WebKeys, restricted to the site's address):
 *  from the server's runs.js (window.FINDALINE_APP) or the app page's meta; none on a map opened from disk,
 *  so no satellite map there. Esri's terms: its tiles are never cached or prefetched by us. */
export function esriKey(): string | null {
  const app = typeof window !== "undefined" ? window.FINDALINE_APP : undefined;
  if (app?.esri_key) return app.esri_key;
  const meta = typeof document !== "undefined" ? document.querySelector<HTMLMetaElement>('meta[name="findaline-esri-key"]') : null;
  return meta?.content || null;
}

/** Esri's attribution of World Imagery as ArcGIS Location Platform asks for it ("Powered by Esri" and the
 *  sources of the imagery; the about page says the same: web.py ESRI_SOURCE). */
export const ESRI_SOURCE = "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community";
export const ESRI_NAME = "Esri World Imagery";
/** Esri's native tiles reach z19 nearly everywhere (z20/21 only in places): enlarged above it. */
export const ESRI_MAX_ZOOM = 19;

/** The tiles of Esri World Imagery ({z}/{y}/{x}) with the operator's key. */
export function esriTileUrl(key: string): string {
  return "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=" +
    encodeURIComponent(key);
}

/** Esri's credits: "Powered by Esri" linked to its site, and the sources of the imagery. */
export function esriHtml(): string {
  return linked("Powered by Esri", "https://www.esri.com") + " | " + escape(ESRI_SOURCE);
}

export function escape(text: string): string {
  return text.replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
}

/** Plain text as HTML, a link when `url` is http(s) (Leaflet's attribution control and the 3D view's credits render HTML). */
export function linked(text: string, url: string | null | undefined): string {
  return url && /^https?:\/\//.test(url)
    ? '<a href="' + escape(url) + '" target="_blank" rel="noopener">' + escape(text) + "</a>" : escape(text);
}

/** The orthophoto's attribution: its text, a link to `attribution_url` when the service has one. */
export function orthoHtml(ortho: Ortho): string {
  return linked(ortho.attribution, ortho.attribution_url);
}

/** What every run's credits add (ATTRIBUTION.txt and the about page say the same: runs.py, web.py): the
 *  data were changed. */
export const PROCESSED_NOTE = "Find-a-Line's lines, heights, profiles and maps are computed from these data, " +
  "which were resampled and combined onto a working grid (changed).";

/** The data credits of a run for Leaflet's attribution control, which renders HTML: escaped text, links
 *  to http(s) only, and the run's ATTRIBUTION.txt (`notices`, a URL of ours) with the full notices. With
 *  `toggle`, a button (its `label`) before them that folds them on a phone (ui.css .u-credits; `open`:
 *  unfolded); the tile credits beside them stay in sight, as the OSM tile policy wants. */
export function creditsHtml(credits: Credit[], notices: string, toggle?: {label: string; open: boolean}): string {
  const parts = credits.map((c) => escape(c.attribution) + " (" + linked(c.licence, c.url) + ")");
  const html = "Data: " + Array.from(new Set(parts)).join(" | ") + ". " + escape(PROCESSED_NOTE) +
    ' <a href="' + escape(notices) + '" target="_blank">Notices</a>';
  if (!toggle) return html;
  return '<button type="button" class="u-credits-toggle" aria-expanded="' + toggle.open + '">' + escape(toggle.label) +
    '</button><span class="u-credits' + (toggle.open ? " u-open" : "") + '">' + html + "</span>";
}
