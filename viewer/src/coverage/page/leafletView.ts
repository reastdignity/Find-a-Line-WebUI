// The Leaflet view: the app's base layers (layers.ts, with their credits) under the areas, filled by level
// (the 30 m rest faint, so the tiles stay readable), partial areas with a dashed edge.
import "../../leaflet";
import L from "leaflet";
import { baseLayers } from "../../baselayers";
import { levelColour } from "../palette";
import { BOXES, keyOf, levelOfKey, partialOfKey } from "./geo";
import type { MapView, ViewContext } from "./view";

const MAX_ZOOM = 12;

export function mountLeaflet(el: HTMLElement, ctx: ViewContext): MapView {
  const box = document.createElement("div");
  box.className = "cov-leaflet";
  el.append(box);
  const map = L.map(box, {worldCopyJump: true, minZoom: 1, maxZoom: MAX_ZOOM, zoomSnap: 0.5}).setView([35, 10], 2);
  const layers = baseLayers(null, MAX_ZOOM);
  Object.values(layers)[0].addTo(map);
  L.control.layers(layers, {}, {position: "topright"}).addTo(map);

  const style = (key: string): L.PathOptions => {
    const theme = ctx.theme(), level = levelOfKey(key), partial = partialOfKey(key), chosen = ctx.selected() === key;
    return {
      fillColor: levelColour(theme, level), fillOpacity: level === 3 ? 0.12 : partial ? 0.4 : 0.65,
      color: chosen ? theme.ink : partial ? theme.l1 : level === 3 ? theme.muted : theme.edge,
      weight: chosen ? 2.5 : partial ? 1.4 : level === 3 ? 0.4 : 0.8,
      opacity: level === 3 && !chosen ? 0.5 : 1, dashArray: partial && !chosen ? "4 3" : undefined,
    };
  };
  let credit = ctx.credit();
  const areas = L.geoJSON(ctx.geo.features as any, {
    attribution: credit,
    style: f => style(keyOf(f as any)),
    onEachFeature: (f, layer) => {
      const key = keyOf(f as any);
      layer.on("click", () => ctx.select(key));
      layer.bindTooltip(() => ctx.label(key), {sticky: true});
    },
  }).addTo(map);
  const dots = ctx.geo.dots.map(dot => {
    const marker = L.circleMarker([dot.lonlat[1], dot.lonlat[0]], {radius: 5, weight: 1.5, fillOpacity: 1})
      .on("click", () => ctx.select(dot.key)).bindTooltip(() => ctx.label(dot.key)).addTo(map);
    return {dot, marker};
  });
  const paint = () => {
    const theme = ctx.theme();
    areas.setStyle(f => style(keyOf(f as any)));
    for (const {dot, marker} of dots) {
      marker.setStyle({fillColor: levelColour(theme, levelOfKey(dot.key)), color: ctx.selected() === dot.key ? theme.ink : theme.surface});
    }
  };
  paint();
  // the container may still be laid out when the view is made
  const sized = setTimeout(() => map.invalidateSize(), 50);
  const resize = new ResizeObserver(() => map.invalidateSize());
  resize.observe(box);

  return {
    zoomTo(name) {
      const [[w, s], [e, n]] = BOXES[name];
      map.flyToBounds([[s, Math.max(w, -180)], [n, Math.min(e, 180)]], {animate: !ctx.reducedMotion(), duration: 0.8});
    },
    update() {
      paint();
      const now = ctx.credit();
      if (now !== credit) {
        map.attributionControl.removeAttribution(credit).addAttribution(now);
        credit = now;
      }
    },
    destroy() { clearTimeout(sized); resize.disconnect(); map.remove(); el.replaceChildren(); },
  };
}
