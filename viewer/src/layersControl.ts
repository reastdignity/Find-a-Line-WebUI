// The maps' layers control (Leaflet's Layers with the kit's "layers" icon, rows redrawn with a hook, an opened box
// fitted above the map's credits): the place map's (app/PlaceMap.ts: the search page, the OSM page, the highline
// layer's map) and the result view's (result/view/SpotColumns.tsx). A module of its own so that the result view's
// bundles (map.html's viewer.js too) take it without PlaceMap.ts' Leaflet-Geoman; its look is mapbar.css's.

import L from "leaflet";
import { ICONS } from "./ui/icons";

/** How long after the box opens a press inside it is not taken (ms): a second tap at the button's place (a double
 *  tap is under 300 ms; the box's rows of 44 px appear under the finger at once). */
export const OPEN_GUARD_MS = 400;

let keyUnmarks = false;  // the page's one listener of keys added
/** The map's own keyboard ring only after a key (step 3d G6, A7): Leaflet focuses its box on every press, and the
 *  browsers then mark that focus :focus-visible, so a press marks the box (`u-map-pressed`, mapbar.css draws no ring
 *  then) until the next key anywhere on the page. Both maps take it with their layers control (one place). The key's
 *  listener is one for the page, whatever the maps made and removed (Leaflet's map.remove() does not call a control's
 *  onRemove, so a listener per map would stay with its removed box: the code review's finding 4). */
export function pressMarks(box: HTMLElement) {
  box.addEventListener("pointerdown", () => box.classList.add("u-map-pressed"), true);
  if (keyUnmarks) return;
  keyUnmarks = true;
  document.addEventListener("keydown", () => {
    for (const marked of document.querySelectorAll(".u-map-pressed")) marked.classList.remove("u-map-pressed");
  }, true);
}

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
    // The keyboard as a disclosure (WAI-ARIA; step 3d G6, A6): Enter or Space on the button opens the box with the
    // focus on its chosen row (the button is hidden while the box is open: the focus fell to the page); Escape closes
    // it with the focus back on the button (a press on the map closes it, as Leaflet's)
    const link: HTMLElement = this._layersLink, container: HTMLElement = this._container;
    link.setAttribute("aria-expanded", "false");
    L.DomEvent.on(link, "keydown", (e: Event) => {
      const key = (e as KeyboardEvent).key;
      if (key !== "Enter" && key !== " ") return;
      L.DomEvent.preventDefault(e);
      this._expandSafely();
      const rows = [...container.querySelectorAll<HTMLInputElement>(".leaflet-control-layers-selector")];
      (rows.find((input) => input.checked) ?? rows[0])?.focus();
    });
    L.DomEvent.on(container, "keydown", (e: Event) => {
      if ((e as KeyboardEvent).key !== "Escape" || !container.classList.contains("leaflet-control-layers-expanded")) return;
      L.DomEvent.stop(e);
      this.collapse();
      link.focus();
    });
    container.addEventListener("pointerdown", (e: PointerEvent) => { this._byTouch = e.pointerType !== "mouse"; }, true);
  },
  onAdd(this: any, map: L.Map) {
    const container = (L.Control.Layers.prototype as any).onAdd.call(this, map);
    pressMarks(map.getContainer());
    return container;
  },
  _update(this: any) {
    const done = (L.Control.Layers.prototype as any)._update.call(this);
    if (this._container) {
      // the rows' boxes the kit's (ui.css .u-check and its round twin .u-radio: step 3d G6, Q4 a)
      for (const input of this._container.querySelectorAll(".leaflet-control-layers-selector")) {
        input.classList.add(input.type === "radio" ? "u-radio" : "u-check");
      }
      this.options.afterUpdate?.();
    }
    return done;
  },
  collapse(this: any) {
    L.Control.Layers.prototype.collapse.call(this);
    this._layersLink?.setAttribute("aria-expanded", "false");
    return this;
  },
  /** Opened by a tap or the mouse: as Leaflet's, but a press inside the box is not taken for a while (a second tap
   *  where the button stood lands on the row now under the finger: it switched the base map; step 3d G6, A6). */
  _expandSafely(this: any) {
    const section: HTMLElement = this._section;
    this._preventClick = true;
    L.DomEvent.on(section, "click", L.DomEvent.preventDefault);
    this.expand();
    clearTimeout(this._guard);
    this._guard = setTimeout(() => {
      L.DomEvent.off(section, "click", L.DomEvent.preventDefault);
      this._preventClick = false;
    }, this._byTouch ? OPEN_GUARD_MS : 0);  // a mouse: Leaflet's one turn
  },
  expand(this: any) {
    L.Control.Layers.prototype.expand.call(this);
    this._layersLink?.setAttribute("aria-expanded", "true");
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
