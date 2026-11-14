// A test page of the uncertain shore's control (shoreLayer.ts) with the app's CSS (ui.css under .ui):
// tests/test_viewer.py opens it in headless Edge at a desktop and a phone width. On the phone layout (under
// 768 px) the chip with the total in view, unfold and fold, the state kept across a map move, hidden with no
// shore in view, the opened box with its "?" text within the map; on the desktop no chip and no fold button.
// The findings go into <pre id="result"> as JSON.

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "../src/ui/ui.css";
import { addShore, shoreTotal } from "../src/shoreLayer";
import type { Shore } from "../src/types";

const out: Record<string, unknown> = {};
const finish = () => {
  const pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
};

const shown = (e: Element | null | undefined) => !!e && (e as HTMLElement).offsetParent !== null;

try {
  const root = document.createElement("div");
  root.className = "ui";
  const div = document.createElement("div");
  div.style.width = "100%";
  div.style.height = "420px";
  root.appendChild(div);
  document.body.style.margin = "0";
  document.body.appendChild(root);
  const lat = 36.0, lon = 14.33;
  const map = L.map(div, {center: [lat, lon], zoom: 17});
  L.control.scale().addTo(map);  // a bottom-left corner the opened box keeps above
  const ring = (dx: number): [number, number][] => [[lon + dx - 0.0002, lat - 0.0001], [lon + dx + 0.0002, lat - 0.0001],
    [lon + dx + 0.0002, lat + 0.0001], [lon + dx - 0.0002, lat + 0.0001], [lon + dx - 0.0002, lat - 0.0001]];
  const shore: Shore = {rim_min: 5, segments: [{kind: "surface", px: 60, m: 1200, ring: ring(-0.0004)},
                                               {kind: "sea", px: 80, m: 1800, ring: ring(0.0004)}],
                        totals: {surface_m: 1200, sea_m: 1800, surface_px: 60, sea_px: 80}};
  addShore(map, shore, {});
  map.setView([lat, lon], 17, {animate: false});
  const holder = div.querySelector<HTMLElement>(".u-shore-ctl")!;
  const chip = holder.querySelector<HTMLButtonElement>(".u-shore-chip")!;
  const box = holder.querySelector<HTMLElement>(".u-shore")!;
  const fold = holder.querySelector<HTMLButtonElement>(".u-shore-fold")!;
  const help = holder.querySelector<HTMLButtonElement>(".u-shore-help")!;
  const more = holder.querySelector<HTMLElement>(".u-shore-more")!;
  const swatches = () => [...chip.querySelectorAll<HTMLElement>(".u-shore-swatch")].filter((s) => !s.hidden)
    .map((s) => s.classList.contains("u-shore-sea") ? "sea" : "surface");
  const state = () => ({holder: !holder.hidden, chip: shown(chip), box: shown(box), fold: shown(fold),
                        title: shown(holder.querySelector(".u-shore-title"))});
  out.phone = window.matchMedia("(max-width: 767px)").matches;
  out.totals = [shoreTotal(3000), shoreTotal(820), shoreTotal(999.4), shoreTotal(999.6), shoreTotal(1049)];
  out.start = {...state(), text: chip.textContent, label: chip.getAttribute("aria-label"),
               expanded: chip.getAttribute("aria-expanded"), swatches: swatches()};
  chip.focus();  // as from the keyboard: the focus moves to the fold button and back
  chip.click();
  out.unfolded = {...state(), expanded: chip.getAttribute("aria-expanded"), focus: document.activeElement === fold,
                  text: box.textContent};
  // A move that leaves only the sea's segment in view: still unfolded, its metres updated
  map.setView([lat, lon + 0.0006], 20, {animate: false});
  out.moved = {...state(), text: box.textContent, chipText: chip.textContent, swatches: swatches()};
  map.setView([lat, lon], 17, {animate: false});
  // The "?" text opened: the box keeps above the scale and within the map, its text scrolls inside
  help.click();
  const mapRect = div.getBoundingClientRect(), boxRect = box.getBoundingClientRect();
  const scale = div.querySelector<HTMLElement>(".leaflet-bottom.leaflet-left")!.getBoundingClientRect();
  out.help = {open: !more.hidden, bottom: Math.round(boxRect.bottom), scaleTop: Math.round(scale.top),
              mapBottom: Math.round(mapRect.bottom), scrolls: box.scrollHeight > box.clientHeight,
              overflow: getComputedStyle(box).overflowY,
              // the opened text scrolled up under the title, which stays in sight
              textUp: Math.abs(more.getBoundingClientRect().top - box.querySelector(".u-shore-head")!.getBoundingClientRect().bottom) < 6,
              titleTop: Math.round(box.querySelector(".u-shore-head")!.getBoundingClientRect().top - boxRect.top)};
  fold.click();
  out.folded = {...state(), expanded: chip.getAttribute("aria-expanded"), focus: document.activeElement === chip,
                helpClosed: more.hidden};
  map.setView([lat + 0.05, lon], 17, {animate: false});
  out.away = state();
  map.setView([lat, lon], 17, {animate: false});
  out.back = state();
} catch (e) {
  out.error = String(e && (e as Error).stack || e);
}
finish();
