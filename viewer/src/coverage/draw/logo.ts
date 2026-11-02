// The wordmark (ui/logo/logo.svg, the same file as the app's) drawn on a canvas: its paths read once, coloured
// by their classes as ui.css colours them (u-li ink fill, u-ls ink stroke, u-ll and u-lf the line's colour).
import logoSvg from "../../ui/logo/logo.svg";
import type { Theme } from "../palette";
import type { Ctx } from "./canvas";

interface Part { path: Path2D; cls: string; width: number }

let parts: Part[] | null = null;
let viewBox: number[] = [0, 0, 1, 1];

function read(): Part[] {
  const doc = new DOMParser().parseFromString(logoSvg, "image/svg+xml"), svg = doc.documentElement;
  viewBox = (svg.getAttribute("viewBox") || "0 0 1 1").trim().split(/[\s,]+/).map(Number);
  const out: Part[] = [];
  for (const el of Array.from(svg.querySelectorAll("path, circle"))) {
    let path: Path2D;
    if (el.tagName === "circle") {
      path = new Path2D();
      path.arc(+el.getAttribute("cx")!, +el.getAttribute("cy")!, +el.getAttribute("r")!, 0, 2 * Math.PI);
    } else path = new Path2D(el.getAttribute("d") || "");
    out.push({path, cls: el.getAttribute("class") || "", width: +(el.getAttribute("stroke-width") || 0)});
  }
  return out;
}

/** The logo's height for a width (its viewBox's ratio). */
export function logoHeight(width: number): number {
  if (!parts) parts = read();
  return width * viewBox[3] / viewBox[2];
}

/** The wordmark centred on (cx, cy), `width` wide. */
export function drawLogo(ctx: Ctx, th: Theme, cx: number, cy: number, width: number): void {
  if (!parts) parts = read();
  const [x0, y0, w, h] = viewBox, s = width / w;
  ctx.save();
  ctx.translate(cx - width / 2 - x0 * s, cy - h * s / 2 - y0 * s); ctx.scale(s, s);
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const {path, cls, width: lw} of parts) {
    if (cls === "u-li") { ctx.fillStyle = th.ink; ctx.fill(path); }
    else if (cls === "u-lf") { ctx.fillStyle = th.clear; ctx.fill(path); }
    else { ctx.strokeStyle = cls === "u-ll" ? th.clear : th.ink; ctx.lineWidth = lw; ctx.stroke(path); }
  }
  ctx.restore();
}
