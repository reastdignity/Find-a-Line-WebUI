// The coarser terrain on a Leaflet map (coarser.ts): the regions a fallback filled as a hatched overlay of the layer
// control, and a small control (top left, under the uncertain shore's) with each fallback's km² in view and a "?"
// with a longer explanation, shown only while the view holds some. As shoreLayer.ts, whose box styles it shares.

import L from "leaflet";
import { t } from "./i18n";
import { fallbacks, hasCoarser, km2InView, km2Text, regionBox, regionsBox } from "./coarser";
import type { LatLngBox } from "./shore";
import type { TerrainSources } from "./types";

/** The outline's colour for Leaflet's attribute; CSS (.u-coarse-area, the token --coarse) gives each theme its own. */
const COARSER_COLOUR = "#3b3f5c";
const SVG_NS = "http://www.w3.org/2000/svg";
let patterns = 0;

/** A diagonal hatch as a pattern in the renderer's SVG (its id returned); the line's stroke comes from CSS. */
function addHatch(renderer: L.SVG): string {
  const id = `fal-coarse-hatch-${++patterns}`;
  renderer.once("add", () => {
    const svg = (renderer as unknown as {_container: SVGSVGElement})._container;
    const defs = document.createElementNS(SVG_NS, "defs");
    const pattern = document.createElementNS(SVG_NS, "pattern");
    pattern.setAttribute("id", id);
    pattern.setAttribute("width", "7");
    pattern.setAttribute("height", "7");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    pattern.setAttribute("patternTransform", "rotate(45)");
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", "0");
    line.setAttribute("y1", "0");
    line.setAttribute("x2", "0");
    line.setAttribute("y2", "7");
    line.setAttribute("class", "u-coarse-hatch");
    pattern.appendChild(line);
    defs.appendChild(pattern);
    svg.insertBefore(defs, svg.firstChild);
  });
  return id;
}

/** The overlay of a run's coarser regions: each a polygon with its holes, hatched, its outline dashed for the first
 *  fallback and solid for a later one (Alaska's 1/3″ DEM after its IfSAR), on a renderer of its own (an SVG pane
 *  that leaves the map with the group, so a result's canvas and its clicks are not touched). */
export function coarserLayer(sources: TerrainSources, renderer: L.SVG = L.svg({padding: 0.5})): L.LayerGroup {
  const group = L.layerGroup([renderer]);
  const hatch = addHatch(renderer);
  const first = fallbacks(sources)[0];
  for (const r of sources.regions) {
    const later = sources.layers[r.layer] !== first;
    L.polygon(r.rings.map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number])), {
      color: COARSER_COLOUR, weight: 1.5, opacity: 0.9, dashArray: later ? undefined : "6 4",
      fillColor: `url(#${hatch})`, fillOpacity: 1, interactive: false, renderer,
      className: later ? "u-coarse-area u-coarse-later" : "u-coarse-area"}).addTo(group);
  }
  return group;
}

/** The control of the coarser terrain in the map's view: a row per fallback with its resolution, its name and the km²
 *  of its regions in view (updated on every move), and a "?" opening a longer explanation; hidden while the view
 *  holds none (or the overlay is off); at the top left of the map. `coarserControl(map, sources).remove()` takes it
 *  off. */
export function coarserControl(map: L.Map, sources: TerrainSources, overlay?: L.Layer,
                               position: L.ControlPosition = "topleft"): L.Control {
  const boxes = sources.regions.map(regionBox);
  const box = L.DomUtil.create("div", "u-shore u-coarse");
  box.setAttribute("role", "status");
  L.DomEvent.disableClickPropagation(box);
  const head = L.DomUtil.create("div", "u-shore-head", box);
  L.DomUtil.create("b", "", head).textContent = t("ui.coarse.title");
  const help = L.DomUtil.create("button", "u-hint u-shore-help", head);
  help.type = "button";
  help.textContent = "?";
  help.setAttribute("aria-label", t("ui.coarse.help_button"));
  help.setAttribute("aria-expanded", "false");
  const first = fallbacks(sources)[0];
  const rows = sources.layers.map((layer) => {
    if (layer.role !== "fallback") return null;
    const row = L.DomUtil.create("div", "u-shore-row", box);
    L.DomUtil.create("span", layer === first ? "u-coarse-swatch" : "u-coarse-swatch u-coarse-later", row)
      .setAttribute("aria-hidden", "true");
    return {row, text: L.DomUtil.create("span", "", row)};
  });
  const more = L.DomUtil.create("p", "u-shore-more", box);
  more.textContent = t("ui.coarse.help");
  more.hidden = true;
  help.onclick = () => {
    more.hidden = !more.hidden;
    help.setAttribute("aria-expanded", String(!more.hidden));
  };
  const update = () => {
    const b = map.getBounds();
    const view: LatLngBox = {south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast()};
    const km2 = km2InView(sources, view, boxes);
    let any = false;
    sources.layers.forEach((layer, k) => {
      const r = rows[k];
      if (!r) return;
      r.row.hidden = km2[k] === 0;
      any ||= km2[k] > 0;
      r.text.textContent = t("ui.coarse.km2", {km2: km2Text(km2[k]), res: layer.resolution ?? "?", name: layer.name});
    });
    box.hidden = !any || (!!overlay && !map.hasLayer(overlay));
  };
  const Control = L.Control.extend({
    onAdd() { map.on("moveend zoomend resize layeradd layerremove", update); update(); return box; },
    onRemove() { map.off("moveend zoomend resize layeradd layerremove", update); },
  });
  return new Control({position}).addTo(map);
}

/** Both on a map, when the run has coarser regions: the overlay (on, in `overlays` for the layer control under its
 *  name), the control, and `fit` that shows every region (the result head's "Show on map"). */
export function addCoarser(map: L.Map, sources: TerrainSources | null | undefined,
                           overlays: Record<string, L.Layer>): {control: L.Control; fit: () => void} | null {
  if (!hasCoarser(sources)) return null;
  const overlay = coarserLayer(sources).addTo(map);
  overlays[t("ui.coarse.layer")] = overlay;
  const control = coarserControl(map, sources, overlay);
  const all = regionsBox(sources)!;
  const fit = () => {
    if (!map.hasLayer(overlay)) overlay.addTo(map);
    map.fitBounds([[all.south, all.west], [all.north, all.east]], {maxZoom: 17, padding: [24, 24]});
  };
  return {control, fit};
}
