// The scenes of the stories (the prototypes of stage A): each draws one frame at p, 0..1 through the scene.
// Data from coverage.json (data.ts), the outlines and the contrast (assets.ts); texts from the coverage
// catalogue (i18n.ts); colours from palette.ts.
import { areaOf, COVERAGE, timeline } from "../data";
import { camFor, drawMap, lerpCam } from "../draw/map";
import { areaName, ct, metres, resText, type Lang } from "../i18n";
import { levelColour } from "../palette";
import { bgFill, chip, clamp, ease, font, numberText, rrect, seg, text, textBottom, wrapLines, type Frame, type TextStyle } from "../draw/canvas";
import { drawLogo, logoHeight } from "../draw/logo";
import { captionTop, isTall, layoutOf, legendAboveFooter, mapBox, mapBoxUnder, mapCredit, SITE } from "../draw/layout";
import { GROUPS, type View } from "../draw/world";
import { got } from "./assets";

export type Scene = (f: Frame, p: number) => void;

/** How long a story is: short, medium, long (its scenes: stories.ts). */
export type Depth = 0 | 1 | 2;

/** The places of the contrast in contrast.json's order. */
export const places = (): string[] => Object.keys(got().contrast.places);

/** Up to two other places with many 1 m spots, for the longer stories. */
export const otherPlaces = (place: string): string[] =>
  places().filter(k => k !== place && got().contrast.places[k].fine.spots > 100).slice(0, 2);

/** The credit of a place's 1 m data: "Data: © swisstopo · swisstopo OGD terms ...". */
export function placeCredit(place: string, lang: Lang): string {
  const c = got().contrast.places[place]?.fine.credits[0];
  if (!c) return "";
  // the year of the searches is in the credits (tools/coverage_contrast.py); the licence once, when the
  // provider's attribution does not name it already ("©Kartverket, CC BY 4.0, processed"); without our
  // "Data:" when the attribution starts with a label of its own ("Source: …", "Quelle: …")
  const named = c.attribution.includes(c.licence);
  if (/^\p{L}+:\s/u.test(c.attribution)) return named ? c.attribution : `${c.attribution} · ${c.licence}`;
  return ct(lang, named ? "media.data_credit_short" : "media.data_credit", {attribution: c.attribution, licence: c.licence});
}

/** A title card: the title, a line under it and the logo's line drawn across above it. */
export function sceneTitle(title: string, sub: string | null): Scene {
  return (f, p) => {
    const {ctx, th, W, H} = f, L = layoutOf(W, H);
    bgFill(f);
    const a = ease(seg(p, 0, .35));
    ctx.globalAlpha = a;
    const y0 = H * (L.wide ? .42 : .4) + (1 - a) * 30;
    const h = text(ctx, title, L.pad, y0, {size: L.title * 1.25, color: th.ink, max: W - 2 * L.pad, weight: 700});
    if (sub) text(ctx, sub, L.pad, y0 + h + L.body * .6, {size: L.body, font: "b", weight: 500, color: th.ink2, max: W - 2 * L.pad});
    ctx.strokeStyle = th.clear; ctx.lineWidth = Math.max(3, W / 300); ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(L.pad, y0 - L.title * 1.6);
    ctx.lineTo(L.pad + (W - 2 * L.pad) * ease(seg(p, .1, .6)), y0 - L.title * 1.6); ctx.stroke();
    ctx.globalAlpha = 1;
  };
}

/** A hillshade, tinted to the theme. */
function drawShade(f: Frame, img: HTMLImageElement | undefined, x: number, y: number, s: number): void {
  const {ctx, th} = f;
  if (!img) { ctx.fillStyle = th.surface2; ctx.fillRect(x, y, s, s); return; }
  ctx.drawImage(img, x, y, s, s);
  ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.fillStyle = th.tint; ctx.fillRect(x, y, s, s); ctx.restore();
}

