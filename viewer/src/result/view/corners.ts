// The bottom corners of a result's Leaflet map (the attribution, which the OSM tile usage policy forbids
// hiding, and the scale) kept clear of what covers the map: on a phone above the sheet (with the sheet at
// full height the map is covered whole and they stay where they are); on a desktop above the floating
// profile card where it covers them.

import type { RefObject } from "preact";
import { useEffect } from "preact/hooks";

type Box = RefObject<HTMLElement | null> | (() => HTMLElement | null);
const element = (box: Box) => typeof box === "function" ? box() : box.current;

/** Raises the corners `bottom` px (0: Leaflet's own place), the scale above the attribution (on a phone it
 *  wraps over the whole width). */
function place(map: HTMLElement, bottom: number) {
  const attribution = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-right");
  const scale = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-left");
  if (attribution) attribution.style.bottom = bottom ? `${bottom}px` : "";
  const above = bottom ? bottom + (attribution?.offsetHeight ?? 0) : 0;
  if (scale) scale.style.bottom = above ? `${above}px` : "";
}

/** Keeps the corners of the map in `mapBox` above the `.u-sheet` in `root` while `on`. */
export function useCornersAboveSheet(root: Box, mapBox: Box, on: boolean) {
  useEffect(() => {
    const map = element(mapBox), sheet = element(root)?.querySelector<HTMLElement>(".u-sheet");
    if (!on || !map || !sheet) return;
    const update = () => {
      const rect = map.getBoundingClientRect(), covered = rect.bottom - sheet.getBoundingClientRect().top;
      place(map, covered > 0 && covered < rect.height - 120 ? Math.round(covered) : 0);
    };
    update();
    const observer = new ResizeObserver(update);  // the sheet's height animates: every frame of it
    observer.observe(sheet);
    observer.observe(map);
    // the attribution grows when its data credits unfold, and the scale above it moves up
    const attribution = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-right");
    if (attribution) observer.observe(attribution);
    return () => { observer.disconnect(); place(map, 0); };
  }, [on]);
}

const GAP = 8;  // px between the card's top and a corner raised above it

/** Keeps each bottom corner of the map in `mapBox` (the attribution, the scale) above the profile card
 *  (`.r-card`, ProfileCard) where the card covers it horizontally, in its own place elsewhere, while `on`.
 *  `cardBox` is the card or its positioned parent (the map's column, the card one of its children): the card
 *  comes and goes with the selection, and its size is followed as it is dragged or folded. */
export function useCornersAboveCard(mapBox: Box, cardBox: Box, on: boolean) {
  useEffect(() => {
    const map = element(mapBox), holder = element(cardBox);
    if (!on || !map || !holder) return;
    const attribution = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-right");
    const scale = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-left");
    let card: HTMLElement | null = null;
    const update = () => {
      const now = holder.matches(".r-card") ? holder : holder.querySelector<HTMLElement>(":scope > .r-card");
      if (now !== card) {
        if (card) sizes.unobserve(card);
        card = now;
        if (card) sizes.observe(card);
        // its size and place set by ProfileCard (style, folded): seen at once, also where no frame is drawn
        styles.disconnect();
        if (card) styles.observe(card, {attributes: true, attributeFilter: ["style", "class"]});
      }
      const rect = map.getBoundingClientRect(), box = card?.getBoundingClientRect();
      const up = box && box.height ? Math.max(0, Math.round(rect.bottom - box.top) + GAP) : 0;
      // Horizontally the corners do not move: their rectangles tell whether the card is under them
      const a = attribution?.getBoundingClientRect(), s = scale?.getBoundingClientRect();
      const covers = (r?: DOMRect) => !!(up && r && r.width && box!.left < r.right + GAP / 2 &&
                                         box!.right > r.left - GAP / 2);
      const attributionUp = covers(a), scaleUp = covers(s);
      if (attribution) {
        attribution.style.bottom = attributionUp ? `${up}px` : "";
        attribution.style.left = attribution.style.right = "";
      }
      // Both raised and side by side on one line: the scale goes above the attribution
      const stacked = attributionUp && scaleUp && a && s && a.left < s.right;
      if (scale) scale.style.bottom = scaleUp ? `${up + (stacked ? attribution!.offsetHeight : 0)}px` : "";
    };
    const sizes = new ResizeObserver(update), styles = new MutationObserver(update);
    sizes.observe(map);
    if (attribution) sizes.observe(attribution);  // its data credits unfold
    // The card is added and removed (a selection, the profile closed): a child of its parent
    const children = holder.matches(".r-card") ? null : new MutationObserver(update);
    children?.observe(holder, {childList: true});
    update();
    return () => { sizes.disconnect(); styles.disconnect(); children?.disconnect(); place(map, 0); };
  }, [on]);
}
