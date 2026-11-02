// The layouts of the frames (4:5 and 9:16 tall, 2:1 wide: README and its GIF) and the parts they share: the
// title above the map, the legend of the three levels in the chosen scale, the footer with the map's credit
// and the address. Sizes follow the frame (the width of a tall one, the height of a wide one), so every
// frame size draws the same picture.
import { ct, metres, type Lang } from "../i18n";
import { levelColour } from "../palette";
import type { Level } from "../types";
import { font, rrect, text, type Box, type Frame } from "./canvas";
import { hatchFor } from "./map";

/** The address shown on the images. */
export const SITE = "findaline.lukawski.org";

export interface Layout { wide: boolean; pad: number; title: number; body: number; small: number }

export function layoutOf(W: number, H: number): Layout {
  const wide = W / H > 1.2, pad = wide ? W * .04 : W * .07, unit = wide ? H : W;
  return {wide, pad, title: unit * .085, body: unit * .042, small: unit * .026};
}

/** Whether a tall frame is a story (9:16) rather than a post (4:5). */
export const isTall = (f: Frame): boolean => f.H / f.W > 1.5;

/** The map's box: a wide frame keeps a title strip above it, so no caption covers a country. */
export function mapBox(W: number, H: number): Box {
  return layoutOf(W, H).wide ? {x: 0, y: H * .17, w: W, h: H * .83} : {x: 0, y: H * .26, w: W, h: H * (H / W > 1.5 ? .5 : .49)};
}

/** The title and a line under it above the map. */
export function captionTop(f: Frame, title: string, sub: string | null, alpha = 1): void {
  const {ctx, th, W, H} = f, L = layoutOf(W, H);
  ctx.globalAlpha = alpha;
  if (L.wide) {
    text(ctx, title, L.pad, H * .085, {size: H * .07, color: th.ink, weight: 700, max: W - 2 * L.pad});
    if (sub) text(ctx, sub, L.pad, H * .14, {size: H * .032, font: "b", weight: 500, color: th.ink2, max: W - 2 * L.pad});
  } else {
    const y = H * .1, h = text(ctx, title, L.pad, y, {size: L.title, color: th.ink, weight: 700, max: W - 2 * L.pad});
    if (sub) text(ctx, sub, L.pad, y + h * .95 + L.body * .2, {size: L.body, font: "b", weight: 500, color: th.ink2, max: W - 2 * L.pad});
  }
  ctx.globalAlpha = 1;
}

/** The resolutions of a level as the legend tags it: "≤ 1 m", "2–5 m", "30 m". */
export function levelTag(level: Level, lang: Lang): string {
  return level === 1 ? `≤ ${metres(1, lang)}` : level === 2 ? `2–${metres(5, lang)}` : metres(30, lang);
}

/** A level's name in the scale: "Very detailed", "A doormat", "★★★ Best". */
export function levelLabel(level: Level, f: Pick<Frame, "lang" | "scale">): string {
  if (f.scale === "life") return ct(f.lang, `life.${level}`);
  if (f.scale === "stars") return `${"★".repeat(4 - level)} ${ct(f.lang, `stars.${level}`)}`;
  return ct(f.lang, `level.${level}`);
}

export const legendTitle = (f: Pick<Frame, "lang" | "scale">): string =>
  ct(f.lang, f.scale === "life" ? "life.head" : "legend.title").toUpperCase();

export interface LegendOptions { title?: boolean; partial?: boolean; horizontal?: boolean }

const LEVELS: Level[] = [1, 2, 3];

/** The legend's rows (a swatch, the level's name, its resolutions; the hatched "only in parts") from the
 *  first row's baseline y; returns the baseline of its last row. */
