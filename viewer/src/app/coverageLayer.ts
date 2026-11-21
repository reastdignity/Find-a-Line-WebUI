// The data coverage on the app's place map (PlaceMap): "Data coverage" (remembered in localStorage), the
// outlines of the areas with detailed data (coverage-shapes.json next to the bundle, fetched the first time it
// is switched on) filled by level, fainter as the map zooms in so the tiles stay readable; the 30 m rest of the
// world is left unfilled. A tooltip names the area and its level, a small legend links to the coverage page. The
// app is English: the coverage catalogue's English texts.
// Two places (PlaceMap's arrangements; `place`): a box of its own among the map's controls with a button (a
// desktop, a tablet), or a row of the layers' box (a phone: Leaflet's own checkbox of an overlay, with the link to
// the coverage page at the row's end while it is ticked: put there again after each redraw of the box's rows). Either way the layer is on while its outlines' group is
// on the map: the button and the checkbox only add or remove the group.
import L from "leaflet";
import { areaOf, loadShapes, SHAPES_FILE, type Shape } from "../coverage/data";
import { areaName, ct, resText } from "../coverage/i18n";
import { THEMES, levelColour, type Theme } from "../coverage/palette";
import type { Level } from "../coverage/types";
import { t } from "../i18n";
import "./coverageLayer.css";

const STORAGE_KEY = "findaline.layer.coverage";
// the outlines lie next to this bundle (/app/app.js → /app/coverage-shapes.json)
const script = typeof document !== "undefined" ? document.currentScript as HTMLScriptElement | null : null;
const SHAPES_URL = script?.src ? new URL(SHAPES_FILE, script.src).href : SHAPES_FILE;

function remembered(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === "1"; } catch { return false; }
}
function remember(on: boolean) {
  try { localStorage.setItem(STORAGE_KEY, on ? "1" : "0"); } catch { /* not remembered */ }
}

/** A press on an outline moves no focus (the map keeps Leaflet's: its keys go on working). */
const noFocus = (e: Event) => e.preventDefault();

/** The fill's opacity at a zoom: strong on a continent, faint over a valley. */
const opacity = (zoom: number, partial: boolean) => (partial ? 0.6 : 1) * Math.max(0.1, Math.min(0.45, 0.45 - (zoom - 5) * 0.06));

export type CoveragePlace = "box" | "row";

export class CoverageLayer {
  private areas = L.featureGroup();
  private control: L.Control;
  private box!: HTMLElement;
  private button!: HTMLButtonElement;
  private legend: HTMLElement;   // the status line and the three levels
  private status: HTMLElement;
  private link: HTMLAnchorElement;
  private extra: HTMLElement;    // in the layers' box: the legend under the coverage's row
  private placed: CoveragePlace | null = null;
  private filled = false;
  on = false;

