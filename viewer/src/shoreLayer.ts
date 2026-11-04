// The uncertain shore on a Leaflet map (shore.ts): the segments as an overlay of the layer control, and a
// small control (top left, under the run's title bar) naming the metres of it in view, shown only while the view holds some.

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

/** The control naming the metres of uncertain shore in the map's view, updated on every move; hidden when the
 *  view holds none; at the top left under the run's title bar (workspace.css moves the corner down).
 *  `shoreControl(map, shore).remove()` takes it off. */
export function shoreControl(map: L.Map, shore: Shore, position: L.ControlPosition = "topleft"): L.Control {
  const boxes = shore.segments.map(segmentBox);
  const box = L.DomUtil.create("div", "u-shore");
  box.setAttribute("role", "status");
  box.title = t("ui.shore.help");
  const update = () => {
    const b = map.getBounds();
    const view: LatLngBox = {south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast()};
    const m = metresInView(shore, view, boxes);
    const total = m.surface + m.sea;
    box.hidden = total === 0;
    if (total) box.textContent = t("ui.shore.in_view", {surface: m.surface, sea: m.sea});
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
