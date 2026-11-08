// The cells of the highline layer on the map (LayerPage.tsx): the rows of every cube in view as polygons on one
// canvas (SafeCanvas: safe on removal), coloured by their density per km² in five log classes, the picked one
// outlined. The cells are lon/lat rectangles of the global lattice (30″ and its levels); a row's part of its cell
// is drawn and divides its count (the server's `cut`): a side-0 row (the country's own lines) over its cell's part
// inside the country, a partner row (side 1-7: lines across the border whose western end lies beyond it, counted
// from this country's data) over its part beyond the border, hatched; so neighbours' cells meet at their border. At
// low zoom the countries' outlines instead, coloured by their total over their area. The classes: the fixed breaks
// (CLASS_BREAKS, a colour means the same everywhere) or breaks fitted to the view (layerState.ts quantileBreaks),
// eased from the old to the new ones by `recolour` frame by frame.

import L from "leaflet";
import type { GeoJSON } from "geojson";
import type { CountryCells } from "../api";
import { SafeCanvas } from "../../result/ResultMap";
import { rectKm2 } from "./layerState";

export type LayerMode = "lines" | "spots";

/** The density classes per km² (lines; spots), on a log scale: a cell of density d is in class k when
 *  d >= breaks[k-1] (k = 0 below the first). Five classes: the tokens --layer-1 … --layer-5 (ui/tokens.css,
 *  checked with the dataviz skill's validator: one hue, light to dark, in both themes). The fixed scale, so a
 *  colour keeps its meaning across regions (the report: 1 to 23 million lines and 0.1 to 40 000 spots per km²). */
export const CLASS_BREAKS: Record<LayerMode, number[]> = {lines: [10, 300, 1e4, 3e5], spots: [1, 10, 100, 1000]};
export const CLASSES = 5;

/** The class (0 … 4) of a density per km² under the given breaks. */
export function densityClass(density: number, breaks: number[]): number {
  let k = 0;
  for (const b of breaks) if (density >= b) k++;
  return Math.min(CLASSES - 1, k);
}

/** 300000 → "300 k", 12 → "12", 0.5 → "0.5". */
export function short(n: number): string {
  if (n >= 1e9) return `${+(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} G`;
  if (n >= 1e6) return `${+(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M`;
  if (n >= 1e4) return `${+(n / 1e3).toFixed(0)} k`;
  if (n >= 100) return String(Math.round(n));
  return String(+n.toFixed(n >= 10 ? 0 : n >= 1 ? 1 : 2));
}

/** A density per km² as the selected cell's card and a cell's tooltip write it: short's digits without its
 *  abbreviations, with the thousands separator of the page's counts (`toLocaleString("en")`): 0.5 → "0.5",
 *  9135 → "9,135", 300000 → "300,000". */
export function densityText(n: number): string {
  return n.toLocaleString("en", {maximumFractionDigits: n >= 10 ? 0 : n >= 1 ? 1 : 2});
}

/** The class colours of the theme in force, from the tokens on `element`'s .ui root. */
export function classColours(element: HTMLElement): string[] {
  const style = getComputedStyle(element);
  return Array.from({length: CLASSES}, (_, k) => style.getPropertyValue(`--layer-${k + 1}`).trim() || "#2a78d6");
}

/** [lat, lon] × 4 of a row's corners (SW, SE, NE, NW). */
export function corners(flat: number[]): L.LatLngTuple[] {
  return [0, 2, 4, 6].map((k) => [flat[k], flat[k + 1]] as L.LatLngTuple);
}

/** The bounds of a row's corners. */
export function rowBounds(row: number[]): L.LatLngBounds {
  return L.latLngBounds(corners(row.slice(3, 11)));
}

/** A row's side: 0 the country's own lines, 1-7 the partner index of its partner lines (rows before cube v2: 0). */
export const rowSide = (row: number[]): number => row.length > 11 ? row[11] : 0;

/** The key of a row's part in the answer's `cut`. */
export const cutKey = (row: number[]): string => rowSide(row) ? `${row[0]},${row[1]},out` : `${row[0]},${row[1]}`;

/** The latlngs of a polygon on the map: a cell's corners, or the polygons of a row's part of it. */
export type CellShape = L.LatLngExpression[] | L.LatLngExpression[][][];

/** The km² of a whole cell of a row (its lon/lat rectangle on the ellipsoid). */
export function wholeKm2(row: number[]): number {
  return rectKm2(row[3], row[7], row[4], row[6]);
}

/** The km² of a row's part of its cell: the divisor of its density. */
export function cellKm2(data: CountryCells, row: number[]): number {
  return data.cut[cutKey(row)]?.km2 ?? wholeKm2(row);
}

/** What is drawn of a row's cell: its part (inside the country, or beyond it for a partner row). */
export function cellShape(data: CountryCells, row: number[]): CellShape {
  const cut = data.cut[cutKey(row)];
  return cut ? cut.shape as L.LatLngExpression[][][] : corners(row.slice(3, 11));
}

/** The cells of one cube, as the server answered them. */
export interface DrawnCells { country: string; data: CountryCells }
/** A row the user picked: its cube, level, cell side in degrees, position and side, its count and corners, the km² and
 *  shape of its part. */
export interface PickedCell { country: string; level: number; deg: number; i: number; j: number; side: number; count: number;
                              corners: number[]; km2: number; whole: number; shape: CellShape }
/** A country's outline at low zoom with its total under the filters. */
export interface OutlineShape { country: string; name: string; total: number; area_km2: number; geometry: GeoJSON }