/** The same rock at 30 m, then wiped to 1 m, its spots' lines drawn in and the count running up. */
export function sceneContrast(place: string): Scene {
  return (f, p) => {
    const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), d = got().contrast.places[place];
    bgFill(f);
    if (!d) return;
    const wipe = ease(seg(p, .32, .58)), fine = wipe > .5;
    // tall frames from the bottom up: the credit (room for the longer of its two texts), the count, then the
    // image in the height left under the place's name
    const credit: TextStyle = {size: L.small, font: "m", weight: 500, color: th.muted, max: W - 2 * L.pad, lh: 1.3};
    const creditBottom = H - L.small * 1.3;
    const creditLines = Math.max(wrapLines(ctx, placeCredit(place, lang), credit).length, wrapLines(ctx, sameData(lang), credit).length);
    const creditTop = creditBottom - (creditLines - 1) * L.small * 1.3 - L.small;
    let labelY = creditTop - L.small * 1.8, numberY = labelY - L.body * 1.45;
    const numberTop = numberY - L.title * 1.7 * .75;
    let placeY = H * (isTall(f) ? .1 : .085);
    // the place's name may wrap: the image starts under its last line
    const nameStyle: TextStyle = {size: L.body * 1.1, font: "b", weight: 600, color: th.ink2};
    const nameMax = W - 2 * L.pad;
    const nameLines = L.wide ? 1 : wrapLines(ctx, ct(lang, `place.${place}`), {...nameStyle, max: nameMax}).length;
    let y = L.wide ? 0 : placeY + L.body * .9 + (nameLines - 1) * L.body * 1.1 * 1.15;
    const s = L.wide ? H * .74 : Math.min(W * .86, numberTop - L.pad * .5 - y);
    // a tall frame has height to spare when the image is as wide as it may be: half of it above the image,
    // half between the count and the credit, so the image and its count stay together
    const spare = L.wide ? 0 : numberTop - L.pad * .5 - y - s;
    if (spare > 0) { placeY += spare / 2; y += spare / 2; numberY -= spare / 2; labelY -= spare / 2; }
    const x = L.wide ? W - L.pad - s : (W - s) / 2, top = L.wide ? (H - s) / 2 : y;
    ctx.save(); rrect(ctx, x, top, s, s, s * .04); ctx.clip();
    drawShade(f, got().images.get(`${place}-coarse`), x, top, s);
    if (wipe > 0) {
      ctx.save(); ctx.beginPath(); ctx.rect(x, top, s * wipe, s); ctx.clip();
      drawShade(f, got().images.get(`${place}-fine`), x, top, s); ctx.restore();
    }
    const lp = ease(seg(p, .58, .92));
    if (lp > 0) {
      ctx.lineCap = "round";
      const segments = d.fine.segments, n = Math.ceil(segments.length * lp);
      for (let i = 0; i < n; i++) {
        const [x1, y1, x2, y2, over] = segments[i];
        ctx.beginPath(); ctx.moveTo(x + x1 * s, top + y1 * s); ctx.lineTo(x + x2 * s, top + y2 * s);
        ctx.strokeStyle = "rgba(0,0,0,.45)"; ctx.lineWidth = s / 160; ctx.stroke();
        ctx.strokeStyle = over ? th.trees : th.lineMap; ctx.lineWidth = s / 260; ctx.stroke();
      }
    }
    if (wipe > 0 && wipe < 1) { ctx.fillStyle = th.clear; ctx.fillRect(x + s * wipe - 2, top, 4, s); }
    ctx.restore();
    const chipSize = L.wide ? H * .032 : W * .03;
    const sideText = fine ? ct(lang, "media.fine", {res: metres(d.fine.res, lang)}) : ct(lang, "media.coarse", {res: metres(d.coarse.res, lang)});
    chip(ctx, th, sideText, x + s * .04, top + s * .04, chipSize, {dot: fine ? th.l1 : th.land});
    const tx = L.pad, ty = L.wide ? H * .22 : placeY;
    text(ctx, ct(lang, `place.${place}`), tx, ty, {...nameStyle, max: L.wide ? W - s - 3 * L.pad : nameMax});
    const coarseN = d.coarse.spots, fineN = d.fine.spots;
    const n = p < .58 ? coarseN : Math.round(coarseN + (fineN - coarseN) * ease(seg(p, .58, .9)));
    const ny = L.wide ? H * .55 : numberY;
    ctx.font = font(700, L.title * 1.7); ctx.fillStyle = fine ? th.clear : th.ink; ctx.textAlign = L.wide ? "left" : "center";
    ctx.fillText(numberText(n, lang), L.wide ? tx : W / 2, ny);
    ctx.font = font(500, L.body, "b"); ctx.fillStyle = th.ink2;
    ctx.fillText(ct(lang, "media.found", {count: n}), L.wide ? tx : W / 2, L.wide ? ny + L.body * 1.4 : labelY);
    ctx.textAlign = "left";
    textBottom(ctx, fine ? placeCredit(place, lang) : sameData(lang), L.pad, creditBottom, credit);
  };
}

