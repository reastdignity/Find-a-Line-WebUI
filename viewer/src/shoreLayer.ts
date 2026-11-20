// The uncertain shore on a Leaflet map (shore.ts): the segments as an overlay of the layer control, and a
// small control (top left, under the run's title bar) with a legend of the two kinds, the metres of each in view and
// the kit's "info" icon opening a longer explanation, shown only while the view holds some; on a phone folded into a
// one-line chip.

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

let controls = 0;  // the ids of the boxes a chip controls

/** The total in view in the chip: from 1 km up in km with one decimal ("3.0 km"), below in metres ("820 m"). */
export function shoreTotal(m: number): string {
  return Math.round(m) >= 1000 ? t("ui.shore.km", {km: (m / 1000).toFixed(1)}) : t("ui.shore.m", {m: Math.round(m)});
}

/** The kit's "info" icon (ui/icons.tsx ICONS.info, drawn as its Icon draws it), copied: this file is also bundled
 *  without the loader of the logo's .svg files that icons.tsx imports (viewer/test/shore_page.ts in
 *  tests/test_viewer.py). tests/test_access_view.py holds the copy equal to the kit's. */
export const INFO_ICON = '<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true">' +
  '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>';

/** The help button of a box over the map (the shore's, the coarser terrain's): the kit's plain icon button with the
 *  "info" icon (as access.tsx's key in the result view: R9, no "?" character), `label` its name and its title. */
export function helpButton(parent: HTMLElement, label: string): HTMLButtonElement {
  const help = L.DomUtil.create("button", "u-ib u-plain u-shore-help", parent);
  help.type = "button";
  help.innerHTML = INFO_ICON;
  help.setAttribute("aria-label", label);
  help.title = label;
  help.setAttribute("aria-expanded", "false");
  return help;
}