interface Drawn { polygon: L.Polygon; density: number; cls: number }

/** The hatching of the partner rows: thin diagonal lines in the ink's colour on a transparent tile (a canvas pattern
 *  given to Leaflet's canvas as a fill: it sets fillStyle to whatever the option holds). */
function hatchPattern(element: HTMLElement): CanvasPattern | string {
  const ink = getComputedStyle(element).getPropertyValue("--ink").trim() || "#17201c";
  const tile = document.createElement("canvas");
  tile.width = tile.height = 6;
  const ctx = tile.getContext("2d");
  if (!ctx) return "transparent";
  ctx.strokeStyle = ink;
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  for (const k of [-6, 0, 6]) { ctx.moveTo(k, 6); ctx.lineTo(k + 6, 0); }
  ctx.stroke();
  return ctx.createPattern(tile, "repeat") || "transparent";
}

/** The cells on the map: polygons on their own canvas (safe on removal), the picked one outlined. */
export class CellsLayer {
  private readonly renderer = new SafeCanvas({padding: 0.5});
  private readonly group = L.layerGroup();
  private readonly top = L.layerGroup();
  private drawn: Drawn[] = [];
  private colours: string[] = [];
  private picked: PickedCell | null = null;

  /** `onPick(country, row)`: a cell clicked; `onOutline(country)`: an outline clicked (the page zooms to it);
   *  `tooltip(count, density, side)`: a cell's hover text. */
  constructor(private readonly map: L.Map, private readonly onPick: (country: string, row: number[]) => void,
              private readonly onOutline: (country: string) => void,
              private readonly tooltip: (count: number, density: number, side: number) => string) {
    this.group.addTo(map);
    this.top.addTo(map);
  }

  /** The rows of the cubes (`cells`), or the outlines at low zoom (`outlines`, coloured by `outlineBreaks`), the rows
   *  by `breaks`; the partner rows hatched over their colour. */
  draw(cells: DrawnCells[], outlines: OutlineShape[], breaks: number[], outlineBreaks: number[]) {
    this.group.clearLayers();
    this.drawn = [];
    const container = this.map.getContainer();
    this.colours = classColours(container);
    let hatch: CanvasPattern | string | null = null;
    for (const {country, data} of cells) {
      for (const row of data.cells) {
        const density = row[2] / cellKm2(data, row);
        const cls = densityClass(density, breaks);
        const colour = this.colours[cls];
        const shape = cellShape(data, row);
        const polygon = L.polygon(shape, {renderer: this.renderer, color: colour, weight: 0.6, opacity: 0.9,
                                          fillColor: colour, fillOpacity: 0.62});
        polygon.bindTooltip(this.tooltip(row[2], density, rowSide(row)), {sticky: true});
        polygon.on("click", (e: L.LeafletMouseEvent) => { L.DomEvent.stopPropagation(e as any); this.onPick(country, row); });
        this.group.addLayer(polygon);
        this.drawn.push({polygon, density, cls});
        if (rowSide(row)) {
          hatch ??= hatchPattern(container);
          this.group.addLayer(L.polygon(shape, {renderer: this.renderer, interactive: false, stroke: false,
                                                fillColor: hatch as unknown as string, fillOpacity: 0.5}));
        }
      }
    }
    for (const shape of outlines) {
      const density = shape.area_km2 > 0 ? shape.total / shape.area_km2 : 0;
      const colour = this.colours[densityClass(density, outlineBreaks)];
      const layer = L.geoJSON(shape.geometry, {renderer: this.renderer, style: {color: colour, weight: 1.2, opacity: 0.9,
                                                                                fillColor: colour, fillOpacity: 0.5}} as L.GeoJSONOptions);
      layer.bindTooltip(this.tooltip(shape.total, density, 0), {sticky: true});
      layer.on("click", (e: L.LeafletMouseEvent) => { L.DomEvent.stopPropagation(e as any); this.onOutline(shape.country); });
      this.group.addLayer(layer);
      const label = L.tooltip({permanent: true, direction: "center", interactive: false, className: "c-layer-outline-label"})
        .setLatLng(layer.getBounds().getCenter()).setContent(`${shape.name}: ${short(shape.total)}`);
      this.group.addLayer(label);
    }
    this.pick(this.picked);  // a canvas draws in the order added: the outline of the picked cell over the new cells
  }

  /** The picked row outlined on top of the cells (null: none), apart from them: picking redraws no cell. */
  pick(picked: PickedCell | null) {
    this.picked = picked;
    this.top.clearLayers();
    if (!picked) return;
    const style = getComputedStyle(this.map.getContainer());
    const halo = style.getPropertyValue("--halo").trim() || "#ffffff";
    const ink = style.getPropertyValue("--ink").trim() || "#17201c";
    this.top.addLayer(L.polygon(picked.shape, {renderer: this.renderer, interactive: false, color: halo, weight: 5, fill: false}));
    this.top.addLayer(L.polygon(picked.shape, {renderer: this.renderer, interactive: false, color: ink, weight: 2.5, fill: false}));
  }

  /** The cells' colours under other breaks (an eased refit): only the cells whose class changed are restyled. */
  recolour(breaks: number[]) {
    for (const d of this.drawn) {
      const cls = densityClass(d.density, breaks);
      if (cls === d.cls) continue;
      d.cls = cls;
      d.polygon.setStyle({color: this.colours[cls], fillColor: this.colours[cls]});
    }
  }

  remove() {
    this.group.remove();
    this.top.remove();
    this.renderer.remove();
  }
}
