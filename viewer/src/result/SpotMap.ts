// The result view's canvas (docs/line-volume/spec-view.md B.2): draws a SpotView (spots.ts) on a Leaflet map the
// frame (view/SpotColumns.tsx) owns, and tells the view what the map shows: at every full redraw (the map moved,
// zoomed or was resized, the frame's free part changed) the part of the map a person sees goes to the view as a
// Quad in the run's grid metres with its metres per pixel (SpotView.setView), which gives the level under Auto,
// the spots in view and their numbers.
//
// MILESTONE 1: the moves and the view's rectangle only. The drawing (squares, strokes, numbers, the fan), the
// presses and the hover come with milestones 2 and 3; `highlight`, `hoverAt` and `drawn` are in place for the
// panels that call them.

import L from "leaflet";
import type { Padding } from "./ResultMap";
import type { SpotChoice, SpotView } from "./spots";
import type { Quad } from "./viewgeom";

export type { Padding };

export interface SpotMapOptions {
  /** Several spots lie about as near a press (`at`: its point in the map's container): let the user choose. */
  onChoose(c: SpotChoice[], at: L.Point): void;
  /** A short message of the map ("Several spots here. Zoomed in. Tap again."). */
  onToast(text: string): void;
  /** The frame's own boxes over the map (the hint, its "?"): no number is placed under them. */
  obstacles(): DOMRect[];
  // --- added to the plan's interface (section 1) ---
  /** The pixels of the map's box, from each side, that a person does not see (a phone's sheet): the view's
   *  rectangle is the rest. None: the whole box. */
  free?(): Padding;
  /** After every full redraw (the first one: the view is drawn). */
  onDrawn?(): void;
}

const NONE: Padding = {top: 0, right: 0, bottom: 0, left: 0};
/** The closest a move of the map by the page zooms in, metres per pixel (the mock-up's last zoom): a row revealed,
 *  a sector shown; from here on a crowded tap opens the table of spots (B.2 item 9). */
export const CLOSE_MPP = 0.25;
const SNAP = 0.25;

export class SpotMap {
  private readonly map: L.Map;
  private readonly view: SpotView;
  private readonly options: SpotMapOptions;
  private readonly unsubscribe: () => void;
  private redrawing = false;
  private hovered: number | null = null;
  private marker: L.LatLngExpression | null = null;

  constructor(map: L.Map, view: SpotView, options: SpotMapOptions) {
    this.map = map;
    this.view = view;
    this.options = options;
    map.on("moveend resize", this.refresh);
    this.unsubscribe = view.subscribe(() => { if (!this.redrawing) this.paint(); });
  }

  /** Remove every layer and handler of this map. */
  destroy() {
    this.unsubscribe();
    this.map.off("moveend resize", this.refresh);
  }

  // --- the view's rectangle ---

  /** The part of the map's box a person sees, in the container's pixels. */
  private freeBox(): {left: number; top: number; right: number; bottom: number} {
    const size = this.map.getSize(), p = this.options.free?.() ?? NONE;
    const left = Math.min(Math.max(0, p.left), size.x), top = Math.min(Math.max(0, p.top), size.y);
    return {left, top, right: Math.max(left, size.x - Math.max(0, p.right)), bottom: Math.max(top, size.y - Math.max(0, p.bottom))};
  }

  /** A full redraw: the view's rectangle and metres per pixel to the model, then the picture. Called by the map's
   *  moves; the frame calls it when the free part changed without one (a phone's sheet moved). */
  refresh = () => {
    const map = this.map, fit = this.view.fit, box = this.freeBox();
    if (!(box.right > box.left && box.bottom > box.top)) return;
    const corner = (x: number, y: number): [number, number] => {
      const at = map.containerPointToLatLng([x, y]);
      return fit.toGrid(at.lat, at.lng);
    };
    const quad: Quad = [corner(box.left, box.top), corner(box.right, box.top), corner(box.right, box.bottom),
                        corner(box.left, box.bottom)];
    // metres of the grid per pixel at the view's middle: the map's metres on the ground there, by the grid's scale
    // (the corners above are clamped to the run's box by the fit, so their distance is not the view's width)
    const y = (box.top + box.bottom) / 2, x = (box.left + box.right) / 2, span = Math.min(64, (box.right - box.left) / 2);
    const west = map.containerPointToLatLng([x - span, y]), east = map.containerPointToLatLng([x + span, y]);
    const mpp = map.distance(west, east) / (2 * span) * fit.scale((west.lat + east.lat) / 2, (west.lng + east.lng) / 2);
    this.redrawing = true;
    try {
      this.view.setView(quad, mpp);
    } finally {
      this.redrawing = false;
    }
    this.paint();
    this.options.onDrawn?.();
  };

