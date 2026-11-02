// The map of the images and animations: Equal Earth (d3-geo) seen by a camera (a centre and a zoom over the
// world fitted to the box's width), the areas in their level's colour, hatched where the level is reached in
// parts only, small areas as dots too.
import { geoEqualEarth, geoPath, type GeoProjection } from "d3-geo";
import { areaOf, levelOf } from "../data";
import { levelColour, type Theme } from "../palette";
import type { Level } from "../types";
import { rrect, type Box, type Ctx } from "./canvas";
import type { View, World } from "./world";

/** The boxes (west-south, east-north) the cameras of the views frame. */
export const BOXES: Record<View, [[number, number], [number, number]]> = {
  world: [[-170, -58], [190, 80]], europe: [[-11, 35], [33, 71.5]], na: [[-168, 16], [-52, 71]],
  oceania: [[140, -48], [180, -26]],
};

export interface Camera { lon: number; lat: number; k: number }

const baseScales = new Map<number, number>();
/** The scale of Equal Earth showing the whole sphere `w` wide. */
function baseScale(w: number): number {
  if (!baseScales.has(w)) baseScales.set(w, geoEqualEarth().fitWidth(w, {type: "Sphere"}).scale());
  return baseScales.get(w)!;
}

const cameras = new Map<string, Camera>();
/** The camera framing a view in a box (the world never zoomed in beyond its width). */
export function camFor(view: View, box: Box): Camera {
  const key = `${view}${box.w}x${box.h}`;
  if (cameras.has(key)) return cameras.get(key)!;
  const [[w, s], [e, n]] = BOXES[view], lon = (w + e) / 2, lat = (s + n) / 2;
  const p = geoEqualEarth().rotate([-lon, 0]).scale(baseScale(box.w)).translate([0, 0]);
  const pts: [number, number][] = [];
  for (let i = 0; i <= 8; i++) for (const y of [s, n, (s + n) / 2]) pts.push(p([w + (e - w) * i / 8, y])!);
  const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]);
  const k = Math.min(box.w * .92 / (Math.max(...xs) - Math.min(...xs)), box.h * .92 / (Math.max(...ys) - Math.min(...ys)));
  const cam = {lon, lat, k: view === "world" ? Math.min(k, 1) : k};
  cameras.set(key, cam);
  return cam;
}

/** Between two cameras: the centre linearly, the zoom on a log scale (an even flight). */
export const lerpCam = (a: Camera, b: Camera, t: number): Camera => ({
  lon: a.lon + (b.lon - a.lon) * t, lat: a.lat + (b.lat - a.lat) * t,
  k: Math.exp(Math.log(a.k) + (Math.log(b.k) - Math.log(a.k)) * t),
});

export function projFor(cam: Camera, box: Box): GeoProjection {
  const p = geoEqualEarth().rotate([-cam.lon, 0]).scale(baseScale(box.w) * cam.k).translate([0, 0]);
  const c = p([cam.lon, cam.lat])!;
  return p.translate([box.x + box.w / 2 - c[0], box.y + box.h / 2 - c[1]]);
}

const hatches = new Map<string, CanvasPattern>();
/** Stripes of a level's colour over the land: the level in parts of the area only. */
export function hatchFor(ctx: Ctx, th: Theme, level: Level, scale: number): CanvasPattern {
  const key = th.bg + level + scale.toFixed(1);
  if (hatches.has(key)) return hatches.get(key)!;
  const n = Math.max(6, Math.round(10 * scale)), c = document.createElement("canvas");
  c.width = c.height = n;
  const x = c.getContext("2d")!;
  x.fillStyle = th.land; x.fillRect(0, 0, n, n);
  x.strokeStyle = levelColour(th, level); x.lineWidth = n * .38;
  x.beginPath();
  for (const o of [-n, 0, n]) { x.moveTo(o - 2, n + 2); x.lineTo(o + n + 2, -2); }
  x.stroke();
  const pattern = ctx.createPattern(c, "repeat")!;
  hatches.set(key, pattern);
  return pattern;
}

export interface MapOptions {
  reveal?: (id: string) => number;   // 0..1, how far an area's colour has come in (default: all)
  radius?: number;                   // rounded corners of the box
}

/** Draws the map into `box` (clipped); returns the projection. */
export function drawMap(ctx: Ctx, th: Theme, world: World, box: Box, cam: Camera, o: MapOptions = {}): GeoProjection {
  const proj = projFor(cam, box), path = geoPath(proj, ctx), reveal = o.reveal || (() => 1);
  ctx.save(); rrect(ctx, box.x, box.y, box.w, box.h, o.radius || 0); ctx.clip();
  ctx.fillStyle = th.sea; ctx.fillRect(box.x, box.y, box.w, box.h);
  const lw = Math.max(.5, box.w / 1400), scale = box.w / 1080;
  ctx.fillStyle = th.land;
  for (const f of world.countries) { ctx.beginPath(); path(f); ctx.fill(); }
  for (const f of [...world.countries, ...world.regions]) {
    const area = f.properties.rest ? null : areaOf(f.properties.id);
    if (!area) continue;
    const r = reveal(f.properties.id);
    if (r <= 0) continue;
    ctx.beginPath(); path(f); ctx.globalAlpha = r;
    ctx.fillStyle = area.partial ? hatchFor(ctx, th, area.level, scale * 2) : levelColour(th, area.level);
    ctx.fill(); ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = th.edge;
  ctx.beginPath(); for (const f of world.countries) path(f); ctx.lineWidth = lw; ctx.stroke();
  ctx.beginPath(); for (const f of world.regions) path(f); ctx.lineWidth = lw * .8; ctx.stroke();
  const dot = Math.max(4, box.w / 160);
  for (const id of world.small) {
    const r = reveal(id), [x, y] = proj(world.centroids.get(id)!)!;
    if (x < box.x || x > box.x + box.w || y < box.y || y > box.y + box.h) continue;
    ctx.beginPath(); ctx.arc(x, y, dot, 0, 7);
    ctx.fillStyle = r > 0 ? levelColour(th, levelOf(id)) : th.land; ctx.globalAlpha = Math.max(.5, r); ctx.fill();
    ctx.globalAlpha = 1; ctx.lineWidth = dot * .45; ctx.strokeStyle = th.bg; ctx.stroke();
  }
  ctx.restore();
  return proj;
}
