// The uncertain shore on a Leaflet map (shore.ts): the segments as an overlay of the layer control, and a
// small control (top left, under the run's title bar) with a legend of the two kinds, the metres of each in view and a
// "?" with a longer explanation, shown only while the view holds some.

import L from "leaflet";
import { t } from "./i18n";
import { hasShore, metresInView, segmentBox, SHORE_COLOURS, type LatLngBox } from "./shore";
import type { Shore, ShoreKind } from "./types";

/** The style of a segment on the map: the surface model's face dashed, the sea's fill solid. */
export function shoreStyle(kind: ShoreKind, renderer?: L.Renderer): L.PathOptions {
  return {color: SHORE_COLOURS[kind], weight: 2, opacity: 0.9, fillColor: SHORE_COLOURS[kind], fillOpacity: 0.3,
          dashArray: kind === "surface" ? "4 3" : undefined, interactive: false, renderer};
}

/** The overlay of a run's shore: a polygon per segment on a renderer of its own (an SVG pane that leaves the map
 *  with the group, so a result's canvas and its clicks are not touched). */
export function shoreLayer(shore: Shore, renderer: L.Renderer = L.svg({padding: 0.5})): L.LayerGroup {
  const group = L.layerGroup([renderer]);
  for (const s of shore.segments) {
    L.polygon(s.ring.map(([lon, lat]) => [lat, lon] as [number, number]), shoreStyle(s.kind, renderer)).addTo(group);
  }
  return group;
}

/** The control of the uncertain shore in the map's view: a legend of the two kinds with the metres of each in
 *  view (updated on every move), and a "?" opening a longer explanation; hidden while the view holds none; at
 *  the top left of the map. `shoreControl(map, shore).remove()` takes it off. */
export function shoreControl(map: L.Map, shore: Shore, position: L.ControlPosition = "topleft"): L.Control {
  const boxes = shore.segments.map(segmentBox);
  const box = L.DomUtil.create("div", "u-shore");
  box.setAttribute("role", "status");
  L.DomEvent.disableClickPropagation(box);
  const head = L.DomUtil.create("div", "u-shore-head", box);
  const title = L.DomUtil.create("b", "", head);
  title.textContent = t("ui.shore.title");
  const help = L.DomUtil.create("button", "u-hint u-shore-help", head);
  help.type = "button";
  help.textContent = "?";
  help.setAttribute("aria-label", t("ui.shore.help_button"));
  help.setAttribute("aria-expanded", "false");
  const rows: Record<ShoreKind, HTMLElement> = {surface: L.DomUtil.create("div", "u-shore-row", box),
                                                 sea: L.DomUtil.create("div", "u-shore-row", box)};
  const texts: Record<ShoreKind, HTMLElement> = {} as Record<ShoreKind, HTMLElement>;
  for (const kind of ["surface", "sea"] as const) {
    L.DomUtil.create("span", `u-shore-swatch u-shore-${kind}`, rows[kind]).setAttribute("aria-hidden", "true");
    texts[kind] = L.DomUtil.create("span", "", rows[kind]);
  }
  const more = L.DomUtil.create("p", "u-shore-more", box);
  more.textContent = t("ui.shore.help");
  more.hidden = true;
  help.onclick = () => {
    more.hidden = !more.hidden;
    help.setAttribute("aria-expanded", String(!more.hidden));
  };
  const update = () => {
    const b = map.getBounds();
    const view: LatLngBox = {south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast()};
    const m = metresInView(shore, view, boxes);
    box.hidden = m.surface + m.sea === 0;
    texts.surface.textContent = t("ui.shore.surface_m", {m: m.surface});
    texts.sea.textContent = t("ui.shore.sea_m", {m: m.sea});
  };
  const Control = L.Control.extend({
    onAdd() { map.on("moveend zoomend resize", update); update(); return box; },
    onRemove() { map.off("moveend zoomend resize", update); },
  });
  return new Control({position}).addTo(map);
}

/** Both on a map, when the run has a shore: the overlay (on, in `overlays` for the layer control under its name)
 *  and the control. */
export function addShore(map: L.Map, shore: Shore | null | undefined, overlays: Record<string, L.Layer>): L.Control | null {
  if (!hasShore(shore)) return null;
  overlays[t("ui.shore.layer")] = shoreLayer(shore).addTo(map);
  return shoreControl(map, shore);
}