export function legend(f: Frame, x: number, y: number, size: number, o: LegendOptions = {}): number {
  const {ctx, th, lang} = f;
  let yy = y, xx = x;
  ctx.textAlign = "left";
  if (o.title !== false) {
    ctx.font = font(500, size * .62, "m"); ctx.fillStyle = th.muted; ctx.fillText(legendTitle(f), x, yy);
    yy += size * .9;
  }
  const rows: [CanvasPattern | string, string, string][] = LEVELS.map(l => [levelColour(th, l), levelLabel(l, f), levelTag(l, lang)]);
  if (o.partial !== false) rows.push([hatchFor(ctx, th, 1, size / 30), ct(lang, "legend.partial"), ""]);
  rows.forEach(([fill, label, tag], i) => {
    rrect(ctx, xx, yy - size * .72, size * 1.3, size * .82, size * .2); ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = th.line; ctx.lineWidth = 1; ctx.stroke();
    ctx.font = font(600, size); ctx.fillStyle = th.ink; ctx.fillText(label, xx + size * 1.7, yy);
    const labelW = ctx.measureText(label).width;
    ctx.font = font(500, size * .62, "m"); ctx.fillStyle = th.muted; ctx.fillText(tag, xx + size * 1.7 + labelW + size * .4, yy);
    const tagW = ctx.measureText(tag).width;
    if (i < rows.length - 1) { if (o.horizontal) xx += size * 2.4 + labelW + tagW + size * 1.2; else yy += size * 1.35; }
  });
  return yy;
}

/** The width of the legend drawn by `legend` (vertical). */
export function legendWidth(f: Frame, size: number, o: LegendOptions = {}): number {
  const {ctx, lang} = f;
  let widest = 0;
  for (const l of LEVELS) {
    ctx.font = font(600, size); const labelW = ctx.measureText(levelLabel(l, f)).width;
    ctx.font = font(500, size * .62, "m"); const tagW = ctx.measureText(levelTag(l, lang)).width;
    widest = Math.max(widest, size * 2.1 + labelW + tagW);
  }
  if (o.partial !== false) { ctx.font = font(600, size); widest = Math.max(widest, size * 1.7 + ctx.measureText(ct(lang, "legend.partial")).width); }
  if (o.title !== false) { ctx.font = font(500, size * .62, "m"); widest = Math.max(widest, ctx.measureText(legendTitle(f)).width); }
  return widest;
}

/** The legend of a tall frame, its last row a gap above the footer's credit line (never over it). */
export function legendAboveFooter(f: Frame, o: LegendOptions = {}): number {
  const L = layoutOf(f.W, f.H), size = L.body * .8, rows = o.partial === false ? 3 : 4;
  const last = f.H - L.small * 2.6 - L.small * 1.4;
  return legend(f, L.pad, last - size * 1.35 * (rows - 1), size, {title: false, ...o});
}

/** The bottom line: the map's credit (or another) on the left, the address on the right. */
export function footer(f: Frame, size: number, credit?: string): void {
  const {ctx, th, W, H, lang} = f;
  ctx.font = font(500, size, "m"); ctx.textBaseline = "alphabetic";
  ctx.fillStyle = th.muted; ctx.textAlign = "left"; ctx.fillText(credit || ct(lang, "map.credit"), W * .06, H - size * 1.6);
  ctx.fillStyle = th.ink2; ctx.textAlign = "right"; ctx.fillText(SITE, W * .94, H - size * 1.6);
  ctx.textAlign = "left";
}

/** The map's credit alone, bottom left (a tall frame) or bottom right (a wide one). */
export function mapCredit(f: Frame): void {
  const {ctx, th, W, H, lang} = f, L = layoutOf(W, H), credit = ct(lang, "map.credit");
  ctx.font = font(500, L.small, "m"); ctx.textAlign = "left";
  const w = ctx.measureText(credit).width, x = L.wide ? W - L.pad - w : L.pad, y = H - L.small * 1.6;
  // a wide frame's map reaches the bottom: the credit gets a plate, so no country runs through it
  if (L.wide) plate(f, x, y, w, L.small);
  ctx.fillStyle = th.muted; ctx.fillText(credit, x, y);
}

/** A plate of the background behind a line of small print standing on y. */
export function plate(f: Frame, x: number, y: number, w: number, size: number): void {
  const {ctx, th} = f;
  rrect(ctx, x - size * .5, y - size * 1.05, w + size, size * 1.5, size * .4);
  ctx.fillStyle = th.bg; ctx.globalAlpha = .88; ctx.fill(); ctx.globalAlpha = 1;
}
