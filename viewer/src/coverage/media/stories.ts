// The four stories at three lengths: their scenes, each with a weight (its share of the length) and the
// shortest length it appears in, and the frame at a time (a short dip to the background between scenes).
import { ct } from "../i18n";
import { clamp, type Frame } from "../draw/canvas";
import {
  otherPlaces, placeCredit, sceneContrast, sceneEnd, sceneSummary, sceneTimeline, sceneTitle, sceneTour, sceneVerify,
  type Depth, type Scene,
} from "./scenes";
import type { Lang } from "../i18n";

export const STORIES = ["contrast", "fill", "timeline", "mix"] as const;
export type Story = (typeof STORIES)[number];
export const LENGTHS = {short: 10, medium: 18, long: 26} as const;
export type Length = keyof typeof LENGTHS;
const DEPTH: Record<Length, Depth> = {short: 0, medium: 1, long: 2};

export interface TimedScene { start: number; dur: number; draw: Scene }

/** The scenes of a story with their start and duration in seconds; `place` the contrast's first place. */
export function storyScenes(story: Story, length: Length, place: string, lang: Lang): TimedScene[] {
  const depth = DEPTH[length], others = otherPlaces(place);
  // a scene showing data carries its credit, which the end card repeats
  const S = (w: number, draw: Scene, min: Depth = 0, credit?: string) => ({w, draw, min, credit});
  const map = ct(lang, "map.credit"), tour = sceneTour(depth);
  const contrast = (p: string, w: number, min: Depth = 0) => S(w, sceneContrast(p), min, placeCredit(p, lang));
  const list = {
    contrast: [S(1.1, sceneTitle(ct(lang, "media.hook"), ct(lang, `place.${place}`))), contrast(place, 4),
      contrast(others[0] || place, 3, 2), contrast(others[1] || place, 3, 2),
      S(2.6, sceneVerify, 1), S(2, sceneSummary, 1, map)],
    fill: [S(1.1, sceneTitle(ct(lang, "media.fill.title"), null)), S(depth === 0 ? 5 : 7.5, tour, 0, map),
      S(1.6, sceneSummary, 1, map)],
    timeline: [S(1, sceneTitle(ct(lang, "media.timeline.title"), ct(lang, "media.timeline.start"))),
      S(depth === 0 ? 6 : 8, sceneTimeline(depth), 0, map), S(1.6, sceneSummary, 2, map)],
    mix: [contrast(place, 3.4), contrast(others[0] || place, 3, 2), S(2.4, sceneVerify, 2), S(depth === 0 ? 4 : 6, tour, 0, map),
      S(1.4, sceneSummary, 1, map)],
  }[story].filter(s => depth >= s.min);
  list.push(S(1.6, sceneEnd([...new Set(list.flatMap(s => s.credit ? [s.credit] : []))])));
  const total = LENGTHS[length], sum = list.reduce((a, s) => a + s.w, 0);
  let at = 0;
  return list.map(s => { const dur = s.w / sum * total, scene = {start: at, dur, draw: s.draw}; at += dur; return scene; });
}

/** The README's GIF (2:1): the short fill's tour (as long as in the 10 s story), then the summary, as one loop. */
export function gifScenes(): TimedScene[] {
  return [{start: 0, dur: 6.5, draw: sceneTour(0)}, {start: 6.5, dur: 2.5, draw: sceneSummary}];
}

export const scenesLength = (scenes: TimedScene[]): number => scenes[scenes.length - 1].start + scenes[scenes.length - 1].dur;

/** The frame at t seconds. */
export function drawStory(f: Frame, scenes: TimedScene[], t: number): void {
  let i = scenes.findIndex(s => t < s.start + s.dur);
  if (i < 0) i = scenes.length - 1;
  const s = scenes[i];
  f.ctx.save();
  s.draw(f, clamp((t - s.start) / s.dur));
  f.ctx.restore();
  // a short dip between scenes
  const edge = Math.min(.18, s.dur * .08);
  const fadeIn = i > 0 ? clamp((t - s.start) / edge) : 1, fadeOut = i < scenes.length - 1 ? clamp((s.start + s.dur - t) / edge) : 1;
  const a = 1 - Math.min(fadeIn, fadeOut);
  if (a > 0) { f.ctx.fillStyle = f.th.bg; f.ctx.globalAlpha = a; f.ctx.fillRect(0, 0, f.W, f.H); f.ctx.globalAlpha = 1; }
}