  /** The picture again (milestone 2). */
  private paint() {
    // drawn from milestone 2 on
  }

  // --- moves ---

  private fitOptions(p: Padding, margin: number, maxMpp?: number): L.FitBoundsOptions {
    return {paddingTopLeft: [p.left + margin, p.top + margin], paddingBottomRight: [p.right + margin, p.bottom + margin],
            maxZoom: maxMpp ? this.zoomOf(maxMpp) : this.view.model.data.max_zoom, animate: false};
  }

  /** The zoom at which the map shows `mpp` metres per pixel, on the map's quarter steps (not above its last). */
  zoomOf(mpp: number): number {
    const now = this.view.mpp, zoom = this.map.getZoom();
    const want = now === now ? zoom + Math.log2(now / mpp) : zoom;
    return Math.min(this.map.getMaxZoom(), Math.floor(want / SNAP + 1e-6) * SNAP);
  }

  private bounds(xy: [number, number][]): L.LatLngBounds {
    return L.latLngBounds(xy.map(([x, y]) => this.view.fit.toLatLng(x, y)));
  }

  /** Fit the map to the run's lines (the box of their anchors), `p` px kept free on each side. */
  fitArea(p: Padding = NONE) {
    const box = this.view.model.data.box;
    if (!box) return;
    this.map.fitBounds(this.bounds([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]),
                       this.fitOptions(p, 16));
  }

  /** Fit the map to a line, `p` px kept free on each side plus a margin. */
  zoomTo(row: number, p: Padding = NONE) {
    const {x1, y1, x2, y2} = this.view.values;
    this.map.fitBounds(this.bounds([[x1[row], y1[row]], [x2[row], y2[row]]]), this.fitOptions(p, 60));
  }

  /** Bring a line of the list into view: the map moves only when the line is not inside the view less 8 % or is
   *  under 60 px long (then it is fitted, not closer than CLOSE_MPP). */
  reveal(row: number, p: Padding = NONE) {
    const {x1, y1, x2, y2, len} = this.view.values, box = this.freeBox();
    const dx = (box.right - box.left) * 0.08, dy = (box.bottom - box.top) * 0.08;
    const ends = this.bounds([[x1[row], y1[row]], [x2[row], y2[row]]]);
    const inside = [ends.getSouthWest(), ends.getNorthEast(), ends.getNorthWest(), ends.getSouthEast()].every((at) => {
      const q = this.map.latLngToContainerPoint(at);
      return q.x >= box.left + dx && q.x <= box.right - dx && q.y >= box.top + dy && q.y <= box.bottom - dy;
    });
    if (inside && len[row] / this.view.mpp >= 60) return;
    this.map.fitBounds(ends, this.fitOptions(p, 50, CLOSE_MPP));
  }

  /** Fit the map to the shown lines of a sector's spots (`n`: the sector from 0) and flash them. */
  showSector(n: number) {
    const sector = this.view.sectors.find((s) => s.n === n);
    if (!sector || !sector.spots.length) return;
    const {x1, y1, x2, y2} = this.view.values, xy: [number, number][] = [];
    for (const spot of sector.spots) {
      const row = this.view.shownOf(spot);
      xy.push([x1[row], y1[row]], [x2[row], y2[row]]);
    }
    this.map.fitBounds(this.bounds(xy), this.fitOptions(this.options.free?.() ?? NONE, 30, CLOSE_MPP));
    // the flash of 2.4 s comes with the drawing (milestone 2)
  }

  /** Draw a line wider (a row of the list under the mouse); null: none. */
  highlight(row: number | null) {
    this.hovered = row;
    this.paint();
  }

  /** The point of the profile under the mouse; null: none. */
  hoverAt(at: L.LatLngExpression | null) {
    this.marker = at;
    this.paint();
  }

  /** What the map shows now, by the page's own count: the strokes of lines and the numbers with their boxes in the
   *  viewport. */
  drawn(): {strokes: number; numbers: {label: string; box: DOMRect}[]} {
    void this.hovered; void this.marker;
    return {strokes: 0, numbers: []};
  }
}