const degrees = (value: number, lang: Lang): string =>
  `${new Intl.NumberFormat(lang, {maximumFractionDigits: 1}).format(value)}°`;

/** "30 m view: the same data averaged to 30 m; anchors from 40.5°". */
function sameData(lang: Lang): string {
  const c = got().contrast, coarse = Object.values(c.places)[0]?.coarse.res ?? 30;
  return ct(lang, "media.same_data", {res: metres(coarse, lang), threshold: degrees(c.threshold, lang)});
}

/** "4 in 10": a share as a small fraction people read at once (out of 10, or 1 in n). */
function shareText(share: number, lang: Lang): string {
  const word = ct(lang, "media.verify.in");
  return share >= .15 ? `${Math.round(share * 10)} ${word} 10` : `1 ${word} ${Math.round(1 / share)}`;
}

/** The board "Is 30 m enough?": the 1 m spots found at 30 m and the 30 m spots not there, as dots of ten. */
export const sceneVerify: Scene = (f, p) => {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), c = got().contrast, v = c.verify;
  bgFill(f);
  const found = v.fine_found / v.fine_spots, falseShare = (v.coarse_spots - v.coarse_real) / v.coarse_spots;
  const tall = isTall(f);
  text(ctx, ct(lang, "media.verify.title"), L.pad, H * (tall ? .16 : .13), {size: L.title * 1.1, color: th.ink, weight: 700, max: W - 2 * L.pad});
  const rows: [number, string, string, number][] = [
    [found, ct(lang, "media.verify.found"), th.l1, .25], [falseShare, ct(lang, "media.verify.false"), th.trees, .55]];
  rows.forEach(([share, label, colour, at], i) => {
    const a = ease(seg(p, at - .1, at + .15));
    if (a <= 0) return;
    ctx.globalAlpha = a;
    const y = H * (tall ? .3 + i * .25 : .28 + i * .29);
    ctx.font = font(700, L.title * 1.5); ctx.fillStyle = th.ink; ctx.textAlign = "left";
    ctx.fillText(shareText(share, lang), L.pad, y + L.title * 1.2);
    const h = text(ctx, label, L.pad, y + L.title * 1.2 + L.body * 1.4, {size: L.body, font: "b", weight: 500, color: th.ink2, max: W - 2 * L.pad});
    // ten dots, the share filled: under the label however many lines it took
    const n = 10, fill = Math.round(share * 10), r = Math.min(W * .03, (W - 2 * L.pad) / (n * 2.6));
    const dy = y + L.title * 1.2 + L.body * 1.4 + h - L.body * 1.15 + L.body * (tall ? 2.8 : 2.2);
    for (let k = 0; k < n; k++) {
      const on = k < fill && seg(p, at, at + .3) * n > k;
      ctx.beginPath(); ctx.arc(L.pad + r + k * r * 2.6, dy, r, 0, 7);
      if (on) { ctx.fillStyle = colour; ctx.fill(); } else { ctx.strokeStyle = th.line; ctx.lineWidth = r * .25; ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
  });
  const note = ct(lang, "media.verify.note", {
    places: v.places, spots: numberText(v.fine_spots, lang), radius: metres(c.match_radius, lang),
    threshold: degrees(c.threshold, lang), res: metres(Object.values(c.places)[0]?.coarse.res ?? 30, lang),
  });
  // the note stands on the frame's bottom margin
  textBottom(ctx, note, L.pad, H - L.small * 2.2, {size: L.small * 1.1, font: "b", weight: 500, color: th.muted, max: W - 2 * L.pad, lh: 1.35});
};

/** The end card: the logo, the call to action and the address. */
export function sceneEnd(credit: string | null): Scene {
  return (f, p) => {
    const {ctx, th, W, H, lang} = f, L = layoutOf(W, H);
    bgFill(f);
    ctx.globalAlpha = ease(seg(p, 0, .3));
    const lw = Math.min(W * .62, H * .9), ly = H * .4;
    drawLogo(ctx, th, W / 2, ly, lw);
    // the call to action may wrap (Polish): the address goes under its last line
    const ctaY = ly + logoHeight(lw) + L.title * .9;
    const h = text(ctx, ct(lang, "media.cta"), W / 2, ctaY, {size: L.title, color: th.ink, align: "center", weight: 700, max: W * .86});
    chip(ctx, th, SITE, W / 2, ctaY + h - L.title * .75 + L.body * .4, L.body * .9, {align: "center", bg: th.clear, color: th.bg});
    ctx.textAlign = "left";
    if (credit) {
      textBottom(ctx, credit, W / 2, H - L.small * 1.3, {size: L.small, font: "m", weight: 500, color: th.muted, align: "center", max: W - 2 * L.pad, lh: 1.3});
      ctx.textAlign = "left";
    }
    ctx.globalAlpha = 1;
  };
}

/** The name of an area with its resolutions, for a chip: "Norway · 1 m". */
const areaChip = (id: string, lang: Lang): string => `${areaName(id, lang)} · ${resText(areaOf(id)!.res, lang)}`;

/** Areas a caption names: those `listed` (world.ts) and not drawn as dots (islands and microstates are
 *  coloured, but not named: "U.S. Virgin Islands" says little in a tour). */
const named = (ids: string[]): string[] => {
  const {listed, small} = got().world;
  return ids.filter(id => listed.includes(id) && !small.includes(id));
};

/** The tour's camera keyframes (p, view) over the parts of the world with data. */
function tourPlan(depth: Depth): [number, View][] {
  if (depth === 0) return [[0, "world"], [.18, "europe"], [.62, "europe"], [.82, "world"], [1, "world"]];
  return [[0, "world"], [.1, "europe"], [.4, "europe"], [.5, "na"], [.68, "na"], [.76, "oceania"], [.86, "oceania"], [.94, "world"], [1, "world"]];
}

/** When each area's colour comes in: Europe's while the camera is there, then North America's and
 *  Oceania's (together at the end of a short tour), areas elsewhere with the last look at the world. */
function revealSchedule(depth: Depth): Map<string, number> {
  const {groups} = got().world, at = new Map<string, number>();
  const put = (ids: string[], a: number, b: number) => ids.forEach((id, i) => at.set(id, a + (b - a) * i / Math.max(1, ids.length)));
  if (depth === 0) { put(groups.europe, .2, .6); put([...groups.na, ...groups.oceania], .82, .9); }
  else { put(groups.europe, .12, .38); put(groups.na, .52, .66); put(groups.oceania, .78, .84); }
  const grouped = new Set(GROUPS.flatMap(g => groups[g]));
  put(Object.keys(COVERAGE.areas).filter(id => !grouped.has(id)), .9, .94);
  return at;
}

/** The fill: the world at 30 m, the camera flying over the parts with data while their areas light up. */
export function sceneTour(depth: Depth): Scene {
  return (f, p) => {
    const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), plan = tourPlan(depth), at = revealSchedule(depth);
    const title = ct(lang, "media.fill.title"), sub = ct(lang, "media.world30"), box = mapBoxUnder(f, title, sub);
    let i = 0;
    while (i < plan.length - 2 && p > plan[i + 1][0]) i++;
    const [p0, a] = plan[i], [p1, b] = plan[i + 1];
    const cam = lerpCam(camFor(a, box), camFor(b, box), ease(seg(p, p0, p1)));
    bgFill(f);
    drawMap(ctx, th, got().world, box, cam, {reveal: id => { const t0 = at.get(id); return t0 === undefined ? 0 : ease(seg(p, t0, t0 + .05)); }});
    captionTop(f, title, sub);
    // the newest area's name
    let newest: string | null = null, since = -1;
    const candidates = new Set(named([...at.keys()]));
    for (const [id, t0] of at) if (p >= t0 && t0 > since && candidates.has(id)) { since = t0; newest = id; }
    if (newest && p - since < .06 + (depth === 0 ? .1 : 0)) {
      const y = L.wide ? H - L.pad * 1.4 - L.body * 1.9 : box.y + box.h - L.body * .85 * 2.6;
      chip(ctx, th, areaChip(newest, lang), L.wide ? L.pad : W / 2, y, L.body * .85,
        {align: L.wide ? "left" : "center", dot: levelColour(th, areaOf(newest)!.level)});
    }
    if (!L.wide) legendAboveFooter(f);
    mapCredit(f);
  };
}

