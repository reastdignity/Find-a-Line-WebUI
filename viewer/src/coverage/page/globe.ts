// The globe: an orthographic projection on a canvas, turned by dragging (d3-drag) and zoomed with the
// wheel or the presets. It turns slowly by itself until touched, never under prefers-reduced-motion;
// frames are drawn only while it moves.
import { drag } from "d3-drag";
import { geoDistance, geoGraticule10, geoOrthographic, geoPath } from "d3-geo";
import { select } from "d3-selection";
import { levelColour, type Theme } from "../palette";
import type { Level } from "../types";
import { keyOf, levelOfKey, partialOfKey, type BoxName } from "./geo";
import { tween, type MapView, type ViewContext } from "./view";

/** Where each preset turns the globe ([lon, lat] in the middle) and how far it zooms in. */
const AIMS: Record<BoxName, {centre: [number, number]; k: number}> = {
  world: {centre: [10, 25], k: 1},
  europe: {centre: [12, 52], k: 2.6},
  na: {centre: [-100, 48], k: 1.7},
  oceania: {centre: [157, -30], k: 1.8},
};
const MAX_K = 8;
const SPIN = 0.006;  // degrees per millisecond

export function mountGlobe(el: HTMLElement, ctx: ViewContext): MapView {
  const canvas = document.createElement("canvas");
  canvas.className = "cov-canvas";
  el.append(canvas);
  const ratio = Math.min(2, devicePixelRatio || 1);
  const W = el.clientWidth || 600, H = el.clientHeight || 400;
  canvas.width = W * ratio;
  canvas.height = H * ratio;
  const g = canvas.getContext("2d")!;
  g.scale(ratio, ratio);
  const base = Math.min(W, H) / 2 - 16;
  let k = 1;
  const projection = geoOrthographic().translate([W / 2, H / 2]).scale(base).rotate([-15, -38]).clipAngle(90);
  const path = geoPath(projection, g);
  const hatches = new Map<string, CanvasPattern>();

  function hatch(theme: Theme, level: Level): CanvasPattern {
    const key = `${level}${levelColour(theme, level)}${theme.land}`;
    let pattern = hatches.get(key);
    if (!pattern) {
      const tile = document.createElement("canvas");
      tile.width = tile.height = 8;
      const x = tile.getContext("2d")!;
      x.fillStyle = theme.land;
      x.fillRect(0, 0, 8, 8);
      x.strokeStyle = levelColour(theme, level);
      x.lineWidth = 3;
      x.beginPath();
      for (const [a, b, c, d] of [[-2, 10, 10, -2], [-6, 6, 6, -6], [2, 14, 14, 2]]) { x.moveTo(a, b); x.lineTo(c, d); }
      x.stroke();
      pattern = g.createPattern(tile, "repeat")!;
      hatches.set(key, pattern);
    }
    return pattern;
  }

  const centre = () => projection.invert!([W / 2, H / 2])!;
  function draw() {
    const theme = ctx.theme(), chosen = ctx.selected();
    g.clearRect(0, 0, W, H);
    g.beginPath(); path({type: "Sphere"}); g.fillStyle = theme.sea; g.fill();
    g.lineWidth = 1; g.strokeStyle = theme.line; g.stroke();
    g.beginPath(); path(geoGraticule10()); g.globalAlpha = 0.5; g.stroke(); g.globalAlpha = 1;
    let selected = null;
    for (const f of ctx.geo.features) {
      const key = keyOf(f), level = levelOfKey(key);
      g.beginPath(); path(f);
      g.fillStyle = partialOfKey(key) ? hatch(theme, level) : levelColour(theme, level);
      g.fill();
      g.lineWidth = 0.5; g.strokeStyle = theme.edge; g.stroke();
      if (key === chosen) selected = f;
    }
    if (selected) { g.beginPath(); path(selected); g.lineWidth = 2; g.strokeStyle = theme.ink; g.stroke(); }
    const middle = centre();
    for (const dot of ctx.geo.dots) {
      if (geoDistance(dot.lonlat, middle) > 1.5) continue;
      const [x, y] = projection(dot.lonlat)!;
      g.beginPath(); g.arc(x, y, 4, 0, 2 * Math.PI);
      g.fillStyle = levelColour(theme, levelOfKey(dot.key)); g.fill();
      g.strokeStyle = dot.key === chosen ? theme.ink : theme.surface; g.lineWidth = 1.5; g.stroke();
    }
  }

  // turning by itself until the first touch
  let spinning = !ctx.reducedMotion(), frame = 0, last = performance.now();
  const spin = (now: number) => {
    const step = Math.min(50, now - last);
    last = now;
    if (!spinning) return;
    const [lon, lat] = projection.rotate();
    projection.rotate([lon + step * SPIN, lat]);
    draw();
    frame = requestAnimationFrame(spin);
  };
  if (spinning) frame = requestAnimationFrame(spin);
  const still = () => { spinning = false; cancelAnimationFrame(frame); };

  let moved = false;
  select(canvas).call(drag<HTMLCanvasElement, unknown>()
    .on("start", () => { still(); stop(); moved = false; })
    .on("drag", e => {
      moved = true;
      const [lon, lat] = projection.rotate(), scale = 75 / projection.scale();
      projection.rotate([lon + e.dx * scale, Math.max(-85, Math.min(85, lat - e.dy * scale))]);
      draw();
    }));
  const wheel = (e: WheelEvent) => {
    e.preventDefault();
    still();
    k = Math.max(1, Math.min(MAX_K, k * Math.exp(-e.deltaY * 0.002)));
    projection.scale(base * k);
    draw();
  };
  canvas.addEventListener("wheel", wheel, {passive: false});
  canvas.addEventListener("click", e => {
    if (moved) return;
    const box = canvas.getBoundingClientRect(), x = e.clientX - box.left, y = e.clientY - box.top;
    for (const dot of ctx.geo.dots) {  // the dots first: a small country is hard to hit
      if (geoDistance(dot.lonlat, centre()) > 1.5) continue;
      const [dx, dy] = projection(dot.lonlat)!;
      if (Math.hypot(dx - x, dy - y) < 9) { still(); ctx.select(dot.key); return; }
    }
    const lonlat = projection.invert!([x, y]);
    if (!lonlat || geoDistance(lonlat, centre()) > Math.PI / 2) return;
    const key = ctx.geo.hitAt(lonlat as [number, number]);
    if (key) { still(); ctx.select(key); }
  });
  const tip = document.createElement("div");
  tip.className = "cov-tip";
  tip.hidden = true;
  el.append(tip);
  canvas.addEventListener("pointermove", e => {
    if (e.pointerType === "touch" || e.buttons) { tip.hidden = true; return; }
    const box = canvas.getBoundingClientRect(), x = e.clientX - box.left, y = e.clientY - box.top;
    const lonlat = projection.invert!([x, y]);
    const key = lonlat && geoDistance(lonlat, centre()) < Math.PI / 2 ? ctx.geo.hitAt(lonlat as [number, number]) : null;
    tip.hidden = !key;
    if (key) {
      tip.textContent = ctx.label(key);
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    }
  });
  canvas.addEventListener("pointerleave", () => { tip.hidden = true; });

  let stop = () => {};
  draw();
  return {
    zoomTo(name) {
      still();
      stop();
      const aim = AIMS[name];
      const [lon0, lat0] = projection.rotate(), k0 = k;
      let lon1 = -aim.centre[0];
      lon1 += 360 * Math.round((lon0 - lon1) / 360);  // the shorter way round
      stop = tween(900, ctx.reducedMotion(), p => {
        k = Math.exp(Math.log(k0) + (Math.log(aim.k) - Math.log(k0)) * p);
        projection.rotate([lon0 + (lon1 - lon0) * p, lat0 + (-aim.centre[1] - lat0) * p]).scale(base * k);
        draw();
      });
    },
    update: () => { if (!spinning) draw(); },
    destroy() { still(); stop(); canvas.removeEventListener("wheel", wheel); el.replaceChildren(); },
  };
}
