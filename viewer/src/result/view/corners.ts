// The bottom corners of a result's Leaflet map (the attribution, which the OSM tile usage policy forbids
// hiding, and the scale) kept clear of what covers the map: on a phone above the sheet (with the sheet at
// full height the map is covered whole and they stay where they are); on a desktop (D/B's workspace) left
// of the results panel and above the profile dock, the attribution wrapping in between.

import type { RefObject } from "preact";
import { useEffect } from "preact/hooks";

type Box = RefObject<HTMLElement | null> | (() => HTMLElement | null);
const element = (box: Box) => typeof box === "function" ? box() : box.current;
const SCALE = 110;  // px at the left kept for the scale (Leaflet's control is at most 100 px wide)

/** Offsets of the corners (px; 0: Leaflet's own place): `right` gives the attribution's corner a width of its
 *  own beside the scale, so a long attribution wraps there; without it the scale goes above the attribution
 *  (on a phone it wraps over the whole width). */
function place(map: HTMLElement, bottom: number, right = 0) {
  const attribution = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-right");
  const scale = map.querySelector<HTMLElement>(".leaflet-bottom.leaflet-left");
  if (attribution) {
    attribution.style.bottom = bottom ? `${bottom}px` : "";
    attribution.style.right = right ? `${right}px` : "";
    attribution.style.left = right ? `${SCALE}px` : "";
  }
  const above = bottom && !right ? bottom + (attribution?.offsetHeight ?? 0) : bottom;
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
    return () => { observer.disconnect(); place(map, 0); };
  }, [on]);
}

/** Keeps the corners of the map in `mapBox` left of a panel `right` px wide (with its margin) and above the
 *  `.r-dock` in `dock` (the profile; its wrapper ends `gap` px above the map's bottom) while `on`. */
export function useCornersBesidePanel(mapBox: Box, dock: Box, right: number, gap: number, on: boolean) {
  useEffect(() => {
    const map = element(mapBox), wrapper = element(dock);
    if (!on || !map || !wrapper) return;
    const update = () => {
      const height = wrapper.querySelector<HTMLElement>(".r-dock")?.offsetHeight ?? 0;
      place(map, height ? height + gap + 4 : 0, right);
    };
    update();
    const observer = new ResizeObserver(update);  // the wrapper grows when the profile opens
    observer.observe(wrapper);
    return () => { observer.disconnect(); place(map, 0); };
  }, [on]);
}
