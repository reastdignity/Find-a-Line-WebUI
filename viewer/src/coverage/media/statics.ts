// The still images: README's world and continents (2:1, light and dark from the theme), the carousel (4:5),
// the Stories (9:16) and the A3 poster at 300 dpi.
import { areaOf } from "../data";
import { camFor, drawMap } from "../draw/map";
import { areaName, ct, resText } from "../i18n";
import { levelColour } from "../palette";
import { bgFill, chip, font, rrect, text, type Frame } from "../draw/canvas";
import { drawLogo, logoHeight } from "../draw/logo";
import {
  captionTop, footer, layoutOf, legend, legendAboveFooter, legendWidth, levelLabel, levelTag, mapBox, mapBoxUnder, plate, SITE,
} from "../draw/layout";
import type { View } from "../draw/world";
import type { Level } from "../types";
import { got } from "./assets";
import { sceneEnd, summaryText } from "./scenes";

export type StaticGroup = "readme" | "carousel" | "stories" | "poster";
export interface StaticImage { name: string; width: number; height: number; group: StaticGroup; draw: (f: Frame) => void }

const VIEWS: View[] = ["world", "europe", "na", "oceania"];

/** README: the map under its title, the legend in a box bottom left, the credit and address bottom right. */
function readme(view: View) {
  return (f: Frame) => {
    const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), box = mapBox(W, H);
    bgFill(f);
    drawMap(ctx, th, got().world, box, camFor(view, box));
    captionTop(f, ct(lang, "media.readme.title"), view === "world" ? ct(lang, "legend.rest") : ct(lang, `zoom.${view}`));
    const size = L.body * .78, rows = 4, pad = L.pad * .4;
    const w = legendWidth(f, size, {title: false}) + 2 * pad, h = size * 1.35 * (rows - 1) + size * .82 + 2 * pad;
    const x = L.pad * .6, y = H - L.pad * .6 - h;
    rrect(ctx, x, y, w, h, 14); ctx.fillStyle = th.bg; ctx.globalAlpha = .88; ctx.fill(); ctx.globalAlpha = 1;
    legend(f, x + pad, y + pad + size * .72, size, {title: false});
    const credit = `${ct(lang, "map.credit")} · ${SITE}`;
    ctx.font = font(500, L.small, "m");
    const cw = ctx.measureText(credit).width;
    plate(f, W - L.pad * .6 - cw, H - L.small, cw, L.small);
    ctx.fillStyle = th.muted; ctx.textAlign = "right"; ctx.fillText(credit, W - L.pad * .6, H - L.small); ctx.textAlign = "left";
  };
}

/** The first slide: the logo, the question, the world in the height left above the "Swipe" chip. */
function cover(f: Frame): void {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H);
  bgFill(f);
  const logoW = W * .5;
  drawLogo(ctx, th, L.pad + logoW / 2, H * .09, logoW);
  const size = L.title * 1.15, top = H * .09 + logoHeight(logoW) / 2 + size * 1.25;
  const h = text(ctx, ct(lang, "media.cover"), L.pad, top, {size, color: th.ink, weight: 700, max: W - 2 * L.pad});
  const chipSize = L.body * .8, chipY = H - L.pad - chipSize * 1.75;
  const mapTop = top + h - size * .55 + L.pad * .7;
  const box = {x: 0, y: mapTop, w: W, h: chipY - L.pad * .6 - mapTop};
  drawMap(ctx, th, got().world, box, camFor("world", box));
  chip(ctx, th, ct(lang, "media.swipe"), W - L.pad, chipY, chipSize, {align: "right", bg: th.clear, color: th.bg});
}

/** "What the colours mean": a card per level, its name in the scale, its resolutions and what it sees. */
function legendSlide(f: Frame): void {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H);
  bgFill(f);
  text(ctx, ct(lang, "media.legend_slide"), L.pad, H * .14, {size: L.title, color: th.ink, weight: 700, max: W - 2 * L.pad});
  let y = H * .26;
  for (const l of [1, 2, 3] as Level[]) {
    rrect(ctx, L.pad, y, W - 2 * L.pad, H * .17, 22); ctx.fillStyle = th.surface; ctx.fill();
    rrect(ctx, L.pad + W * .04, y + H * .035, H * .1, H * .1, 14); ctx.fillStyle = levelColour(th, l); ctx.fill();
    const tx = L.pad + W * .04 + H * .13, max = W - tx - L.pad * 1.4;
    text(ctx, levelLabel(l, f), tx, y + H * .07, {size: L.body * 1.35, color: th.ink, weight: 700, max});
    text(ctx, `${levelTag(l, lang)} · ${ct(lang, `level.${l}.desc`)}`, tx, y + H * .115, {size: L.body * .8, font: "b", weight: 500, color: th.ink2, max});
    y += H * .2;
  }
  footer(f, L.small);
}

/** The areas a list names (world.ts `listed`), by level, then by name. */
function listedAreas(f: Frame): string[] {
  return got().world.listed.slice().sort((a, b) => areaOf(a)!.level - areaOf(b)!.level || areaName(a, f.lang).localeCompare(areaName(b, f.lang), f.lang));
}

