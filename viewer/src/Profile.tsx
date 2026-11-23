// Terrain profile of the selected line (ProfileDock, docked at the bottom of the result):
// terrain, trees/buildings, water, the safety limit of the search, the sag
// estimator (webbing, envelope, fall zone, athlete under the cursor). The same panel shows
// two points measured on the map, with their anchors at a height above the ground. Compact (a card that
// can be made low: ProfileCard): no head row (its title goes to the caller's bar, `onTitle`), the legend
// and the 1:1 scale with the controls of "Rigging and layers", the readout wrapping in a box of steady height (the
// room of the longest text it can show: readoutRoom).
// A run with a no-fall zone or A-frames (helpers.end_zone_rule): the anchors on A-frames of the run's height (the
// webbing, the sag and the limit start from their tops), the zone as shaded bands at both ends with the limit
// stepping up inside them (endzone.ts limits), and what the line needs rigged above the chart. The labels are placed
// by labels.ts so that none overlaps another (profilechart.ts).

import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { riggingNeed, limits, shortMetres, zoneMetres, type LimitRule } from "./endzone";
import { t } from "./i18n";
import { estimateWidth, textWidth, type PlacedLabel } from "./labels";
import { chartFrame, chartLabels, frameLeg, MARGIN as M, type ChartMarks, type MarkerMark } from "./profilechart";
import * as Sag from "./sag";
import { clearanceText } from "./tight";
import { Icon } from "./ui/icons";
import { COLORS } from "./style";
import type { Line, Rigging } from "./types";

export const PROFILE = {terrain: "#8a7656", terrainFill: "#e3d8c3", trees: "#3f8f35",
                        treesFill: "rgba(76,153,60,0.45)", limit: "#d62728", envelope: "#6a3d9a",
                        fallFill: "rgba(214,39,40,0.12)", athlete: "#222", water: "#2f6fc0",
                        waterFill: "rgba(47,111,192,0.45)", zone: "#2350c8", zoneFill: "rgba(35,80,200,0.11)",
                        frame: "#3c4e52"};
// a rigging field's step and its label's key (ui.profile.rig.<name>: the unit first, after the number field)
const RIGGING: [keyof Rigging, number][] = [
  ["pretension", 0.1], ["stretch", 0.5], ["webbing_weight", 5], ["athlete_mass", 5], ["fall_zone", 0.5]];
type LayerName = "webbing" | "athlete" | "envelope" | "fall";
const LAYERS: [LayerName, string][] = [
  ["webbing", "height:3px;background:" + COLORS.clean],
  ["athlete", "height:2px;background:" + PROFILE.athlete],
  ["envelope", "border-top:2px dotted " + PROFILE.envelope + ";height:0"],
  ["fall", "height:8px;background:" + PROFILE.fallFill + ";border:1px solid " + PROFILE.limit]];
// The chart's height: fixed, or in fill mode its box's (a card the user resizes), at least CHART_MIN
const HEIGHT = 170, CHART_MIN = 120;
// The chart's text, px (R1's smallest: the user's "12 a", 11 before), and its labels' boxes for labels.ts' layout at
// that size: the glyphs' cells (measured in Edge on Windows: 13 px above the baseline, 3 below), 2 px kept free around
// each (they stood on touching lines on the narrow card: the UX task's P1)
const TEXT_PX = 12, LABEL_BOXES = {ascent: 13, descent: 3, pad: 2};

function Swatch({style, class: cls}: {style?: string; class?: string}) {
  return <span class={"fal-swatch" + (cls ? " " + cls : "")} style={style}></span>;
}

function niceStep(span: number, count: number): number {
  const raw = span / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const step of [1, 2, 5, 10]) if (step * mag >= raw) return step * mag;
  return 10 * mag;
}

export interface ProfileProps {
  line: Line;
  model: "formula" | "sag";
  slope: number;
  leashFall: number;
  rigging: Rigging;                      // initial values (the run's)
  /** The run's no-fall zone at the ends and A-frame height, metres (the head's "end_zone", "lift"; the patch meta's);
   *  none: off (a run without them, or before them). */
  endZone?: number;
  lift?: number;
  measured?: boolean;                    // two points measured on the map, not a found line
  fill?: boolean;                        // the chart takes its box's height (at least 120 px) instead of 170 px
  compact?: boolean;                     // no head row: the legend and the scale with the controls, a steady readout
  needBelow?: boolean;                   // the need row ("no A-frame needed" ...) under the chart, not above it
  onTitle?(title: string, facts: string): void;  // the title (as the head has it) and its facts after the length
  onClose(): void;
  onHover(at: [number, number] | null): void;   // (lat, lon) under the cursor
  /** An outside cursor (the 3D view's walker): the distance from A1 shown while the chart is not pointed at. */
  cursorAt?: number | null;
  /** The distance from A1 under the chart's own cursor, with the line's length (null: it left the chart). */
  onCursor?(distance: number | null, length: number): void;
}

