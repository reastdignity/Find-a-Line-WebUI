// The colours of the coverage map, one source for the page (set as CSS custom properties by `applyPalette`,
// through the CSSOM: the CSP allows no style attributes), the place map's layer and the canvas of the
// animations and images. Levels 1 and 2 were checked for colour-blind readers against `bg`, light and
// dark (the dataviz validator, 2026-11-02); the 30 m base stays neutral and is named in the legend.
import type { Level } from "./types";

export interface Theme {
  bg: string; surface: string; surface2: string; ink: string; ink2: string; muted: string; line: string;
  sea: string; land: string; l1: string; l2: string; edge: string; clear: string; lineMap: string;
  trees: string; tint: string;
}

export const THEMES: Record<"light" | "dark", Theme> = {
  light: {
    bg: "#f3f5f2", surface: "#ffffff", surface2: "#e9eee9", ink: "#17201c", ink2: "#45524b", muted: "#6c7a73",
    line: "#d2dad4", sea: "#e6edef", land: "#d3dbd5", l1: "#c40cba", l2: "#e98be3", edge: "#f7f9f7",
    clear: "#e10fd6", lineMap: "#ff10f0", trees: "#ff8c00", tint: "#e9eee9",
  },
  dark: {
    bg: "#0e1311", surface: "#161c19", surface2: "#1f2723", ink: "#e5ebe7", ink2: "#b1bcb6", muted: "#85928b",
    line: "#2c3631", sea: "#0b1114", land: "#26302a", l1: "#ff4cf4", l2: "#8f3489", edge: "#0e1311",
    clear: "#ff4cf4", lineMap: "#ff10f0", trees: "#ff9f30", tint: "#7d8c84",
  },
};

/** The fill of a level: 1 and 2 their colours, 3 the land. */
export const levelColour = (theme: Theme, level: Level): string => (level === 1 ? theme.l1 : level === 2 ? theme.l2 : theme.land);

/** The theme's colours as custom properties of `element` (--cov-<name>: --cov-l1, --cov-land, ...). */
export function applyPalette(element: HTMLElement, theme: Theme): void {
  for (const [name, value] of Object.entries(theme)) element.style.setProperty(`--cov-${name}`, value);
}
