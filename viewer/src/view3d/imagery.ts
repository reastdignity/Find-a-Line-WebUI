// The imagery of the 3D view (docs/3d-view-contract.md, "Wave 2", V2b): the run's national orthophoto (our cache
// first where it may have the tiles, else its service), Esri's satellite imagery (with the operator's key), or
// the terrain shaded. Each chunk gets one canvas of its tiles (tiles.ts: the zoom, the URLs, the UVs) as its
// texture; the control is a segmented one in the scene's toolbar, the credits go to the scene's credits box
// (credits.ts). Plain DOM, no style attributes (the CSP's style-src 'self'): classes of ui.css.

import { CanvasTexture, LinearMipmapLinearFilter, SRGBColorSpace } from "three";
import { t } from "../i18n";
import { orthoForApp } from "../result/load";
import type { Ortho } from "../types";
import { DATA_CREDITS, DATA_ORDER, dataCredits, IMAGERY_CREDITS, IMAGERY_ORDER, imageryCredits } from "./credits";
import type { Chunk, Scene3D } from "./scene-api";
import {
  cacheBusted, corridorOf, dataBounds, esriDraws, orthoDraws, orthoOf, planTextures, TILE_PX, uvOf,
  type TexturePlan, type TileDraw, type TileImage,
} from "./tiles";

export type ImageryKind = "ortho" | "esri" | "shaded";

export interface Imagery {
  /** The kinds this run can show, the default first. */
  available: ImageryKind[];
  current: ImageryKind;
  set(kind: ImageryKind): Promise<void>;
  dispose(): void;
}

/** Images loaded at once (the browser's limit per host is about six). */
const PARALLEL = 6;

const LABELS: Record<ImageryKind, string> = {
  ortho: "ui.view3d.imagery_ortho", esri: "ui.view3d.imagery_esri", shaded: "ui.view3d.imagery_shaded",
};

/** Loads images a few at a time; `stop` drops what waits and cancels what loads. */
class Loader {
  private waiting: (() => void)[] = [];
  private active = new Set<HTMLImageElement>();
  private running = 0;
  stopped = false;

  /** An image with CORS (`crossOrigin` before `src`, so the canvas stays clean), null when it fails. */
  load(url: string): Promise<HTMLImageElement | null> {
    return new Promise((resolve) => {
      const run = () => {
        if (this.stopped) { resolve(null); return; }
        this.running++;
        const img = new Image();
        this.active.add(img);
        const done = (ok: boolean) => {
          img.onload = img.onerror = null;
          this.active.delete(img);
          this.running--;
          this.waiting.shift()?.();
          resolve(ok && !this.stopped ? img : null);
        };
        img.onload = () => done(true);
        img.onerror = () => done(false);
        img.crossOrigin = "anonymous";
        img.decoding = "async";
        img.src = url;
      };
      if (this.running < PARALLEL) run(); else this.waiting.push(run);
    });
  }

  /** A service's image: asked once more past the browser's cache when it fails (a CORS failure of a response
   *  the 2D map cached without `Vary: Origin` looks like any error). */
  async service(url: string): Promise<HTMLImageElement | null> {
    return await this.load(url) ?? (this.stopped ? null : await this.load(cacheBusted(url)));
  }

  stop() {
    this.stopped = true;
    for (const run of this.waiting.splice(0)) run();
    for (const img of this.active) img.src = "";
  }
}

function drawImage(ctx: CanvasRenderingContext2D, img: HTMLImageElement, part: TileImage, dx: number, dy: number) {
  if (part.crop) {
    const [sx, sy, size] = part.crop;
    ctx.drawImage(img, sx, sy, size, size, dx, dy, TILE_PX, TILE_PX);
  } else ctx.drawImage(img, dx, dy, TILE_PX, TILE_PX);
}

/** One chunk's canvas: the shaded terrain's colour under the tiles (a tile that fails leaves it), each tile from
 *  our cache when worth trying, else its layers from the service. Null when stopped. */
async function compose(plan: TexturePlan, draws: TileDraw[], loader: Loader, fill: string):
    Promise<HTMLCanvasElement | null> {
  const canvas = document.createElement("canvas");
  canvas.width = plan.width;
  canvas.height = plan.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, plan.width, plan.height);
  await Promise.all(draws.map(async (d) => {
    const dx = d.x * TILE_PX - plan.px0, dy = d.y * TILE_PX - plan.py0;
    const cached = d.cache ? await loader.load(d.cache) : null;  // ours: same origin, no CORS retry
    if (cached) { ctx.drawImage(cached, dx, dy, TILE_PX, TILE_PX); return; }
    const images = await Promise.all(d.layers.map((part) => loader.service(part.url)));
    images.forEach((img, k) => { if (img) drawImage(ctx, img, d.layers[k], dx, dy); });  // bottom first
  }));
  return loader.stopped ? null : canvas;
}

