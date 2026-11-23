// The map of the app: a click sets the centre of a circle, or areas are drawn
// (Leaflet-Geoman: polygons and rectangles), or an uploaded area is shown.
// Pages that only need a map (the OSM extracts, MapPage) take the search's layers, tools and clicks off
// it with setSearchVisible(false); `controls` places its controls. "Data coverage" (coverageLayer.ts) shows where
// the elevation data is detailed.
// Two arrangements of the controls (the user's pick of 2026-11-19, option A2 of the mock-up): on a desktop and a
// tablet the zoom, the layers and the coverage's own box at `controls`; on a phone (PHONE: the narrow frame, or a
// touch screen at most 480 px high: a phone held sideways) the zoom's two buttons side by side at the top left, the
// layers' button at the top right (its box closed until it is pressed; a press on the map closes it) and "Data
// coverage" as a row of that box. Their look is the result view's (result/view/mapbar.css, one set of rules).

import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { FeatureCollection, GeoJSON } from "geojson";
import L from "leaflet";
import { baseLayers } from "../baselayers";
import { t } from "../i18n";
import { TOUCH } from "../ui/components";
import { Layers } from "../layersControl";
import { keepScaleAboveAttribution } from "../result/view/corners";
import { ICONS } from "../ui/icons";
import { CoverageLayer } from "./coverageLayer";
import "../result/view/mapbar.css";  // the controls' look, shared with the result view's map

export type Mode = "point" | "draw" | "file" | "preset";
const COLOR = "#1f77b4";
const START: [number, number] = [50.1559508, 19.7562722];  // Żabi Koń
const MAX_ZOOM = 21;
/** Where the controls take the phone's arrangement: the app's narrow frame (components.tsx DESKTOP is 768 px), or a
 *  touch screen too low for the controls one above the other (a phone held sideways in the columns). */
export const PHONE = "(max-width: 767px), (pointer: coarse) and (max-height: 480px)";

/** Leaflet-Geoman's words for the tools the place map shows (its button titles, the actions under a tool, the
 *  tooltips while drawing), from the catalogue; a tooltip that names a click takes its tap twin on a touch screen. */
function geomanTexts() {
  const touch = typeof matchMedia === "function" && matchMedia(TOUCH).matches;
  const tip = (key: string) => t(`ui.draw.${key}${touch ? "_touch" : ""}`);
  return {
    tooltips: {firstVertex: tip("first_corner"), continueLine: tip("next_corner"), finishPoly: tip("finish_polygon"),
               finishRect: tip("finish_rectangle")},
    actions: {finish: t("ui.draw.finish"), cancel: t("ui.draw.cancel"), removeLastVertex: t("ui.draw.remove_last")},
    buttonTitles: {drawPolyButton: t("ui.draw.polygon"), drawRectButton: t("ui.draw.rectangle"), editButton: t("ui.draw.edit"),
                   dragButton: t("ui.draw.drag"), deleteButton: t("ui.draw.remove")},
  };
}

/** Each drawing tool's link named by its title (Geoman puts the title on the link's box only: axe's link-name). */
function nameTools(map: HTMLElement) {
  for (const box of map.querySelectorAll<HTMLElement>(".leaflet-pm-toolbar .button-container[title]")) {
    box.querySelector("a.leaflet-buttons-control-button")?.setAttribute("aria-label", box.title);
  }
}

export class PlaceMap {
  map: L.Map;
  private marker: L.Marker | null = null;
  private circle: L.Circle | null = null;
  private drawn = L.featureGroup();
  private shown = L.geoJSON(undefined, {style: {color: COLOR, weight: 2}});
  private preview = L.geoJSON(undefined, {interactive: false,
                                          style: {color: "#d95f02", weight: 2, dashArray: "6 4", fillOpacity: 0.08}});
  private mode: Mode = "point";
  private hidden = false;    // setSearchVisible(false)
  private controls: L.ControlPosition;  // of the zoom buttons, the layers and the drawing tools
  private phone = false;     // the phone's arrangement (PHONE): the drawing tools at the top left, a row beside the zoom
  coverage: CoverageLayer;   // where the elevation data is detailed (its own button)
  onPoint: (lat: number, lon: number) => void = () => {};
  onDrawn: () => void = () => {};