/** "Detailed data in 20 countries" (counted in coverage.json). */
export const summaryText = (lang: Lang): string => ct(lang, "count.countries", {count: COVERAGE.countries});

/** The whole map with the count of countries. */
export const sceneSummary: Scene = (f, p) => {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), title = summaryText(lang), sub = ct(lang, "legend.rest");
  const box = mapBoxUnder(f, title, sub);
  bgFill(f);
  drawMap(ctx, th, got().world, box, camFor("world", box));
  captionTop(f, title, sub, ease(seg(p, 0, .3)));
  if (!L.wide) legendAboveFooter(f);
  mapCredit(f);
};

/** The view a timeline step needs: Europe while every area so far is there, else the world. */
function stepView(steps: {ids: string[]}[], step: number): View {
  const europe = new Set(got().world.groups.europe);
  return steps.slice(0, step + 1).every(s => s.ids.every(id => europe.has(id))) ? "europe" : "world";
}

/** How the map grew: the dates the sources went live (coverage.json `added`), each step's areas lit up. */
export function sceneTimeline(depth: Depth): Scene {
  return (f, p) => {
    const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), box = mapBox(W, H), steps = timeline();
    const n = steps.length, step = Math.min(n - 1, Math.floor(p * n * 1.05)), local = p * n * 1.05 - step;
    const shown = new Map<string, number>();
    steps.forEach((s, i) => s.ids.forEach(id => shown.set(id, i)));
    const reveal = (id: string) => { const i = shown.get(id); return i === undefined || i > step ? 0 : i < step ? 1 : ease(clamp(local * 2.5)); };
    const cam = depth === 0 ? camFor("world", box)
      : lerpCam(camFor(stepView(steps, Math.max(0, step - 1)), box), camFor(stepView(steps, step), box), ease(clamp(local * 2)));
    bgFill(f);
    drawMap(ctx, th, got().world, box, cam, {reveal});
    const date = new Intl.DateTimeFormat(lang === "pl" ? "pl-PL" : "en-GB", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"})
      .format(new Date(`${steps[step].date}T00:00:00Z`));
    captionTop(f, ct(lang, "media.timeline.title"), null);
    // the dot stays with the name before it, so no line starts with one
    const ids = named(steps[step].ids);
    const names = steps[step].ids.length ? ids.map(id => areaName(id, lang)).join("\u00a0· ") : ct(lang, "media.timeline.start");
    ctx.font = font(700, L.title * 1.15); ctx.fillStyle = th.clear; ctx.textAlign = "left";
    if (L.wide) {
      ctx.fillText(date, L.pad, H - L.pad * 1.2);
      text(ctx, names, L.pad, H - L.pad * 1.2 + L.body * 1.6, {size: L.body * .85, font: "b", weight: 500, color: th.ink2, max: W * .6});
    } else {
      // tall: the date under the title, the names between the map and the credit, smaller when there are many
      ctx.fillText(date, L.pad, H * .1 + L.title * 1.3);
      const top = box.y + box.h + L.body * 1.5, bottom = H - L.small * 3.4;
      let size = L.body * .9;
      while (size > L.body * .5 && wrapLines(ctx, names, {size, font: "b", weight: 500, max: W - 2 * L.pad}).length * size * 1.2 > bottom - top + size) size *= .93;
      text(ctx, names, L.pad, top, {size, font: "b", weight: 500, color: th.ink2, max: W - 2 * L.pad, lh: 1.2});
    }
    mapCredit(f);
  };
}
