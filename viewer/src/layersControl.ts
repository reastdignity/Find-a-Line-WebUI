// The maps' layers control (Leaflet's Layers with the kit's "layers" icon, rows redrawn with a hook, an opened box
// fitted above the map's credits): the place map's (app/PlaceMap.ts: the search page, the OSM page, the highline
// layer's map) and the result view's (result/view/SpotColumns.tsx). A module of its own so that the result view's
// bundles (map.html's viewer.js too) take it without PlaceMap.ts' Leaflet-Geoman; its look is mapbar.css's.

import L from "leaflet";
import { ICONS } from "./ui/icons";

/** The layers' control: opened at the map's top it never grows past the map's bottom edge (Leaflet leaves 50 px
 *  under it and counts the list before the box's padding): it scrolls inside, above the map's credits. After every
 *  redraw of its rows (Leaflet draws them again at each change) it calls `options.afterUpdate`: the coverage's row
 *  gets its link again (coverageLayer.ts). */
export const Layers = L.Control.Layers.extend({
  // the button with the kit's "layers" icon instead of Leaflet's grey picture (static markup: the CSP allows it;
  // mapbar.css takes the picture off)
  _initLayout(this: any) {
    (L.Control.Layers.prototype as any)._initLayout.call(this);
    this._layersLink.innerHTML = `<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS.layers}</svg>`;
  },
  _update(this: any) {
    const done = (L.Control.Layers.prototype as any)._update.call(this);
    if (this._container) this.options.afterUpdate?.();
    return done;
  },
  expand(this: any) {
    L.Control.Layers.prototype.expand.call(this);
    const section: HTMLElement = this._section;
    if (!String(this.options.position).startsWith("top")) return this;
    section.style.height = "";
    const container: HTMLElement = this._container;
    const around = container.offsetHeight - section.offsetHeight;  // the box's padding and edge
    // down to 4 px above the map's credits (a phone's take one or two lines at the map's bottom), 8 px above its edge
    const credits = (this._map.getContainer() as HTMLElement).querySelector<HTMLElement>(".leaflet-control-attribution");
    const room = this._map.getSize().y - container.offsetTop - around - Math.max(8, 4 + (credits?.offsetHeight ?? 0));
    const scrolls = section.scrollHeight > room;
    section.classList.toggle("leaflet-control-layers-scrollbar", scrolls);
    if (scrolls) {
      // the list ends in the middle of a row, never between two: the cut row says there is more to scroll to
      const row = section.querySelector<HTMLElement>("label")?.offsetHeight || 44;
      let height = Math.max(room, row);
      const over = height % row;
      if (over < row / 4 || over > row * 3 / 4) height = (Math.round(height / row) - 0.5) * row;
      section.style.height = `${Math.max(height, row)}px`;
    }
    return this;
  },
}) as unknown as new (base: L.Control.LayersObject, overlays: L.Control.LayersObject, options: L.Control.LayersOptions) => L.Control.Layers;