/** The imagery of `scene`: its control in `scene.toolbar`, its credits in `scene.credits`. */
export function createImagery(scene: Scene3D, options: { runId: string; esriKey: string | null }): Imagery {
  const {meta} = scene;
  const ortho: Ortho | null = orthoForApp(orthoOf(meta.ortho), options.runId);
  const available: ImageryKind[] = [...(ortho ? ["ortho" as const] : []), ...(options.esriKey ? ["esri" as const] : []),
                                    "shaded"];
  const data = dataCredits(meta.attribution, options.runId);
  if (data) scene.credits.set(DATA_CREDITS, data, DATA_ORDER);

  // The textures' plans, once: the line's chunks first (they are looked at first)
  const order = scene.chunks.map((c, k) => k).sort((a, b) => Number(scene.chunks[b].hasLine) - Number(scene.chunks[a].hasLine));
  const plans = planTextures(meta.affine, scene.chunks.map((c) => ({bounds: dataBounds(meta, c.bounds), hasLine: c.hasLine})),
                             scene.level);
  const corridors = new Map<number, ReturnType<typeof corridorOf>>();
  const corridor = (z: number) => {
    if (!corridors.has(z)) corridors.set(z, corridorOf(meta.affine, meta.anchors, z));
    return corridors.get(z)!;
  };
  const textures = new Map<Chunk, CanvasTexture>();
  let loader: Loader | null = null;

  // The control: a segmented one when there is a choice, else the note that the terrain is shaded
  const box = document.createElement("div");
  box.className = "u-row";
  const buttons = new Map<ImageryKind, HTMLButtonElement>();
  if (available.length > 1) {
    const seg = document.createElement("div");
    seg.className = "u-seg";
    seg.setAttribute("role", "radiogroup");
    seg.setAttribute("aria-label", t("ui.view3d.imagery"));
    for (const kind of available) {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.textContent = t(LABELS[kind]);
      b.onclick = () => { void imagery.set(kind); };
      buttons.set(kind, b);
      seg.append(b);
    }
    box.append(seg);
  } else {
    const note = document.createElement("span");
    note.className = "u-small";
    note.textContent = t("ui.view3d.no_imagery");
    box.append(note);
  }
  const status = document.createElement("span");
  status.className = "u-small";
  status.setAttribute("role", "status");
  status.hidden = true;
  status.textContent = t("ui.view3d.loading_imagery");
  box.append(status);
  scene.toolbar.append(box);

  const mark = (kind: ImageryKind) => buttons.forEach((b, k) => {
    b.className = k === kind ? "u-on" : "";
    b.setAttribute("aria-checked", String(k === kind));
  });

  const retexture = (chunk: Chunk, texture: CanvasTexture | null, uv?: (x: number, y: number) => [number, number]) => {
    chunk.setTexture(texture, uv);
    textures.get(chunk)?.dispose();
    if (texture) textures.set(chunk, texture); else textures.delete(chunk);
  };

  // The 2D map's terrain colour (tokens.css, under the page's .ui root) where a tile is missing
  const fillColour = () => getComputedStyle(scene.toolbar).getPropertyValue("--terrain").trim() || "#bba680";

  const imagery: Imagery = {
    available,
    current: available[0],
    async set(kind: ImageryKind) {
      if (!available.includes(kind)) return;
      loader?.stop();
      imagery.current = kind;
      mark(kind);
      const credit = imageryCredits(kind, ortho);
      if (credit) scene.credits.set(IMAGERY_CREDITS, credit, IMAGERY_ORDER); else scene.credits.remove(IMAGERY_CREDITS);
      if (kind === "shaded") {
        loader = null;
        status.hidden = true;
        for (const chunk of scene.chunks) retexture(chunk, null);
        scene.invalidate();
        return;
      }
      const mine = loader = new Loader(), fill = fillColour();
      status.hidden = false;
      // Chunk by chunk, the line's first; each keeps its last texture until its new one is ready
      await Promise.all(order.map(async (k) => {
        const plan = plans[k], chunk = scene.chunks[k];
        if (!plan) { retexture(chunk, null); return; }
        const draws = kind === "esri" ? esriDraws(options.esriKey!, plan)
          : orthoDraws(ortho!, plan, chunk.hasLine ? corridor(plan.z) : null);
        const canvas = await compose(plan, draws, mine, fill);
        if (!canvas || mine.stopped) return;
        const texture = new CanvasTexture(canvas);
        texture.colorSpace = SRGBColorSpace;
        texture.minFilter = LinearMipmapLinearFilter;
        texture.generateMipmaps = true;
        texture.flipY = true;  // uvOf: v = 1 at the canvas's top
        retexture(chunk, texture, uvOf(meta.affine, plan));
        scene.invalidate();
      }));
      if (loader === mine) { status.hidden = true; loader = null; }
    },
    dispose() {
      loader?.stop();
      loader = null;
      for (const chunk of [...textures.keys()]) retexture(chunk, null);
      scene.credits.remove(IMAGERY_CREDITS);
      scene.credits.remove(DATA_CREDITS);
      box.remove();
    },
  };
  mark(imagery.current);
  void imagery.set(imagery.current);
  return imagery;
}