  constructor(private map: L.Map, position: L.ControlPosition, private layers: L.Control.Layers) {
    const layer = this;
    this.legend = L.DomUtil.create("div", "n-coverage-legend");
    this.legend.hidden = true;
    this.status = L.DomUtil.create("div", "n-coverage-status", this.legend);
    this.status.setAttribute("role", "status");
    const list = L.DomUtil.create("ul", "", this.legend);
    for (const level of [1, 2] as Level[]) {
      const item = L.DomUtil.create("li", "", list);
      L.DomUtil.create("span", `n-coverage-sw n-coverage-sw${level}`, item);
      item.append(`${ct("en", `level.${level}`)} (${level === 1 ? "≤ 1 m" : "2–5 m"})`);
    }
    const rest = L.DomUtil.create("li", "", list);
    L.DomUtil.create("span", "n-coverage-sw n-coverage-sw3", rest);
    rest.append(ct("en", "legend.rest"));
    this.link = L.DomUtil.create("a", "n-coverage-link") as HTMLAnchorElement;
    this.link.href = "/coverage?lang=en";
    this.link.target = "_blank";
    this.link.rel = "noopener";
    this.link.textContent = t("ui.coverage.open");
    this.link.hidden = true;
    this.extra = L.DomUtil.create("div", "n-coverage-extra");
    const Control = L.Control.extend({
      onAdd() {
        if (layer.box) return layer.box;
        const box = layer.box = L.DomUtil.create("div", "n-coverage");
        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);
        layer.button = L.DomUtil.create("button", "n-coverage-btn", box);
        layer.button.type = "button";
        layer.button.textContent = t("ui.coverage.layer");
        layer.button.addEventListener("click", () => layer.set(!layer.on));
        return box;
      },
    });
    this.control = new Control({position});
    (layers.options as any).afterUpdate = () => this.dress();
    // the group on the map is the layer switched on, whoever put it there (the button, the layers' checkbox)
    this.areas.on("add", () => this.switched(true));
    // not the map's own removal (a page left): Leaflet takes every layer off then, and the choice must stay
    let leaving = false;
    map.on("unload", () => { leaving = true; });
    this.areas.on("remove", () => { if (!leaving) this.switched(false); });
    map.on("zoomend", () => { if (this.on) this.paint(); });
    // a short map (a phone's search panel) keeps only the button or the row, and the link
    const fit = () => this.legend.classList.toggle("n-compact", map.getSize().y < 420);
    map.on("resize", fit);
    fit();
    if (remembered()) this.set(true);
  }

  /** Where the coverage is switched: its own box among the map's controls, or a row of the layers' box. */
  place(place: CoveragePlace) {
    if (place === this.placed) return;
    this.placed = place;
    if (place === "box") {
      this.layers.removeLayer(this.areas);
      this.extra.remove();
      this.control.addTo(this.map);
      this.box.append(this.legend);
      this.legend.append(this.link);
    } else {
      this.control.remove();
      this.extra.append(this.legend);
      this.layers.addOverlay(this.areas, t("ui.coverage.layer"));  // draws the rows: dress() follows
      this.dress();
    }
    this.show();
  }

  /** In the layers' box: the link at the end of the coverage's row (its only overlay), the legend under the rows. */
  private dress() {
    if (this.placed !== "row") return;
    const box = this.layers.getContainer();
    // beside the row's label, not inside it: the checkbox keeps its name "Data coverage"
    box?.querySelector(".leaflet-control-layers-overlays")?.append(this.link);
    box?.querySelector(".leaflet-control-layers-list")?.append(this.extra);
  }

  private theme(): Theme {
    return getComputedStyle(this.map.getContainer()).colorScheme === "dark" ? THEMES.dark : THEMES.light;
  }

  private style(shape: Shape): L.PathOptions {
    const id = shape.properties.id, area = areaOf(id)!, theme = this.theme(), zoom = this.map.getZoom();
    return {fillColor: levelColour(theme, area.level), fillOpacity: opacity(zoom, area.partial),
            color: area.partial ? theme.l1 : levelColour(theme, area.level), weight: area.partial ? 1.5 : 1,
            opacity: 0.8, dashArray: area.partial ? "5 4" : undefined, className: "n-coverage-area"};
  }

  private paint() {
    this.areas.eachLayer(layer => (layer as L.GeoJSON).setStyle(f => this.style(f as Shape)));
    const theme = this.theme();
    for (const level of [1, 2, 3] as Level[]) {
      const swatch = this.legend.querySelector<HTMLElement>(`.n-coverage-sw${level}`);
      if (swatch) swatch.style.background = level === 3 ? "transparent" : levelColour(theme, level);
    }
  }

  /** What shows that the layer is on: the button's state, the legend, the link. */
  private show() {
    this.button?.setAttribute("aria-pressed", String(this.on));
    this.button?.classList.toggle("n-on", this.on);
    this.legend.hidden = !this.on;
    this.link.hidden = !this.on;
  }

  /** Switches the coverage on or off (remembered); the outlines are fetched the first time. */
  set(on: boolean) {
    if (on) this.areas.addTo(this.map); else this.areas.remove();
  }

  /** The group was put on the map or taken off it. */
  private switched(on: boolean) {
    this.on = on;
    remember(on);
    this.show();
    if (!on) return;
    this.paint();
    if (this.filled) return;
    this.status.textContent = t("ui.coverage.loading");
    loadShapes(SHAPES_URL).then(shapes => {
      if (this.filled) return;
      this.filled = true;
      this.status.textContent = "";
      // only the areas with detailed data, not a country's rest (the 30 m stays unfilled)
      const covered = shapes.features.filter(f => !f.properties.rest && areaOf(f.properties.id));
      this.areas.addLayer(L.geoJSON(covered as any, {
        style: f => this.style(f as Shape),
        onEachFeature: (f, layer) => {
          const id = (f as Shape).properties.id, area = areaOf(id)!;
          layer.bindTooltip(`${areaName(id, "en")}: ${ct("en", `level.${area.level}`)}, ${resText(area.res, "en")}` +
                            (area.partial ? ` (${ct("en", "legend.partial").toLowerCase()})` : ""), {sticky: true});
          // Out of the Tab order: Leaflet listens for the focus on an outline with a tooltip, and Chromium makes an SVG
          // shape with such a listener a Tab stop (83 before the pin and the map's controls); the coverage page's link
          // is the keyboard's way. And no focus by a press: tabindex lets WebKit focus the outline on a press, which
          // kept its tooltip open and stopped the arrows panning the map; with the press's default prevented the map
          // keeps the focus Leaflet gives it on any press, in WebKit as before and in Chromium now too (where a press
          // focused the outline). Each time the outline is drawn (its element is made anew when the layer is added)
          layer.on("add", () => {
            const outline = (layer as L.Path).getElement();
            outline?.setAttribute("tabindex", "-1");
            outline?.addEventListener("mousedown", noFocus);
          });
        },
      }));
      this.paint();
    }).catch(() => { this.status.textContent = t("ui.coverage.failed"); });
  }

  remove() {
    this.areas.remove();
    this.layers.removeLayer(this.areas);
    this.extra.remove();
    this.control.remove();
  }
}
