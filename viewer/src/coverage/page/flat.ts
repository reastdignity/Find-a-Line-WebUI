// The flat view (the default): an SVG world in the Equal Earth projection (d3-geo), zoomed and panned with
// d3-zoom; the areas coloured by classes of page.css (the palette's --cov-* properties), so a theme change
// needs no drawing. Partial areas are hatched, small covered areas get a dot.
import { geoEqualEarth, geoGraticule10, geoPath } from "d3-geo";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { BOXES, keyOf, levelOfKey, partialOfKey, type BoxName } from "./geo";
import { tween, type MapView, type ViewContext } from "./view";

const MAX_K = 24;

/** The class of an area's fill. */
export const fillClass = (key: string): string =>
  partialOfKey(key) ? `cov-hf${levelOfKey(key)}` : `cov-f${levelOfKey(key)}`;

export function mountFlat(el: HTMLElement, ctx: ViewContext): MapView {
  const W = el.clientWidth || 600, H = el.clientHeight || 400;
  const svg = select(el).append("svg").attr("class", "cov-svg").attr("viewBox", `0 0 ${W} ${H}`).attr("aria-hidden", "true");
  const defs = svg.append("defs");
  const patterns = [1, 2].map(level => {
    const pattern = defs.append("pattern").attr("id", `cov-hatch${level}`).attr("patternUnits", "userSpaceOnUse")
      .attr("width", 6).attr("height", 6).attr("patternTransform", "rotate(45)");
    pattern.append("rect").attr("width", 6).attr("height", 6).attr("class", "cov-f3");
    pattern.append("rect").attr("width", 3).attr("height", 6).attr("class", `cov-f${level}`);
    return pattern;
  });
  const projection = geoEqualEarth().rotate([-10, 0]).fitExtent([[8, 8], [W - 8, H - 8]], {type: "Sphere"});
  const path = geoPath(projection);
  const g = svg.append("g");
  g.append("path").attr("class", "cov-sphere").attr("d", path({type: "Sphere"}));
  g.append("path").attr("class", "cov-grat").attr("d", path(geoGraticule10()));
  g.selectAll("path.cov-shape").data(ctx.geo.features).join("path")
    .attr("class", d => `cov-shape ${fillClass(keyOf(d))}`).attr("data-key", d => keyOf(d)).attr("d", d => path(d) || "");
  const dots = g.selectAll("circle.cov-dot").data(ctx.geo.dots).join("circle")
    .attr("class", d => `cov-dot cov-shape cov-f${levelOfKey(d.key)}`).attr("data-key", d => d.key)
    .attr("cx", d => projection(d.lonlat)![0]).attr("cy", d => projection(d.lonlat)![1]).attr("r", 3.5);

  const tip = document.createElement("div");
  tip.className = "cov-tip";
  tip.hidden = true;
  el.append(tip);
  const keyOfTarget = (target: EventTarget | null) => (target as Element | null)?.closest?.("[data-key]")?.getAttribute("data-key") || null;
  const node = svg.node()!;
  node.addEventListener("click", e => { const key = keyOfTarget(e.target); if (key) ctx.select(key); });
  node.addEventListener("pointermove", e => {
    const key = keyOfTarget(e.target);
    if (!key || e.pointerType === "touch") { tip.hidden = true; return; }
    const box = el.getBoundingClientRect();
    tip.hidden = false;
    tip.textContent = ctx.label(key);
    tip.style.left = `${e.clientX - box.left}px`;
    tip.style.top = `${e.clientY - box.top}px`;
  });
  node.addEventListener("pointerleave", () => { tip.hidden = true; });

  const behaviour = zoom<SVGSVGElement, unknown>().scaleExtent([1, MAX_K])
    .translateExtent([[-W * 0.2, -H * 0.2], [W * 1.2, H * 1.2]])
    .on("zoom", e => {
      g.attr("transform", e.transform.toString());
      dots.attr("r", 3.5 / Math.sqrt(e.transform.k));
      // the hatch keeps its width on the screen
      for (const pattern of patterns) pattern.attr("patternTransform", `rotate(45) scale(${1 / e.transform.k})`);
      tip.hidden = true;
    });
  let current: ZoomTransform = zoomIdentity;
  behaviour.on("zoom.current", e => { current = e.transform; });
  svg.call(behaviour);
  let stop = () => {};

  /** The transform that shows a box, its centre in the middle. */
  function fit(name: BoxName): ZoomTransform {
    if (name === "world") return zoomIdentity;
    const [[w, s], [e, n]] = BOXES[name];
    const ring = [[w, s], [w, n], [e, n], [e, s], [w, s]];
    const [[x0, y0], [x1, y1]] = path.bounds({type: "Polygon", coordinates: [ring]});
    const k = Math.min(MAX_K, 0.9 / Math.max((x1 - x0) / W, (y1 - y0) / H));
    return zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
  }

  function update() {
    const chosen = ctx.selected();
    g.selectAll<SVGElement, unknown>(".cov-shape").classed("cov-sel", function () { return this.getAttribute("data-key") === chosen; });
    g.selectAll(".cov-sel").raise();
  }
  update();
  // a tall narrow box (a phone) leaves the world a thin strip: start closer, on the Atlantic
  const [[, wy0], [, wy1]] = path.bounds({type: "Sphere"});
  if (wy1 - wy0 < H * 0.6) {
    const k = Math.min(MAX_K, (H * 0.85) / (wy1 - wy0)), [cx, cy] = projection([-35, 12])!;
    svg.call(behaviour.transform, zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k));
  }

  return {
    zoomTo(name) {
      stop();
      const from = current, to = fit(name);
      // the centre of the view moves straight, the scale geometrically
      const c0 = [(W / 2 - from.x) / from.k, (H / 2 - from.y) / from.k], c1 = [(W / 2 - to.x) / to.k, (H / 2 - to.y) / to.k];
      stop = tween(700, ctx.reducedMotion(), p => {
        const k = Math.exp(Math.log(from.k) + (Math.log(to.k) - Math.log(from.k)) * p);
        const cx = c0[0] + (c1[0] - c0[0]) * p, cy = c0[1] + (c1[1] - c0[1]) * p;
        svg.call(behaviour.transform, zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k));
      });
    },
    update,
    destroy() { stop(); svg.on(".zoom", null); el.replaceChildren(); },
  };
}