  /** `options.controls`: where the zoom buttons, the layer switch and the drawing tools go. */
  constructor(element: HTMLElement, options: {controls: L.ControlPosition}) {
    this.controls = options.controls;
    element.classList.add("c-placemap");  // the controls' look (result/view/mapbar.css)
    this.map = L.map(element, {center: START, zoom: 13, maxZoom: MAX_ZOOM, zoomControl: false});
    // the zoom's buttons with the kit's icons, not the characters "+" and "−" (R9), as the result view's
    const icon = (name: "plus" | "minus") => `<svg class="u-ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
    const zoom = L.control.zoom({position: options.controls, zoomInText: icon("plus"), zoomOutText: icon("minus")}).addTo(this.map);
    L.control.scale().addTo(this.map);
    keepScaleAboveAttribution(element);  // on a phone the credits take the whole width: the scale above them
    const layers = baseLayers(null, MAX_ZOOM);
    Object.values(layers)[0].addTo(this.map);
    const layersControl = new Layers(layers, {}, {position: options.controls}).addTo(this.map);
    this.coverage = new CoverageLayer(this.map, options.controls, layersControl);
    // the arrangement follows the window (a phone turned, a window made narrow)
    const media = typeof matchMedia === "function" ? matchMedia(PHONE) : null;
    const arrange = () => {
      const phone = this.phone = !!media?.matches;
      // the layers' control is built again at its new place: the keyboard's focus on its button goes with it
      const held = !!layersControl.getContainer()?.contains(document.activeElement);
      element.classList.toggle("c-map-phone", phone);
      zoom.setPosition(phone ? "topleft" : options.controls);
      layersControl.setPosition(phone ? "topright" : options.controls);
      this.coverage.place(phone ? "row" : "box");
      if (this.mode === "draw" && !this.hidden) this.setMode("draw");  // the drawing tools to their corner
      if (held) layersControl.getContainer()?.querySelector<HTMLElement>(".leaflet-control-layers-toggle")?.focus();
    };
    arrange();
    media?.addEventListener("change", arrange);
    this.map.on("unload", () => media?.removeEventListener("change", arrange));  // not after the map is gone
    // an open layers' box is fitted again when the map's size changes (a phone turned): its last row stays in reach
    this.map.on("resize", () => {
      if (layersControl.getContainer()?.classList.contains("leaflet-control-layers-expanded")) layersControl.expand();
    });
    this.drawn.addTo(this.map);
    this.shown.addTo(this.map);
    this.preview.addTo(this.map);
    this.map.pm.setGlobalOptions({layerGroup: this.drawn, pathOptions: {color: COLOR}, exitModeOnEscape: true} as any);
    // the drawing tools' words from the catalogue, in sentence case (Geoman's own are English in title case); a tap's
    // words on a touch screen (B2 of step 3d's G6)
    this.map.pm.setLang("findaline" as any, geomanTexts(), "en");
    this.map.on("pm:create", (e: any) => {
      e.layer.on("pm:edit", () => this.onDrawn());
      this.onDrawn();
    });
    this.map.on("pm:remove", () => this.onDrawn());
    // a finger's tap on the map that closes the opened layers' box sets no centre (the user's pick: "closes on a tap
    // on the map", on phone frames); a mouse's click sets the centre as ever, the box open or not. Whether the box is
    // open is read when the pointer goes down: Leaflet closes it before the click (on the pointer leaving the box, or
    // on the map's click)
    let closing = false;
    element.addEventListener("pointerdown", (e) => {
      const box = layersControl.getContainer();  // a press inside the box closes nothing
      closing = e.pointerType !== "mouse" && !!box?.classList.contains("leaflet-control-layers-expanded") &&
        !box.contains(e.target as Node);
    }, true);
    this.map.on("click", (e: L.LeafletMouseEvent) => {
      if (closing) { closing = false; return; }
      if (this.mode === "point" && !this.hidden) this.onPoint(e.latlng.lat, e.latlng.lng);
    });
  }

  /** Removes the drawing tools and ends any of their modes: removing the toolbar alone leaves an
   *  unfinished polygon drawing, whose shape would join the search unseen. */
  private stopTools() {
    const pm = this.map.pm;
    pm.disableDraw();
    pm.disableGlobalEditMode();
    pm.disableGlobalDragMode();
    pm.disableGlobalRemovalMode();
    pm.disableGlobalCutMode();
    pm.disableGlobalRotateMode();
    pm.removeControls();
  }

  /** Shows or hides the search on the map: the point and circle, the drawn and uploaded areas, the
   *  preview, the drawing tools and the clicks that set the centre. */
  setSearchVisible(visible: boolean) {
    if (visible === !this.hidden) return;
    this.hidden = !visible;
    if (visible) {
      this.preview.addTo(this.map);
      this.setMode(this.mode);
      return;
    }
    this.stopTools();
    for (const layer of [this.marker, this.circle, this.drawn, this.shown, this.preview]) layer?.remove();
    this.map.getContainer().style.cursor = "";
  }

  setMode(mode: Mode) {
    this.mode = mode;
    if (this.hidden) return;  // setSearchVisible(true) applies it
    if (mode === "draw") {
      // a phone: at the top left, a row beside the zoom (mapbar.css; at the bottom right their column reaches the
      // layers' button)
      this.map.pm.removeControls();
      this.map.pm.addControls({position: this.phone ? "topleft" : this.controls, drawMarker: false, drawCircleMarker: false,
                               drawPolyline: false, drawText: false, drawCircle: false, cutPolygon: false,
                               rotateMode: false});
      nameTools(this.map.getContainer());
    } else this.stopTools();
    const point = mode === "point";
    for (const layer of [this.marker, this.circle]) {
      if (layer && point) layer.addTo(this.map); else if (layer) layer.remove();
    }
    if (mode === "draw") this.drawn.addTo(this.map); else this.drawn.remove();
    if (mode === "file") this.shown.addTo(this.map); else this.shown.remove();
    this.map.getContainer().style.cursor = point ? "crosshair" : "";
  }

  /** The centre of the circle and its radius in metres. */
  setPoint(lat: number, lon: number, radius: number) {
    if (!this.marker) {
      this.marker = L.marker([lat, lon]);
      this.circle = L.circle([lat, lon], {radius, color: COLOR, weight: 2, fill: false, interactive: false});
      if (!this.hidden) {
        this.marker.addTo(this.map);
        this.circle.addTo(this.map);
      }
    }
    this.marker.setLatLng([lat, lon]);
    this.circle!.setLatLng([lat, lon]).setRadius(radius);
  }

  /** Removes the point, the drawn areas, the uploaded file and the preview. */
  clear() {
    this.marker?.remove();
    this.circle?.remove();
    this.marker = this.circle = null;
    this.drawn.clearLayers();
    this.shown.clearLayers();
    this.preview.clearLayers();
    this.onDrawn();
  }

  /** Areas to edit (a job's drawn or uploaded area): they replace the drawn ones. */
  loadDrawn(areas: GeoJSON) {
    this.drawn.clearLayers();
    L.geoJSON(areas as any, {style: {color: COLOR}}).eachLayer((layer) => {
      layer.on("pm:edit", () => this.onDrawn());
      this.drawn.addLayer(layer);
    });
    if (this.drawn.getLayers().length) this.map.fitBounds(this.drawn.getBounds(), {maxZoom: 17});
    this.onDrawn();
  }

  /** The drawn polygons and rectangles, or null. */
  drawnAreas(): FeatureCollection | null {
    const collection = this.drawn.toGeoJSON() as FeatureCollection;
    return collection.features.length ? collection : null;
  }

  showFile(collection: FeatureCollection | null) {
    this.shown.clearLayers();
    if (collection) {
      this.shown.addData(collection);
      this.map.fitBounds(this.shown.getBounds(), {maxZoom: 16});
    }
  }

  /** The area the estimate says will be searched (null: none). */
  showPreview(area: GeoJSON | null) {
    this.preview.clearLayers();
    if (area) this.preview.addData(area as any);
  }

  /** The visible part of the map as S,W,N,E (for --within). */
  viewBox(): string {
    const b = this.map.getBounds();
    return [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map((v) => v.toFixed(5)).join(",");
  }
}
