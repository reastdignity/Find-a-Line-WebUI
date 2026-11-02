// Background layers: OpenTopoMap, OpenStreetMap, Esri World Imagery (only with the operator's key of
// ArcGIS Location Platform, from the server: esriKey) and the orthophoto of the data source (from the
// local tile cache when there, else its WMS over its base tiles, if any, or the base tiles alone).

import L from "leaflet";
import type { Credit, Ortho } from "./types";

// The OSM tile usage policy and attribution guidelines: "© OpenStreetMap contributors" linked to the
// copyright page, and the link where map errors are reported (FOSSGIS's terms ask for fixthemap)
const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> ' +
  'contributors (<a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noopener">report a map issue</a>)';

/** A tile that tries the cached one ({cache}/{z}/{x}/{y}.jpg) first, then the service. */
function createCachedTile(this: L.TileLayer & {_cache: string | null}, coords: L.Coords, done: L.DoneCallback) {
  const layer = this as any, cache = this._cache;
  let online = !cache;
  const tile = document.createElement("img");
  tile.alt = "";
  tile.setAttribute("role", "presentation");
  L.DomEvent.on(tile, "load", L.Util.bind(layer._tileOnLoad, layer, done, tile));
  L.DomEvent.on(tile, "error", (e) => {
    if (!online) { online = true; tile.src = this.getTileUrl(coords); }
    else layer._tileOnError(done, tile, e);
  });
  tile.src = online ? this.getTileUrl(coords) : cache + "/" + coords.z + "/" + coords.x + "/" + coords.y + ".jpg";
  return tile;
}

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

const CachedWMS = L.TileLayer.WMS.extend({createTile: createCachedTile});
const CachedTiles = L.TileLayer.extend({createTile: createCachedTile});

export function baseLayers(ortho: Ortho | null, maxZoom: number): Record<string, L.Layer> {
  const layers: Record<string, L.Layer> = {
    "OpenTopoMap": L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom, maxNativeZoom: 17,
      attribution: "Map data: " + OSM + ', <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: ' +
        '&copy; <a href="https://opentopomap.org">OpenTopoMap</a> ' +
        '(<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'}),
    "OpenStreetMap": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom, maxNativeZoom: 19, attribution: OSM}),
  };
  const key = esriKey();
  if (key) {
    // Native tiles to z19 nearly everywhere (z20/21 only in places): enlarged above it
    layers[ESRI_NAME] = L.tileLayer(
      "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=" +
      encodeURIComponent(key),
      {maxZoom, maxNativeZoom: 19, attribution: linked("Powered by Esri", "https://www.esri.com") + " | " + escape(ESRI_SOURCE)});
  }
  if (ortho && !ortho.url && ortho.base) {
    // Tiles in the map's own tiling, no WMS (SWISSIMAGE)
    const layer = new (CachedTiles as any)(ortho.base.url, {
      maxZoom, maxNativeZoom: ortho.base.max_zoom, attribution: orthoHtml(ortho)}) as L.TileLayer;
    (layer as any)._cache = ortho.cache;
    layers[ortho.name] = layer;
  } else if (ortho && ortho.url) {
    // National WMS (e.g. geoportal) may not support Web Mercator, so tiles are requested
    // in WGS84. WMS renders at any scale, so the orthophoto stays sharp up to maxZoom.
    const base = ortho.base;
    const layer = new (CachedWMS as any)(ortho.url, {
      layers: ortho.layer, format: base ? "image/png" : "image/jpeg", version: "1.3.0", transparent: !!base,
      attribution: orthoHtml(ortho), maxZoom, crs: L.CRS.EPSG4326}) as L.TileLayer.WMS;
    (layer as any)._cache = ortho.cache;
    // Where the WMS has no imagery its PNG is transparent and shows the base under it
    // (cached tiles have both already and cover the base)
    layers[ortho.name] = base ? L.layerGroup([L.tileLayer(base.url, {maxZoom, maxNativeZoom: base.max_zoom}), layer])
      : layer;
  }
  return layers;
}

function escape(text: string): string {
  return text.replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
}

/** Plain text as HTML, a link when `url` is http(s) (Leaflet's attribution control renders HTML). */
function linked(text: string, url: string | null | undefined): string {
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
 *  unfolded); the tile credits beside them stay in sight, as the OSM tile policy wants. An empty `notices`
 *  leaves the link out (the highline layer of the local app: no page with the notices). */
export function creditsHtml(credits: Credit[], notices: string, toggle?: {label: string; open: boolean}): string {
  const parts = credits.map((c) => escape(c.attribution) + " (" + linked(c.licence, c.url) + ")");
  const html = "Data: " + Array.from(new Set(parts)).join(" | ") + ". " + escape(PROCESSED_NOTE) +
    (notices ? ' <a href="' + escape(notices) + '" target="_blank">Notices</a>' : "");
  if (!toggle) return html;
  return '<button type="button" class="u-credits-toggle" aria-expanded="' + toggle.open + '">' + escape(toggle.label) +
    '</button><span class="u-credits' + (toggle.open ? " u-open" : "") + '">' + html + "</span>";
}