/** A chevron for the fold buttons, down (unfold) or up (fold). */
function chevron(up: boolean): string {
  return `<svg class="u-shore-chev" viewBox="0 0 10 10" aria-hidden="true"><path d="${up ? "M2 6.5 5 3.5 8 6.5" : "M2 3.5 5 6.5 8 3.5"}"` +
    ` fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

/** The control of the uncertain shore in the map's view: a legend of the two kinds with the metres of each in
 *  view (updated on every move), and the info icon opening a longer explanation; hidden while the view holds none; at
 *  the top left of the map. On the phone layout (under 768 px, ui.css; ui/components.tsx `DESKTOP` is its
 *  opposite) it starts folded into a one-line chip (the swatches of the kinds in view, "Uncertain shore", the total
 *  in view, a chevron) that unfolds into the box; the box's title folds it again, and it stays as it is while the
 *  map moves. From 768 px up the box is always open, no chip and no fold button. On both the opened box keeps
 *  within the map (its text scrolls inside).
 *  `shoreControl(map, shore).remove()` takes it off. */
export function shoreControl(map: L.Map, shore: Shore, position: L.ControlPosition = "topleft"): L.Control {
  const boxes = shore.segments.map(segmentBox);
  const holder = L.DomUtil.create("div", "u-shore-ctl u-shore-folded");
  holder.setAttribute("role", "status");
  L.DomEvent.disableClickPropagation(holder);
  const id = `u-shore-box-${++controls}`;
  // The chip (phones, folded)
  const chip = L.DomUtil.create("button", "u-shore-chip", holder);
  chip.type = "button";
  chip.setAttribute("aria-expanded", "false");
  chip.setAttribute("aria-controls", id);
  const swatches = L.DomUtil.create("span", "u-shore-chip-sw", chip);
  swatches.setAttribute("aria-hidden", "true");
  const chipSwatch = {surface: L.DomUtil.create("span", "u-shore-swatch u-shore-surface", swatches),
                      sea: L.DomUtil.create("span", "u-shore-swatch u-shore-sea", swatches)};
  L.DomUtil.create("b", "", chip).textContent = t("ui.shore.chip");
  const chipTotal = L.DomUtil.create("span", "u-shore-chip-m", chip);
  chip.insertAdjacentHTML("beforeend", chevron(false));
  // Today's box: on a phone its title is the button that folds it
  const box = L.DomUtil.create("div", "u-shore", holder);
  box.id = id;
  const head = L.DomUtil.create("div", "u-shore-head", box);
  const title = L.DomUtil.create("b", "u-shore-title", head);
  title.textContent = t("ui.shore.title");
  const fold = L.DomUtil.create("button", "u-shore-fold", head);
  fold.type = "button";
  fold.setAttribute("aria-expanded", "true");
  fold.setAttribute("aria-controls", id);
  fold.setAttribute("aria-label", t("ui.shore.fold"));
  L.DomUtil.create("span", "", fold).textContent = t("ui.shore.title");
  fold.insertAdjacentHTML("beforeend", chevron(true));
  const help = helpButton(head, t("ui.shore.help_button"));
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
  // The opened box ends above the map's bottom corners (the scale and the credits; on a phone raised above the
  // sheet by result/view/corners.ts) or the map's bottom: a longer text scrolls inside it (ui.css). A phone's map
  // is short, and so is a desktop's in a low window (under about 560 px its "?" text ran under the credits).
  const fit = () => {
    box.style.maxHeight = "";
    if (holder.hidden || box.offsetParent === null) return;
    const area = map.getContainer().getBoundingClientRect(), top = box.getBoundingClientRect();
    let bottom = area.bottom;
    for (const corner of map.getContainer().querySelectorAll<HTMLElement>(".leaflet-bottom")) {
      const r = corner.getBoundingClientRect();
      if (r.height && r.left < top.right && r.right > top.left) bottom = Math.min(bottom, r.top);
    }
    box.style.maxHeight = `${Math.max(80, Math.floor(bottom - top.top - 8))}px`;
  };
  help.onclick = () => {
    more.hidden = !more.hidden;
    help.setAttribute("aria-expanded", String(!more.hidden));
    fit();
    // where the box scrolls (a phone), the opened text comes up under the box's title (sticky there, ui.css)
    if (!more.hidden && box.scrollHeight > box.clientHeight) {
      box.scrollTop += more.getBoundingClientRect().top - head.getBoundingClientRect().bottom - 2;
    }
  };
  const setFolded = (folded: boolean) => {
    holder.classList.toggle("u-shore-folded", folded);
    chip.setAttribute("aria-expanded", String(!folded));
    if (folded) {  // unfolded again it shows the box as at first, as the mock-up does
      more.hidden = true;
      help.setAttribute("aria-expanded", "false");
    }
    // the focus follows from a focused button (the keyboard; a tap on a phone mostly focuses none): no ring after a tap
    const focused = document.activeElement === chip || document.activeElement === fold;
    fit();
    if (focused) (folded ? chip : fold).focus({preventScroll: true});
  };
  chip.onclick = () => setFolded(false);
  fold.onclick = () => setFolded(true);
  const update = () => {
    const b = map.getBounds();
    const view: LatLngBox = {south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast()};
    const m = metresInView(shore, view, boxes);
    holder.hidden = m.surface + m.sea === 0;
    texts.surface.textContent = t("ui.shore.surface_m", {m: m.surface});
    texts.sea.textContent = t("ui.shore.sea_m", {m: m.sea});
    chipSwatch.surface.hidden = m.surface === 0;
    chipSwatch.sea.hidden = m.sea === 0;
    const total = shoreTotal(m.surface + m.sea);
    chipTotal.textContent = total;
    chip.setAttribute("aria-label", t("ui.shore.unfold", {total}));
    fit();
  };
  // The bottom corners move without a map event: result/view/corners.ts raises them above a phone's sheet or a
  // desktop's profile card (their style's bottom), and the credits unfold (their size). Watched while on the map.
  const corners = () => [...map.getContainer().querySelectorAll<HTMLElement>(".leaflet-bottom")];
  const placed = new MutationObserver(fit);
  const sized = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
  const Control = L.Control.extend({
    onAdd() {
      map.on("moveend zoomend resize", update);
      for (const corner of corners()) {
        placed.observe(corner, {attributes: true, attributeFilter: ["style"]});
        sized?.observe(corner);
      }
      update();
      return holder;
    },
    onRemove() {
      map.off("moveend zoomend resize", update);
      placed.disconnect();
      sized?.disconnect();
    },
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
