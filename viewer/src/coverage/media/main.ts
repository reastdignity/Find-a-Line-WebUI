// The page of the coverage animations and images (tools/coverage_media.py; built by `node build.mjs --media
// --out <dir>`, never in dist). It draws on <canvas id="media"> and sets window.FAL_MEDIA once the outlines
// (./coverage-shapes.json), the contrast (./contrast/) and the fonts are loaded: `setup` picks a story or an
// image and sizes the canvas, `frame(t)` draws the frame at t seconds, deterministic (no clock, no
// animation frames), so a tool can step through a story at any frame rate.
import "../../ui/fonts.css";
import type { Frame, Scale } from "../draw/canvas";
import type { Lang } from "../i18n";
import { THEMES } from "../palette";
import { load } from "./assets";
import { places } from "./scenes";
import { STATICS, type StaticGroup } from "./statics";
import { drawStory, gifScenes, LENGTHS, scenesLength, storyScenes, STORIES, type Length, type Story, type TimedScene } from "./stories";

const FORMATS = {"4x5": [1080, 1350], "9x16": [1080, 1920]} as const;
type Format = keyof typeof FORMATS;
/** The README's GIF (2:1). */
const GIF = {width: 1200, height: 600} as const;

type Theme = "light" | "dark";
interface Common { theme: Theme; lang: Lang; scale?: Scale }
export type Setup =
  | Common & { kind: "story"; story: Story; length: Length; format: Format; place?: string }
  | Common & { kind: "static"; name: string }
  | Common & { kind: "gif" };

export interface FalMedia {
  stories: Story[];
  lengths: typeof LENGTHS;
  formats: typeof FORMATS;
  gif: typeof GIF;
  places: string[];
  statics: { name: string; width: number; height: number; group: StaticGroup }[];
  setup(o: Setup): { width: number; height: number; duration: number };
  frame(t: number): void;
}

declare global { interface Window { FAL_MEDIA?: FalMedia; FAL_MEDIA_ERROR?: string } }

function canvas(): HTMLCanvasElement {
  let c = document.getElementById("media") as HTMLCanvasElement | null;
  if (!c) { c = document.createElement("canvas"); c.id = "media"; document.body.append(c); }
  return c;
}

let current: { frame: Frame; scenes: TimedScene[] | null; draw: ((f: Frame) => void) | null } | null = null;

function setup(o: Setup): { width: number; height: number; duration: number } {
  if (!(o.theme in THEMES)) throw new Error(`unknown theme ${o.theme}`);
  const first = places()[0];
  let width: number, height: number, scenes: TimedScene[] | null = null, draw: ((f: Frame) => void) | null = null;
  if (o.kind === "static") {
    const image = STATICS.find(s => s.name === o.name);
    if (!image) throw new Error(`unknown image ${o.name}`);
    ({width, height, draw} = image);
  } else if (o.kind === "gif") {
    ({width, height} = GIF);
    scenes = gifScenes();
  } else {
    if (!STORIES.includes(o.story) || !(o.length in LENGTHS) || !(o.format in FORMATS)) throw new Error("unknown story, length or format");
    [width, height] = FORMATS[o.format];
    scenes = storyScenes(o.story, o.length, o.place || first, o.lang);
  }
  const c = canvas();
  c.width = width; c.height = height;
  const ctx = c.getContext("2d")!;
  current = {frame: {ctx, th: THEMES[o.theme], W: width, H: height, lang: o.lang, scale: o.scale || "words"}, scenes, draw};
  return {width, height, duration: scenes ? scenesLength(scenes) : 0};
}

function frame(t: number): void {
  if (!current) throw new Error("setup first");
  const {frame: f, scenes, draw} = current;
  f.ctx.setTransform(1, 0, 0, 1, 0, 0);
  f.ctx.clearRect(0, 0, f.W, f.H);
  if (scenes) drawStory(f, scenes, t); else draw!(f);
}

load().then(() => {
  window.FAL_MEDIA = {
    stories: [...STORIES], lengths: LENGTHS, formats: FORMATS, gif: GIF, places: places(),
    statics: STATICS.map(({name, width, height, group}) => ({name, width, height, group})),
    setup, frame,
  };
}, (error: unknown) => { window.FAL_MEDIA_ERROR = String(error); });
