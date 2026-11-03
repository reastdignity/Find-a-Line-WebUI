// The data coverage on the app's place map (PlaceMap): a button "Data coverage" (remembered in
// localStorage), the outlines of the areas with detailed data (coverage-shapes.json next to the bundle,
// fetched the first time it is switched on) filled by level, fainter as the map zooms in so the tiles
// stay readable; the 30 m rest of the world is left unfilled. A tooltip names the area and its level, a
// small legend links to the coverage page. The app is English: the coverage catalogue's English texts.
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

/** The fill's opacity at a zoom: strong on a continent, faint over a valley. */
const opacity = (zoom: number, partial: boolean) => (partial ? 0.6 : 1) * Math.max(0.1, Math.min(0.45, 0.45 - (zoom - 5) * 0.06));

export class CoverageLayer {
  private areas = L.featureGroup();
  private control: L.Control;
  private button!: HTMLButtonElement;
  private legend!: HTMLElement;
  private status!: HTMLElement;
  private filled = false;
  on = false;

  constructor(private map: L.Map, position: L.ControlPosition) {
    const layer = this;
    const Control = L.Control.extend({
      onAdd() {
        const box = L.DomUtil.create("div", "n-coverage");
        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);
        layer.button = L.DomUtil.create("button", "n-coverage-btn", box);
        layer.button.type = "button";
        layer.button.textContent = t("ui.coverage.layer");
        layer.button.addEventListener("click", () => layer.set(!layer.on));
        layer.legend = L.DomUtil.create("div", "n-coverage-legend", box);
        layer.legend.hidden = true;
        layer.status = L.DomUtil.create("div", "n-coverage-status", layer.legend);
        layer.status.setAttribute("role", "status");
        const list = L.DomUtil.create("ul", "", layer.legend);
        for (const level of [1, 2] as Level[]) {
          const item = L.DomUtil.create("li", "", list);
          L.DomUtil.create("span", `n-coverage-sw n-coverage-sw${level}`, item);
          item.append(`${ct("en", `level.${level}`)} (${level === 1 ? "≤ 1 m" : "2–5 m"})`);
        }
        const rest = L.DomUtil.create("li", "", list);
        L.DomUtil.create("span", "n-coverage-sw n-coverage-sw3", rest);
        rest.append(ct("en", "legend.rest"));
        const link = L.DomUtil.create("a", "n-coverage-link", layer.legend) as HTMLAnchorElement;
        link.href = "/coverage?lang=en";
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = t("ui.coverage.open") + " ›";
        return box;
      },
    });
    this.control = new Control({position}).addTo(map);
    map.on("zoomend", () => { if (this.on) this.paint(); });
    // a short map (a phone's search panel) keeps only the button and the link
    const fit = () => this.legend.classList.toggle("n-compact", map.getSize().y < 420);
    map.on("resize", fit);
    fit();
    if (remembered()) this.set(true);
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

  /** Switches the coverage on or off (remembered); the outlines are fetched the first time. */
  set(on: boolean) {
    this.on = on;
    remember(on);
    this.button.setAttribute("aria-pressed", String(on));
    this.button.classList.toggle("n-on", on);
    this.legend.hidden = !on;
    if (!on) {
      this.areas.remove();
      return;
    }
    this.areas.addTo(this.map);
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
        },
      }));
      this.paint();
    }).catch(() => { this.status.textContent = t("ui.coverage.failed"); });
  }

  remove() {
    this.areas.remove();
    this.control.remove();
  }
}