/** A slide of a view (carousel and Stories): its map, the count or names of its areas, the legend, the footer. */
function slide(view: View) {
  return (f: Frame) => {
    const {ctx, th, W, H, lang} = f;
    const {world} = got(), shown = view === "world" ? [] : world.groups[view].filter(id => world.listed.includes(id));
    const sub = view === "world" ? summaryText(lang)
      : shown.length > 3 ? ct(lang, "count.areas", {count: shown.length})
      : `${ct(lang, "media.areas_named")} ${shown.map(id => areaName(id, lang)).join(", ")}`;
    const title = ct(lang, `zoom.${view}`), box = mapBoxUnder(f, title, sub);
    bgFill(f);
    drawMap(ctx, th, got().world, box, camFor(view, box));
    captionTop(f, title, sub);
    legendAboveFooter(f);
    footer(f, layoutOf(W, H).small);
  };
}

/** The A3 poster: the logo, the title, the world and the three parts with data, the legend and the list. */
function poster(f: Frame): void {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), {world} = got();
  bgFill(f);
  // the logo on its own line, the title under it (it may wrap), the maps in the height that is left
  const logoW = W * .2, inner = W - 2 * L.pad, gap = W * .015;
  drawLogo(ctx, th, L.pad + logoW / 2, H * .035, logoW);
  const tSize = W * .05, tTop = H * .035 + logoHeight(logoW) / 2 + tSize * 1.15;
  const titleH = text(ctx, ct(lang, "media.readme.title"), L.pad, tTop, {size: tSize, color: th.ink, weight: 700, max: inner});
  const mapsTop = tTop + titleH - tSize * .6 + gap * 1.5, mapsBottom = H * .79, mh = mapsBottom - mapsTop;
  const b1 = {x: L.pad, y: mapsTop, w: inner, h: mh * .44};
  drawMap(ctx, th, world, b1, camFor("world", b1), {radius: 18});
  const y2 = mapsTop + mh * .44 + gap, h2 = mapsBottom - y2;
  const b2 = {x: L.pad, y: y2, w: inner * .62, h: h2};
  drawMap(ctx, th, world, b2, camFor("europe", b2), {radius: 18});
  const b3 = {x: L.pad + inner * .62 + gap, y: y2, w: inner * .38 - gap, h: (h2 - gap) / 2};
  drawMap(ctx, th, world, b3, camFor("na", b3), {radius: 14});
  const b4 = {x: b3.x, y: y2 + (h2 + gap) / 2, w: b3.w, h: (h2 - gap) / 2};
  drawMap(ctx, th, world, b4, camFor("oceania", b4), {radius: 14});
  const legSize = W * .02, listTop = mapsBottom + gap * 2.6;
  legend(f, L.pad, listTop, legSize, {title: true});
  const legRight = L.pad + legendWidth(f, legSize, {title: true}) + legSize * 1.5;
  // the list in as many columns as its longest name allows
  const ids = listedAreas(f), labels = ids.map(id => `${areaName(id, lang)} · ${resText(areaOf(id)!.res, lang)}`);
  const footTop = H - W * .012 * 3.2, x0 = Math.max(legRight, W * .36), avail = W - L.pad - x0;
  let fs = W * .0125, cols = 1, rows = labels.length, colW = 0;
  for (;;) {
    ctx.font = font(500, fs, "b");
    colW = Math.max(...labels.map(s => ctx.measureText(s).width)) + fs * 2.6;
    cols = Math.max(1, Math.floor(avail / colW)); rows = Math.ceil(labels.length / cols);
    if (listTop - fs + rows * fs * 1.7 <= footTop || fs < W * .008) break;
    fs *= .94;
  }
  labels.forEach((s, k) => {
    const cx = x0 + Math.floor(k / rows) * colW, cy = listTop - fs * .2 + (k % rows) * fs * 1.7;
    ctx.fillStyle = levelColour(th, areaOf(ids[k])!.level); ctx.fillRect(cx, cy - fs * .75, fs * .75, fs * .75);
    ctx.fillStyle = th.ink2; ctx.fillText(s, cx + fs * 1.2, cy);
  });
  footer(f, W * .012);
}

const README_SIZE = [1600, 800] as const, POST = [1080, 1350] as const, STORY = [1080, 1920] as const;
/** A3 at 300 dpi. */
export const POSTER_SIZE = [3508, 4961] as const;

export const STATICS: StaticImage[] = [
  ...VIEWS.map(v => ({name: `gh-${v}`, width: README_SIZE[0], height: README_SIZE[1], group: "readme" as const, draw: readme(v)})),
  {name: "carousel-1-cover", width: POST[0], height: POST[1], group: "carousel", draw: cover},
  ...VIEWS.map((v, i) => ({name: `carousel-${i + 2}-${v}`, width: POST[0], height: POST[1], group: "carousel" as const, draw: slide(v)})),
  {name: "carousel-6-legend", width: POST[0], height: POST[1], group: "carousel", draw: legendSlide},
  {name: "carousel-7-end", width: POST[0], height: POST[1], group: "carousel", draw: f => sceneEnd(ct(f.lang, "map.credit"))(f, 1)},
  ...VIEWS.map(v => ({name: `story-${v}`, width: STORY[0], height: STORY[1], group: "stories" as const, draw: slide(v)})),
  {name: "poster", width: POSTER_SIZE[0], height: POSTER_SIZE[1], group: "poster", draw: poster},
];

