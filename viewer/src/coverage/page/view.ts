// What the three map views (flat, Leaflet, globe) share: the page's side of a view and the view's
// handle, so CoveragePage switches between them without knowing how each draws.
import type { Theme } from "../palette";
import type { BoxName, Geo } from "./geo";

export interface ViewContext {
  geo: Geo;
  theme(): Theme;              // the colours now (light or dark)
  selected(): string | null;   // the key of the area whose card is open
  select(key: string): void;   // a click on an area
  label(key: string): string;  // the tooltip of an area: its name and resolution
  credit(): string;            // the outlines' credit (Natural Earth), in the page's language
  reducedMotion(): boolean;
}

export interface MapView {
  zoomTo(box: BoxName): void;
  /** The theme, language or selection changed: draw again. */
  update(): void;
  destroy(): void;
}

export type ViewName = "flat" | "leaflet" | "globe";
export const VIEWS: ViewName[] = ["flat", "leaflet", "globe"];

/** Runs `step(p)` from 0 to 1 over `ms` milliseconds, eased (at once under reduced motion); the
 *  returned function stops it. */
export function tween(ms: number, reduced: boolean, step: (p: number) => void): () => void {
  if (reduced || ms <= 0) {
    step(1);
    return () => {};
  }
  const start = performance.now();
  let frame = 0;
  const run = (now: number) => {
    const x = Math.min(1, (now - start) / ms);
    step(x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    if (x < 1) frame = requestAnimationFrame(run);
  };
  frame = requestAnimationFrame(run);
  return () => cancelAnimationFrame(frame);
}
