// The canvas primitives of the coverage map's images and animations (the prototypes of stage A): fonts,
// text wrapped to a width, text standing on a line, rounded boxes, chips and the easing of the scenes.
// Everything is drawn in the frame's own pixels (1080 x 1350, ...): the caller scales the context.
import type { Lang } from "../i18n";
import type { Theme } from "../palette";

export type Ctx = CanvasRenderingContext2D;

/** A frame being drawn: its context, colours, size, language and the legend's scale. */
export interface Frame { ctx: Ctx; th: Theme; W: number; H: number; lang: Lang; scale: Scale }

/** The legend's way of naming the levels (the page's switch): words, everyday sizes or stars. */
export type Scale = "words" | "life" | "stars";

export interface Box { x: number; y: number; w: number; h: number }

/** d: the display font (Barlow Condensed, fonts.css), b: body text, m: small print and chips. */
export const FONT = {
  d: '"Barlow Condensed", "Arial Narrow", sans-serif',
  b: 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
  m: 'ui-monospace, "Cascadia Mono", Consolas, monospace',
};

export interface TextStyle {
  size?: number; weight?: number; font?: keyof typeof FONT; color?: string; max?: number;
  lh?: number; align?: CanvasTextAlign;
}

export const font = (weight: number, size: number, face: keyof typeof FONT = "d"): string => `${weight} ${size}px ${FONT[face]}`;

/** The lines of a text wrapped to o.max (sets the context's font); a number keeps its unit on its line. */
export function wrapLines(ctx: Ctx, s: string, o: TextStyle = {}): string[] {
  const max = o.max || 1e9;
  ctx.font = font(o.weight || 600, o.size || 40, o.font || "d");
  const words = String(s).replace(/(\d) (m\b|°|%)/g, "$1\u00a0$2").split(" "), lines: string[] = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > max && line) { lines.push(line); line = word; } else line = next;
  }
  lines.push(line);
  return lines;
}

/** A wrapped text whose first line stands on y; returns its height (lines x size x line height). */
export function text(ctx: Ctx, s: string, x: number, y: number, o: TextStyle = {}): number {
  const size = o.size || 40, lh = o.lh || 1.15, lines = wrapLines(ctx, s, o);
  ctx.fillStyle = o.color || "#000"; ctx.textAlign = o.align || "left"; ctx.textBaseline = "alphabetic";
  lines.forEach((line, i) => ctx.fillText(line, x, y + i * size * lh));
  return lines.length * size * lh;
}

/** A wrapped text whose last line stands on `bottom`; returns the top of its first line. */
export function textBottom(ctx: Ctx, s: string, x: number, bottom: number, o: TextStyle = {}): number {
  const size = o.size || 40, lh = o.lh || 1.15, y = bottom - (wrapLines(ctx, s, o).length - 1) * size * lh;
  text(ctx, s, x, y, o);
  return y - size;
}

export function rrect(ctx: Ctx, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r);
}

export interface ChipStyle { dot?: string; bg?: string; color?: string; align?: "left" | "center" | "right" }

/** A rounded label at (x, y) (its top edge; x by o.align), with an optional coloured dot; returns its width. */
export function chip(ctx: Ctx, th: Theme, s: string, x: number, y: number, size: number, o: ChipStyle = {}): number {
  ctx.font = font(500, size, "m");
  const w = ctx.measureText(s).width + size * (o.dot ? 2.1 : 1.2), h = size * 1.75;
  const bx = o.align === "center" ? x - w / 2 : o.align === "right" ? x - w : x;
  rrect(ctx, bx, y, w, h, h / 2); ctx.fillStyle = o.bg || th.surface; ctx.fill();
  if (o.dot) { ctx.beginPath(); ctx.arc(bx + size * .95, y + h / 2, size * .3, 0, 7); ctx.fillStyle = o.dot; ctx.fill(); }
  ctx.fillStyle = o.color || th.ink; ctx.textBaseline = "middle"; ctx.textAlign = "left";
  ctx.fillText(s, bx + size * (o.dot ? 1.5 : .6), y + h / 2 + 1);
  ctx.textBaseline = "alphabetic";
  return w;
}

export function bgFill(f: Frame): void { f.ctx.fillStyle = f.th.bg; f.ctx.fillRect(0, 0, f.W, f.H); }

export const ease = (t: number): number => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const clamp = (v: number, a = 0, b = 1): number => Math.max(a, Math.min(b, v));
/** How far p is through [a, b], 0..1. */
export const seg = (p: number, a: number, b: number): number => clamp((p - a) / (b - a));

/** Numbers as the language writes them ("1,730", "1 730"). */
export const numberText = (n: number, lang: Lang): string => new Intl.NumberFormat(lang === "pl" ? "pl-PL" : "en-GB").format(n);