export function ProfilePanel(props: ProfileProps) {
  const {model, measured, fill, compact} = props;
  const p = props.line.prof!;
  // The run's A-frames: a found line stands on them (its profile's own height when it was made with the rule); a
  // measured line's ends are the fields "m above ground", which start at the run's height
  const runLift = props.lift || 0;
  const lift = measured ? 0 : (p.lift ?? runLift);
  const [rigging, setRigging] = useState<Rigging>({...props.rigging});
  const [heights, setHeights] = useState<[number, number]>([runLift, runLift]);  // anchors above the ground (measured)
  const posts: [number, number] = measured ? heights : [lift, lift];
  const l = useMemo(() => ({...props.line, e1: props.line.e1 + posts[0], e2: props.line.e2 + posts[1]}),
    [props.line, posts[0], posts[1]]);
  const [show, setShow] = useState<Record<LayerName, boolean>>(
    {webbing: true, athlete: true, envelope: true, fall: true});
  const [equal, setEqual] = useState(false);
  const [width, setWidth] = useState(800);
  const [boxHeight, setBoxHeight] = useState(HEIGHT);  // the chart's box (fill mode)
  const [pointed, setHover] = useState<number | null>(null);  // distance from A1 under the chart's cursor
  const hover = pointed ?? props.cursorAt ?? null;  // else the outside cursor's
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const measure = () => {
      setWidth(chartRef.current?.clientWidth || 800);
      setBoxHeight(chartRef.current?.clientHeight || HEIGHT);
    };
    measure();
    window.addEventListener("resize", measure);
    // A panel of the app can change its width without the window (a sheet, a column)
    const observer = typeof ResizeObserver === "function" && chartRef.current ? new ResizeObserver(measure) : null;
    if (observer) observer.observe(chartRef.current!);
    return () => { window.removeEventListener("resize", measure); observer?.disconnect(); };
  }, []);
  // A new line (or none: unmounted) takes the point off the map too: a tap's readout stays after
  // lifting the finger, and no mouseleave would ever clear it
  const onHoverRef = useRef(props.onHover);
  onHoverRef.current = props.onHover;
  useEffect(() => { setHover(null); onHoverRef.current(null); }, [l]);
  useEffect(() => () => onHoverRef.current(null), []);

  const est = useMemo(() => Sag.estimate(l.len, l.e1 - l.e2, rigging), [l, rigging]);
  const H = fill ? Math.max(CHART_MIN, boxHeight) : HEIGHT;
  const W = width;
  const color = l.over ? COLORS.over : COLORS.clean;
  const chord = (d: number) => l.e1 + (l.e2 - l.e1) * d / l.len;
  const fall = rigging.fall_zone;
  const envelopeAt = (d: number) => chord(d) - est!.sagAt(d / l.len);
  // The no-fall zone's metres at each end (the run's, capped at a quarter of the line; or the profile's own)
  const zone = zoneMetres(l.len, props.endZone ?? p.zone ?? 0);
  const options = zone > 0 || lift > 0 || runLift > 0 || p.lift !== undefined;
  const rule: LimitRule = {model, slope: props.slope, leashFall: props.leashFall, fall, zone};
  const lim = limits(l.len, l.e1, l.e2, rule, est ? envelopeAt : null);
  const limit = lim.limitAt;
  const allowance = model === "sag" ? fall : props.leashFall;  // the webbing stands this much above the strict limit

  // Vertical range: everything that is drawn
  const dsamples: number[] = [];
  for (let q = 0; q <= 40; q++) dsamples.push(l.len * q / 40);
  if (zone > 0) {  // the limit's steps at the zone's edges
    dsamples.push(zone - 1e-6, zone, l.len - zone, l.len - zone + 1e-6);
    dsamples.sort((a, b) => a - b);
  }
  const values: (number | null)[] = p.z.concat(p.s || [], [l.e1, l.e2, props.line.e1, props.line.e2]);
  dsamples.forEach((d) => {
    values.push(limit(d));
    if (est) values.push(envelopeAt(d) - (show.fall ? fall : 0));
  });
  const frame = chartFrame(W, H, l.len, values, equal);
  const {X, Y, sx, sy, xoff, pw, ph, visibleMin, visibleMax} = frame;
  const pt = (d: number, z: number) => X(d).toFixed(1) + "," + Y(z).toFixed(1);
  const base = (d: number) => X(d).toFixed(1) + "," + (H - M.b);

  const grid = [];
  const yStep = niceStep(visibleMax - visibleMin, 4);
  for (let z = Math.ceil(visibleMin / yStep) * yStep; z <= visibleMax; z += yStep) {
    grid.push(<line x1={M.l} x2={W - M.r} y1={Y(z)} y2={Y(z)} stroke="#eee" />);
    grid.push(<text x={M.l - 6} y={Y(z) + 4} text-anchor="end" fill="#777">{z.toFixed(0) + " m"}</text>);
  }
  const xStep = niceStep(l.len, 6);
  for (let d = 0; d <= l.len + 0.01; d += xStep) {
    grid.push(<text x={X(d)} y={H - 6} text-anchor="middle" fill="#777">{d.toFixed(0) + " m"}</text>);
  }

  const ground: string[] = [], top: string[] = [], bottom: string[] = [];
  for (let i = 0; i < p.d.length; i++) if (p.z[i] !== null) ground.push(pt(p.d[i], p.z[i]!));
  if (p.s) {
    for (let i = 0; i < p.d.length; i++) {
      if (p.s[i] === null || p.z[i] === null) continue;
      top.push(pt(p.d[i], Math.max(p.s[i]!, p.z[i]!)));
      bottom.unshift(pt(p.d[i], p.z[i]!));
    }
  }
  // Water (sea and lakes): each run of water points, from the surface down
  const water: string[] = [];
  if (p.w) {
    let run: number[] = [];
    const flush = () => {
      if (run.length > 1) {
        water.push(run.map((j) => pt(p.d[j], p.z[j]!)).concat(
          [base(p.d[run[run.length - 1]]), base(p.d[run[0]])]).join(" "));
      }
      run = [];
    };
    for (let i = 0; i < p.d.length; i++) {
      if (p.w[i] && p.z[i] !== null) run.push(i); else flush();
    }
    flush();
  }

  // Smallest clearance over terrain and over trees/buildings: from the search, or for
  // measured points here (their length and anchor heights may lie outside the search's), over the points between
  // the anchors as the search takes them
  const smallest = (above: (i: number) => number | null): [number, number] | null => {
    let best: [number, number] | null = null;
    for (let i = 1; i < p.d.length - 1; i++) {
      const z = above(i), lim = limit(p.d[i]);
      if (z !== null && isFinite(lim) && (!best || lim - z < best[1])) best = [p.d[i], lim - z];
    }
    return best;
  };
  const minTerrain = measured ? smallest((i) => p.z[i]) : p.min;
  const minSurface = !measured ? p.min_nmpt || null : p.s ? smallest((i) =>
    p.s![i] === null || p.z[i] === null ? null : Math.max(p.s![i]!, p.z[i]!)) : null;
  const markerOf = (min: [number, number], kind: "min" | "trees", at: MarkerMark["at"]): MarkerMark | null => {
    const topZ = limit(min[0]);
    if (!isFinite(topZ)) return null;
    // the clearance as the rows write it (tight.ts: a tight line's rounded down); over the trees as before
    const value = kind === "min" ? clearanceText(min[1]) : min[1].toFixed(1);
    return {d: min[0], top: topZ, bottom: topZ - min[1], texts: [t(`ui.profile.mark_${kind}`, {m: value})], at};
  };
  const minMark = minTerrain ? markerOf(minTerrain, "min", "below") : null;
  const treesMark = minTerrain && minSurface && minSurface[1] < minTerrain[1] - 0.05
    ? markerOf(minSurface, "trees", "above") : null;

  // The webbing highest above the terrain, as the search saved it (helpers.webbing_height:
  // the safety limit plus the leash fall or the fall zone, on the A-frames)
  let highMark: MarkerMark | null = null;
  if (!measured && p.max_height) {
    const [d, h] = p.max_height, topZ = lim.strict(d) + allowance;
    if (isFinite(topZ)) {
      highMark = {d, top: topZ, bottom: topZ - h, at: "middle",
                  texts: [t("ui.profile.highest", {m: h.toFixed(0)}), t("ui.profile.highest_short", {m: h.toFixed(0)})]};
    }
  }

  // The labels: each marker's, the anchors', the A-frames' and the zone's, placed without overlapping
  const anchorText = (name: string, k: 0 | 1) => {
    const z = measured ? [l.e1, l.e2][k] : [props.line.e1, props.line.e2][k];
    return name + " " + z.toFixed(1) + " m" + (!measured && lift > 0 ? " " + t("ui.profile.anchor_lift", {m: shortMetres(lift)}) : "");
  };
  const ground1 = props.line.e1, ground2 = props.line.e2;
  const framed = posts[0] > 0 || posts[1] > 0;
  const marks: ChartMarks = {
    len: l.len,
    anchors: [{d: 0, ground: ground1, post: posts[0], text: anchorText("A1", 0)},
              {d: l.len, ground: ground2, post: posts[1], text: anchorText("A2", 1)}],
    aframe: framed ? posts.map((h) => [t("ui.profile.aframe", {m: shortMetres(h)}),
                                       t("ui.profile.aframe_short", {m: shortMetres(h)})]) as [string[], string[]]
      : undefined,
    min: minMark, trees: treesMark, highest: highMark,
    zone: zone > 0 ? {metres: zone, texts: [t("ui.profile.zone", {m: shortMetres(zone)}),
                                              t("ui.profile.zone_short", {m: shortMetres(zone)})]} : null,
  };
  const family = useRef("");
  if (!family.current && chartRef.current && typeof getComputedStyle === "function") {
    family.current = getComputedStyle(chartRef.current).fontFamily;
  }
  const measure = (text: string, bold: boolean) => family.current ? textWidth(text, bold, family.current, TEXT_PX)
    : estimateWidth(text, bold, TEXT_PX);
  const placed = chartLabels(frame, marks, measure, LABEL_BOXES);
  const label = (id: string) => placed.find((q) => q.id === id);
  const labelText = (q: PlacedLabel | undefined, cls: string, fill?: string, bold = false) => q &&
    <text class={"fal-label " + cls} x={q.x} y={q.y} text-anchor={q.anchor} fill={fill}
          font-weight={bold ? "bold" : undefined}>{q.text}</text>;

  let summary = t("ui.profile.sag_none");
  if (est) {
    const k = est.sag.indexOf(Math.max(...est.sag));
    summary = t("ui.profile.sag", {sag: est.sag[k].toFixed(2), at: (est.f[k] * l.len).toFixed(0),
                                   kn: (est.H[k] / 1e3).toFixed(1),
                                   free: Math.max(...est.unloaded.map((e) => e[1] - (l.e1 - l.e2) * e[0] / l.len)).toFixed(2)});
  }

  // The readout's parts under the cursor (and their widest values for its room): a label with a colon each, joined
  // by "; " (R9 and docs/wording.md: no " · " between values); the water, a filled gap, the clearance over the trees
  // and the zone in brackets after the part they belong to
  type ReadValues = {at: string; z?: string; water?: boolean; gap?: boolean; s?: string; limit?: string; clear?: string;
                     over?: string; zone?: boolean; sag?: string; kn?: string; above?: string};
  const readText = (v: ReadValues): string => {
    const parts = [t("ui.profile.read_at", {d: v.at})];
    if (v.z !== undefined) {
      parts.push([t("ui.profile.read_terrain", {m: v.z}), v.water && t("ui.profile.read_water"),
                  v.gap && t("ui.profile.read_gap")].filter(Boolean).join(" "));
    }
    if (v.s !== undefined) parts.push(t("ui.profile.read_trees", {m: v.s}));
    if (v.limit !== undefined) parts.push(t("ui.profile.read_limit", {m: v.limit}));
    if (v.clear !== undefined) {
      parts.push(v.over !== undefined ? t("ui.profile.read_clear", {m: v.clear}) + " " + t("ui.profile.read_over", {m: v.over})
        : t("ui.profile.read_clear", {m: v.clear}));
    }
    if (v.zone) parts[parts.length - 1] += " " + t("ui.profile.in_zone");
    if (v.sag !== undefined) {
      parts.push(t("ui.profile.read_athlete", {sag: v.sag, kn: v.kn}) +
                 (v.above !== undefined ? ", " + t("ui.profile.read_above", {m: v.above}) : ""));
    }
    return parts.join("; ");
  };

  // Under the cursor: readout, the loaded webbing, the point on the map
  let readout = summary, athlete: Sag.Athlete | null = null;
  if (hover !== null) {
    const d = hover;
    let lo = 0, hi = p.d.length - 1;  // nearest terrain sample
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (p.d[mid] < d) lo = mid; else hi = mid; }
    const k = (d - p.d[lo] < p.d[hi] - d) ? lo : hi;
    const z = p.z[k], s = p.s ? p.s[k] : null;
    const v: ReadValues = {at: d.toFixed(0)};
    if (z !== null) v.z = z.toFixed(1);
    if (p.w && p.w[k]) v.water = true;
    if (p.g && p.g[k]) v.gap = true;
    if (s !== null && s !== undefined) v.s = s.toFixed(1);
    const here = limit(d);
    if (isFinite(here)) {
      v.limit = here.toFixed(1);
      if (z !== null) v.clear = (here - z).toFixed(1);
      if (s !== null && s !== undefined && z !== null) v.over = (here - Math.max(s, z)).toFixed(1);
    }
    if (zone > 0 && lim.inZone(d)) v.zone = true;
    athlete = est && show.athlete && d > 0.01 * l.len && d < 0.99 * l.len ? est.athlete(d) : null;
    if (athlete) {
      v.sag = athlete.sag.toFixed(2);
      v.kn = (athlete.H / 1e3).toFixed(1);
      if (z !== null) v.above = (chord(d) - athlete.sag - z).toFixed(1);
    }
    readout = readText(v);
  }

  // The compact readout keeps one height while the cursor moves (the card around it does not jump): its box holds,
  // hidden, the longer of the summary and the cursor's readout made of the widest value of each part along the line
  // (the digits are tabular, so the widest has the most characters) with every part the line can show
  const room = compact ? readoutRoom() : "";
  function readoutRoom(): string {
    const widest = (values: number[], digits: number) => values.reduce((w, v) => {
      const text = isFinite(v) ? v.toFixed(digits) : "";
      return text.length > w.length ? text : w;
    }, "0");
    const zs: number[] = [], ss: number[] = [], limits: number[] = [], clear: number[] = [], over: number[] = [];
    const above: number[] = [], maxSag = est ? Math.max(...est.sag) : 0;
    p.d.forEach((d, i) => {
      const z = p.z[i], s = p.s ? p.s[i] : null, here = limit(d);
      if (z !== null) { zs.push(z); above.push(chord(d) - z, chord(d) - z - maxSag); }  // the athlete's height range
      if (s !== null && s !== undefined) ss.push(s);
      if (isFinite(here)) {
        limits.push(here);
        if (z !== null) clear.push(here - z);
        if (s !== null && s !== undefined && z !== null) over.push(here - Math.max(s, z));
      }
    });
    const v: ReadValues = {at: l.len.toFixed(0)};
    if (zs.length) v.z = widest(zs, 1);
    if (p.w && p.w.some(Boolean)) v.water = true;
    if (p.g && p.g.some(Boolean)) v.gap = true;
    if (ss.length) v.s = widest(ss, 1);
    if (limits.length) {
      v.limit = widest(limits, 1);
      if (clear.length) v.clear = widest(clear, 1);
      if (clear.length && over.length) v.over = widest(over, 1);
    }
    if (zone > 0) v.zone = true;
    if (est && show.athlete) {
      v.sag = widest(est.sag, 2);
      v.kn = widest(est.H.map((h) => h / 1e3), 1);
      if (above.length) v.above = widest(above, 1);
    }
    const text = readText(v);
    return text.length > summary.length ? text : summary;
  }

  const onMove = (e: MouseEvent) => {
    const box = (e.currentTarget as SVGElement).ownerSVGElement!.getBoundingClientRect();
    const d = Math.max(0, Math.min(l.len, (e.clientX - box.left - M.l - xoff) / sx));
    setHover(d);
    const t = d / l.len;
    props.onHover([l.lat1 + (l.lat2 - l.lat1) * t, l.lon1 + (l.lon2 - l.lon1) * t]);
    props.onCursor?.(d, l.len);
  };
  const onLeave = () => { setHover(null); props.onHover(null); props.onCursor?.(null, l.len); };
  // The keyboard: ← → move the readout by a fiftieth of the line (Shift: a tenth), Home/End to the anchors
  const hoverTo = (d: number) => {
    d = Math.max(0, Math.min(l.len, d));
    setHover(d);
    const t = d / l.len;
    props.onHover([l.lat1 + (l.lat2 - l.lat1) * t, l.lon1 + (l.lon2 - l.lon1) * t]);
    props.onCursor?.(d, l.len);
  };
  const onKey = (e: KeyboardEvent) => {
    const by = l.len / (e.shiftKey ? 10 : 50), at = hover ?? 0;
    const to = e.key === "ArrowRight" ? at + by : e.key === "ArrowLeft" ? at - by
      : e.key === "Home" ? 0 : e.key === "End" ? l.len : null;
    if (to === null) return;
    e.preventDefault();
    hoverTo(to);
  };
  // Touch and pens: a tap reads a point, a drag along the chart moves it; the readout stays after lifting
  // (the mouse has its own events above, which leave clears)
  const onPointer = (e: PointerEvent) => {
    if (e.pointerType === "mouse") return;
    if (e.type === "pointerdown") {
      try { (e.currentTarget as Element).setPointerCapture(e.pointerId); } catch { /* not an active pointer */ }
    }
    onMove(e);
  };

  const setRig = (key: keyof Rigging, input: HTMLInputElement) => {
    const v = parseFloat(input.value);
    if (isFinite(v) && (v > 0 || (key !== "pretension" && key !== "stretch" && v >= 0))) {
      setRigging({...rigging, [key]: v});
    } else input.value = String(rigging[key]);
  };
  const setHeight = (k: 0 | 1, input: HTMLInputElement) => {
    const v = parseFloat(input.value);
    if (isFinite(v) && v >= 0) setHeights(k ? [heights[0], v] : [v, heights[1]]);
    else input.value = String(heights[k]);
  };
  // The title: "Profile: <len> m, from A1 at … to A2 at … (height difference …), min. clearance …" (one sentence: its
  // parts joined by words and commas); its facts for a bar, the one that matters first: a measured profile's verdict,
  // the clearance, the anchors, each a label with a colon, joined by "; " (R9; the user's answers of 2026-11-23: no
  // height difference among the facts). A found line's anchors are the ground's (on A-frames the webbing starts
  // higher), a measured one's its ends'
  const t1 = measured ? l.e1 : props.line.e1, t2 = measured ? l.e2 : props.line.e2;
  const a1 = t1.toFixed(1), a2 = t2.toFixed(1), dh = Math.abs(t1 - t2).toFixed(1);
  let clearance = t("ui.profile.clear", {m: clearanceText(l.clr)});
  let factClear = t("ui.profile.fact_clear", {m: clearanceText(l.clr)}), verdict = "";
  if (measured) {
    const clr = minTerrain ? minTerrain[1] : NaN, clrN = minSurface ? minSurface[1] : null;
    clearance = isFinite(clr) ? t("ui.profile.clear", {m: clearanceText(clr)}) : t("ui.profile.clear_unknown");
    factClear = isFinite(clr) ? t("ui.profile.fact_clear", {m: clearanceText(clr)}) : t("ui.profile.fact_clear_unknown");
    if (clrN !== null) {
      clearance += " " + t("ui.profile.clear_over", {m: clrN.toFixed(1)});
      factClear += " " + t("ui.profile.fact_over", {m: clrN.toFixed(1)});
    }
    verdict = !isFinite(clr) ? "" : t(clr < 0 ? "ui.profile.verdict_bad" : clrN !== null && clrN < 0
      ? "ui.profile.verdict_trees" : "ui.profile.verdict_ok");
  }
  const title = t(measured ? "ui.profile.title_measured" : "ui.profile.title",
                  {len: l.len.toFixed(0), a1, a2, dh, clearance}) + (verdict ? " – " + verdict : "");
  const facts = [verdict, factClear, t("ui.profile.fact_ends", {a1, a2})].filter((f) => f).join("; ");
  const onTitle = useRef(props.onTitle);
  onTitle.current = props.onTitle;
  useEffect(() => { onTitle.current?.(title, facts); }, [title, facts]);
  useEffect(() => () => onTitle.current?.("", ""), []);

  // What the line needs rigged (a found line of a run with the options): the A-frames with and without the zone
  const need = options && !measured ? riggingNeed(props.line, p, rule) : null;
  const needRow = need && <div class="fal-need" role="group" aria-label={t("ui.profile.need_label")}>
    {need.needed < 0.05 ? <span class="fal-pill fal-ok">{t("ui.profile.need_none")}</span>
      : <span class={"fal-pill " + (need.needed > runLift + 1e-9 ? "fal-bad" : "fal-warn")}>
        {t("ui.profile.need", {m: need.needed.toFixed(1)})}</span>}
    {zone > 0 && need.noZone !== null && <span>{need.noZone < 0.05 ? t("ui.profile.need_no_zone_none")
      : t("ui.profile.need_no_zone", {m: need.noZone.toFixed(1)})}</span>}
    {need.needed > runLift + 1e-9 && <span class="fal-bad-text">{t("ui.profile.need_over", {m: shortMetres(runLift)})}</span>}
  </div>;

  // The legend in the kit's look (docs/DESIGN.md row 90): the areas' swatches the kit's box (its inset edge), the
  // lines' and the marks' signs drawn as on the chart (a legend's marks)
  const legend = <span class="fal-profile-legend u-legend-items">
    <span class="u-legend-item"><span class="u-legend-sw fal-sw-terrain" />{t("ui.profile.legend_terrain")}</span>
    <span class="u-legend-item"><span class="u-legend-sw fal-sw-trees" />{t("ui.profile.legend_trees")}</span>
    <span class="u-legend-item"><span class="u-legend-sw fal-sw-water" />{t("ui.profile.legend_water")}</span>
    <span class="u-legend-item"><Swatch style={"border-top:2px dashed " + PROFILE.limit + ";height:0"} />
      {t("ui.profile.legend_limit", {model: t(model === "sag" ? "ui.profile.model_sag" : "ui.profile.model_formula")})}</span>
    {zone > 0 && <span class="u-legend-item"><Swatch class="fal-swatch-zone" />{t("ui.profile.legend_zone")}</span>}
    {framed && <span class="u-legend-item"><svg class="fal-swatch-frame" width="12" height="10" viewBox="0 0 12 10" aria-hidden="true">
      <polyline points="1,10 6,1 11,10" fill="none" stroke={PROFILE.frame} stroke-width="2" /></svg>{t("ui.profile.legend_aframe")}</span>}
  </span>;
  // the kit's button (the user kept "×1.6" as the 3D view's "×1": docs/wording.md)
  const scale = <button type="button" class="u-btn fal-scale" onClick={() => setEqual(!equal)}>
    {equal ? t("ui.profile.scale_auto") : t("ui.profile.scale_true", {f: (sy / sx).toFixed(1)})}</button>;

  // The A-frames: two legs from the ground to the anchor on top
  const aframes = framed ? ([[0, ground1, posts[0], 1], [l.len, ground2, posts[1], -1]] as [number, number, number, number][])
    .filter(([, , h]) => h > 0).map(([d, g, h, side]) => {
      const leg = frameLeg(frame, g, h), inner = X(d) + side * leg, outer = X(d) - side * leg;
      return <g class="fal-frame">
        <polyline points={`${outer.toFixed(1)},${Y(g).toFixed(1)} ${X(d).toFixed(1)},${Y(g + h).toFixed(1)} ${inner.toFixed(1)},${Y(g).toFixed(1)}`}
                  fill="none" stroke={PROFILE.frame} stroke-width={2} stroke-linejoin="round" />
        <circle cx={X(d)} cy={Y(g)} r={2} fill={PROFILE.frame} />
      </g>;
    }) : null;
  const marker = (m: MarkerMark | null, stroke: string, width: number, dash?: string) => m &&
    <line x1={X(m.d)} x2={X(m.d)} y1={Y(m.top)} y2={Y(m.bottom)} stroke={stroke} stroke-width={width}
          stroke-dasharray={dash} />;

  return <div class={"fal-profile" + (fill ? " fal-fill" : "") + (compact ? " fal-compact" : "")}
              onClick={(e) => e.stopPropagation()}>
    {!compact && <div class="fal-profile-head">
      <div>
        <b class="fal-profile-title">{title}</b>
        {legend}
      </div>
      <div>
        {scale}{" "}
        {/* the kit's close (components.tsx CloseButton's markup: this file is in the 3D view's bundle too, which
            does not take the kit's components) */}
        <button type="button" class="u-ib u-x fal-close" aria-label={t("ui.profile.close")} title={t("ui.profile.close")}
                onClick={props.onClose}><Icon name="close" /></button>
      </div>
    </div>}
    {!props.needBelow && needRow}
    <div class="fal-profile-controls">
      {compact && <span class="fal-key">{legend}{scale}</span>}
      {measured && <span class="fal-heights">{(["A1", "A2"] as const).map((name, k) =>
        <label><input type="number" min={0} step={0.5} value={heights[k]}
                      onChange={(e) => setHeight(k as 0 | 1, e.currentTarget)} /> {t("ui.profile.height", {name})}</label>)}</span>}
      <span class="fal-rigging">{RIGGING.map(([key, step]) =>
        <label><input type="number" min={0} step={step} value={rigging[key]}
                      onChange={(e) => setRig(key, e.currentTarget)} /> {t(`ui.profile.rig.${key}`)}</label>)}</span>
      <span class="fal-layers">{LAYERS.map(([key, style]) =>
        <label><input type="checkbox" class="u-check" checked={show[key]}
                      onChange={(e) => setShow({...show, [key]: e.currentTarget.checked})} />{" "}
          <Swatch style={style} /> {t(`ui.profile.layer.${key}`)}</label>)}</span>
    </div>
    <div class="fal-profile-chart" ref={chartRef}>
      <svg width={W} height={H} font-size={TEXT_PX}>
        {grid}
        {zone > 0 && [[0, zone], [l.len - zone, l.len]].map(([a, b], k) => <g class="fal-zone">
          <rect class="fal-zone-band" x={X(a)} y={M.t} width={(b - a) * sx} height={ph} fill={PROFILE.zoneFill} />
          <line class="fal-zone-edge" x1={X(k ? a : b)} x2={X(k ? a : b)} y1={M.t} y2={H - M.b} stroke={PROFILE.zone}
                stroke-width={1} stroke-dasharray="4 3" />
        </g>)}
        {est && show.fall && <polygon fill={PROFILE.fallFill} stroke="none" points={
          dsamples.map((d) => pt(d, envelopeAt(d))).concat(
            dsamples.map((d) => pt(d, envelopeAt(d) - fall)).reverse()).join(" ")} />}
        {p.s && <polygon points={top.concat(bottom).join(" ")} fill={PROFILE.treesFill} stroke="none" />}
        <polygon points={ground.concat([base(l.len), base(0)]).join(" ")} fill={PROFILE.terrainFill}
                 stroke={PROFILE.terrain} stroke-width={1} />
        {water.map((points) =>
          <polygon points={points} fill={PROFILE.waterFill} stroke={PROFILE.water} stroke-width={1} />)}
        <polyline points={dsamples.map((d) => pt(d, limit(d))).join(" ")} fill="none" stroke={PROFILE.limit}
                  stroke-width={1.5} stroke-dasharray="6 4" />
        {est && show.envelope && <polyline points={dsamples.map((d) => pt(d, envelopeAt(d))).join(" ")}
                                           fill="none" stroke={PROFILE.envelope} stroke-width={1.5}
                                           stroke-dasharray="2 3" />}
        {show.webbing && <polyline fill="none" stroke={color} stroke-width={2.5} points={
          (est ? est.unloaded.map((e) => pt(e[0], l.e1 - e[1])) : [pt(0, l.e1), pt(l.len, l.e2)]).join(" ")} />}
        {athlete && <polyline class="fal-loaded" fill="none" stroke={PROFILE.athlete} stroke-width={1.5}
                              points={athlete.curve.map((e) => pt(e[0], l.e1 - e[1])).join(" ")} />}
        {athlete && hover !== null && <circle class="fal-athlete" r={4} fill={PROFILE.athlete} cx={X(hover)}
                                              cy={Y(chord(hover) - athlete.sag)} />}
        {marker(minMark, PROFILE.terrain, 2)}
        {marker(treesMark, PROFILE.trees, 2)}
        {marker(highMark, PROFILE.envelope, 1.5, "4 3")}
        {aframes}
        {([[0, l.e1], [l.len, l.e2]] as [number, number][]).map(([d, z]) => <circle cx={X(d)} cy={Y(z)} r={4} fill={color} />)}
        {labelText(label("highest"), "fal-label-highest", PROFILE.envelope)}
        {labelText(label("zone1"), "fal-zone-label", PROFILE.zone)}
        {labelText(label("zone2"), "fal-zone-label", PROFILE.zone)}
        {labelText(label("aframe1"), "fal-frame-label", PROFILE.frame)}
        {labelText(label("aframe2"), "fal-frame-label", PROFILE.frame)}
        {labelText(label("trees"), "fal-label-trees", PROFILE.trees)}
        {labelText(label("min"), "fal-label-min", PROFILE.terrain)}
        {labelText(label("anchor1"), "fal-label-anchor", undefined, true)}
        {labelText(label("anchor2"), "fal-label-anchor", undefined, true)}
        {hover !== null && <line class="fal-cursor" x1={X(hover)} x2={X(hover)} y1={M.t} y2={H - M.b}
                                 stroke="#333" stroke-dasharray="2 2" />}
        <rect class="fal-hover" x={M.l} y={M.t} width={pw} height={ph} fill="transparent" tabIndex={0}
              role="slider" aria-label={t("ui.profile.slider")} aria-valuemin={0}
              aria-valuemax={Math.round(l.len)} aria-valuenow={hover === null ? undefined : Math.round(hover)}
              aria-valuetext={readout || undefined}
              onMouseMove={onMove} onMouseLeave={onLeave} onPointerDown={onPointer} onPointerMove={onPointer}
              onKeyDown={onKey} onBlur={onLeave} />
      </svg>
    </div>
    <div class="fal-profile-readout" title={compact && readout ? readout : undefined} data-room={room || undefined}>
      <span class="fal-readout-text">{readout}</span></div>
    {props.needBelow && needRow}
  </div>;
}
