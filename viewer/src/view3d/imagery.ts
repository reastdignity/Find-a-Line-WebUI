// The imagery of the 3D view (docs/3d-view-contract.md, "Wave 2", V2b): the run's national orthophoto (our cache
// first where it may have the tiles, else its service), Esri's satellite imagery (with the operator's key), or
// the terrain shaded, or its "Edges" look (wave E: scene-api.ts setEdges, where the browser can draw it). Each chunk gets one canvas of its tiles (tiles.ts: the zoom, the URLs, the UVs) as its
// texture; the control is a segmented one in the scene's toolbar (a select on narrow screens), the tiles loaded
// are counted in the activity pill of the stage (`scene.activity`, entry "imagery"), the credits go to the scene's
// credits box (credits.ts). Plain DOM, no style attributes (the CSP's style-src 'self'): classes of ui.css. The page's
// root gets data-imagery="<kind>" (for tests).

import { CanvasTexture, LinearMipmapLinearFilter, SRGBColorSpace } from "three";
import { t } from "../i18n";
import { measure } from "../perf";
import { orthoForApp } from "../result/load";
import type { Ortho } from "../types";
import { DATA_CREDITS, DATA_ORDER, dataCredits, IMAGERY_CREDITS, IMAGERY_ORDER, imageryCredits } from "./credits";
import type { Chunk, Scene3D } from "./scene-api";
import { drawShore, shoreWithin } from "./shore";
import {
  cacheBusted, corridorOf, dataBounds, esriDraws, orthoDraws, orthoOf, planTextures, TILE_PX, uvOf, whiteBlocks,
  type Composed, type TexturePlan, type TileDraw, type TileImage,
} from "./tiles";

export type ImageryKind = "ortho" | "esri" | "shaded" | "edges";

export interface Imagery {
  /** The kinds this run can show, the default first. */
  available: ImageryKind[];
  current: ImageryKind;
  set(kind: ImageryKind): Promise<void>;
  /** Calls `fn` with the new kind whenever the imagery is switched; returns the unsubscribe. */
  onChange(fn: (kind: ImageryKind) => void): () => void;
  dispose(): void;
}

/** Images loaded at once (the browser's limit per host is about six). */
const PARALLEL = 6;
/** The activity pill's count of the tiles loaded changes at most this often (ms). */
const COUNT_MS = 250;
/** What a WMS's tile is laid on (orthophoto._on_white): its parts without imagery in a PNG answer. */
const WHITE = "#ffffff";

const LABELS: Record<ImageryKind, string> = {
  ortho: "ui.view3d.imagery_ortho", esri: "ui.view3d.imagery_esri", shaded: "ui.view3d.imagery_shaded",
  edges: "ui.view3d.imagery_edges",
};

/** A service's images failing this many times in a row mean it refuses us (a block, an outage): its other images
 *  are not asked for, since asking on would only hammer it. */
export const REFUSED_AFTER = 8;

/** Loads images a few at a time; `stop` drops what waits and cancels what loads. */
class Loader {
  private waiting: (() => void)[] = [];
  private active = new Set<HTMLImageElement>();
  private running = 0;
  private failures = 0;
  stopped = false;
  /** The service failed REFUSED_AFTER times in a row: its images still waiting and any asked later come back
   *  null without a request (our own cache's are still loaded). */
  refused = false;

  /** An image with CORS (`crossOrigin` before `src`, so the canvas stays clean), null when it fails; `service`:
   *  one of a service, not asked for once the service refuses; `first`: it waits ahead of the others (a second
   *  try: a tile is settled before more tiles are begun, so a refusing service is known after a few tiles). */
  load(url: string, service = false, first = false): Promise<HTMLImageElement | null> {
    return new Promise((resolve) => {
      const run = () => {
        if (this.stopped || (service && this.refused)) { resolve(null); return; }
        if (this.running >= PARALLEL) { if (first) this.waiting.unshift(run); else this.waiting.push(run); return; }
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
      run();
    });
  }

  /** A service's image: asked once more past the browser's cache when it fails (a CORS failure of a response
   *  the 2D map cached without `Vary: Origin` looks like any error). REFUSED_AFTER of them failing in a row (a
   *  success between starts the count again) stop the service's requests of this loader. */
  async service(url: string): Promise<HTMLImageElement | null> {
    if (this.refused) return null;
    const img = await this.load(url, true) ?? (this.stopped ? null : await this.load(cacheBusted(url), true, true));
    if (this.stopped || this.refused) return img;
    if (img) this.failures = 0;
    else if (++this.failures >= REFUSED_AFTER) {
      this.refused = true;
      // what waits: the service's come back null at once, our cache's start or wait again
      for (const run of this.waiting.splice(0)) run();
    }
    return img;
  }

  stop() {
    this.stopped = true;
    for (const run of this.waiting.splice(0)) run();
    for (const img of this.active) img.src = "";
  }
}

function drawImage(ctx: CanvasRenderingContext2D, img: HTMLImageElement, part: TileImage, dx: number, dy: number) {
  if (part.white) {  // a PNG answered for a JPEG: its parts without imagery white, as in our cache
    ctx.fillStyle = WHITE;
    ctx.fillRect(dx, dy, TILE_PX, TILE_PX);
  }
  if (part.crop) {
    const [sx, sy, size] = part.crop;
    ctx.drawImage(img, sx, sy, size, size, dx, dy, TILE_PX, TILE_PX);
  } else ctx.drawImage(img, dx, dy, TILE_PX, TILE_PX);
}

/** (all white, any white 8×8 block) of a WMS's JPEG drawn on `probe`, a 256 px canvas, over white as the server
 *  lays a PNG answer (orthophoto._on_white); null when its pixels cannot be read (a tainted canvas, no 2D
 *  context). */
function whiteOf(probe: HTMLCanvasElement, img: HTMLImageElement): [boolean, boolean] | null {
  try {
    const ctx = probe.getContext("2d", {willReadFrequently: true});
    if (!ctx) return null;
    ctx.fillStyle = WHITE;
    ctx.fillRect(0, 0, TILE_PX, TILE_PX);
    ctx.drawImage(img, 0, 0, TILE_PX, TILE_PX);
    return whiteBlocks(ctx.getImageData(0, 0, TILE_PX, TILE_PX).data, TILE_PX, TILE_PX);
  } catch {
    return null;
  }
}

/** A tile of a WMS over base tiles as orthophoto.tile_content composes our cache's (tiles.ts Composed): the JPEG
 *  alone where it has imagery throughout; the base where it is all white; the base with the transparent PNG over
 *  it where a white block shows the coverage's edge, or where the JPEG fails or its pixels cannot be read. */
async function drawComposed(ctx: CanvasRenderingContext2D, c: Composed, loader: Loader, probe: HTMLCanvasElement,
                            dx: number, dy: number): Promise<boolean> {
  const jpeg = await loader.service(c.jpeg.url);
  const white = jpeg ? whiteOf(probe, jpeg) : null;
  if (jpeg && white && !white[0] && !white[1]) { drawImage(ctx, jpeg, c.jpeg, dx, dy); return true; }
  const parts = white && white[0] ? [c.base] : [c.base, c.png];
  const images = await Promise.all(parts.map((part) => loader.service(part.url)));
  images.forEach((img, k) => { if (img) drawImage(ctx, img, parts[k], dx, dy); });  // bottom first
  return images.some((img) => img !== null);
}

/** One chunk's canvas: the shaded terrain's colour under the tiles (a tile that fails leaves it), each tile from
 *  our cache when worth trying, else from the service (composed, or its layers); `failed`: the tiles nothing was
 *  drawn of. Null when stopped. */
async function compose(plan: TexturePlan, draws: TileDraw[], loader: Loader, fill: string,
                       hatch?: (ctx: CanvasRenderingContext2D) => void,
                       onTile?: () => void): Promise<{canvas: HTMLCanvasElement; failed: number} | null> {
  const canvas = document.createElement("canvas");
  canvas.width = plan.width;
  canvas.height = plan.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, plan.width, plan.height);
  const probe = document.createElement("canvas");  // a WMS's JPEG drawn alone, for its white test
  probe.width = probe.height = TILE_PX;
  const draw = async (d: TileDraw): Promise<boolean> => {
    const dx = d.x * TILE_PX - plan.px0, dy = d.y * TILE_PX - plan.py0;
    const cached = d.cache ? await loader.load(d.cache) : null;  // ours: same origin, no CORS retry
    if (cached) { ctx.drawImage(cached, dx, dy, TILE_PX, TILE_PX); return true; }
    if (d.composed) return drawComposed(ctx, d.composed, loader, probe, dx, dy);
    const images = await Promise.all(d.layers.map((part) => loader.service(part.url)));
    images.forEach((img, k) => { if (img) drawImage(ctx, img, d.layers[k], dx, dy); });  // bottom first
    return images.some((img) => img !== null);
  };
  let failed = 0;
  await Promise.all(draws.map(async (d) => { if (!await draw(d)) failed++; onTile?.(); }));
  if (loader.stopped) return null;
  hatch?.(ctx);  // the uncertain shore over the imagery
  return {canvas, failed};
}

/** The activity entry of the tiles being loaded (round 2: the pill of the stage's top, chrome.ts). */
const ACTIVITY = "imagery";
/** The pill's notice of tiles that could not be loaded, with "Try again". */
const FAILED = "imagery-failed";

/** The imagery of `scene`: its control in `scene.toolbar`, its tiles counted in `scene.activity`, its credits in
 *  `scene.credits`. */
export function createImagery(scene: Scene3D, options: { runId: string; esriKey: string | null;
                                                        shore?: Uint8Array | null }): Imagery {
  const {meta} = scene;
  const shore = options.shore ?? null;  // the kinds of the uncertain shore (decode.ts), hatched on the textures
  const ortho: Ortho | null = orthoForApp(orthoOf(meta.ortho), options.runId);
  const available: ImageryKind[] = [...(ortho ? ["ortho" as const] : []), ...(options.esriKey ? ["esri" as const] : []),
                                    "shaded", ...(scene.edgesSupported ? ["edges" as const] : [])];
  const root = scene.toolbar.closest?.<HTMLElement>(".ui") ?? null;
  const data = dataCredits(meta.attribution, options.runId);
  if (data) scene.credits.set(DATA_CREDITS, data, DATA_ORDER);

  // The textures' plans, once: the line's chunks first (they are looked at first)
  const order = scene.chunks.map((c, k) => k).sort((a, b) => Number(scene.chunks[b].hasLine) - Number(scene.chunks[a].hasLine));
  const plans = planTextures(meta.affine, scene.chunks.map((c) => ({bounds: dataBounds(meta, c.bounds), hasLine: c.hasLine})),
                             scene.level);
  // The hatching of a chunk: its shore's samples on its plan's canvas, none when the chunk holds none
  const hatchOf = (k: number): ((ctx: CanvasRenderingContext2D) => void) | undefined => {
    const bounds = dataBounds(meta, scene.chunks[k].bounds), plan = plans[k];
    if (!shore || !bounds || !plan || !shoreWithin(shore, meta, bounds)) return undefined;
    return (ctx) => { drawShore(ctx, shore, meta, plan, bounds); };
  };
  const corridors = new Map<number, ReturnType<typeof corridorOf>>();
  const corridor = (z: number) => {
    if (!corridors.has(z)) corridors.set(z, corridorOf(meta.affine, meta.anchors, z));
    return corridors.get(z)!;
  };
  const textures = new Map<Chunk, CanvasTexture>();
  const listeners = new Set<(kind: ImageryKind) => void>();
  let loader: Loader | null = null;

  // The control: a segmented one when there is a choice, a native select instead under 600 px (view3d.css shows
  // one of them, the other is out of the accessibility tree; both show imagery.current), and the note that the
  // terrain is shaded when there is no imagery (Shaded and Edges only, or Shaded alone)
  const box = document.createElement("div");
  box.className = "u-row";
  const buttons = new Map<ImageryKind, HTMLButtonElement>();
  let select: HTMLSelectElement | null = null;
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
    const choice = select = document.createElement("select");
    choice.className = "u-input v3-select";
    choice.setAttribute("aria-label", t("ui.view3d.imagery"));
    for (const kind of available) {
      const option = document.createElement("option");
      option.value = kind;
      option.textContent = t(LABELS[kind]);
      choice.append(option);
    }
    choice.onchange = () => { void imagery.set(choice.value as ImageryKind); };
    box.append(seg, choice);
  }
  if (!available.includes("ortho") && !available.includes("esri")) {
    const note = document.createElement("span");
    note.className = "u-small v3-imagery-note";
    note.textContent = t("ui.view3d.no_imagery");
    box.append(note);
  }
  if (shore) {  // what the hatching means (the Edges look draws none)
    const note = document.createElement("span");
    note.className = "u-small v3-imagery-note v3-shore-note";
    note.textContent = t("ui.view3d.shore_hatched");
    box.append(note);
  }
  // Tiles that could not be loaded: how many, or that the service refuses us, with a way to ask again, as a notice
  // of the activity pill (none while all is well; the root's data-imagery-failed is their number)
  let noticed = false;  // the notice is in the pill's place (FAILED), where the loading's count stood
  const failed = (count: number, total: number, refused: boolean) => {
    if (count) {
      scene.activity.notice(FAILED, refused ? t("ui.view3d.imagery_refused")
        : t("ui.view3d.imagery_failed", {failed: count, total}),
                            {label: t("ui.view3d.imagery_retry"), onClick: () => { void imagery.set(imagery.current); }});
    } else if (noticed) scene.activity.clear(FAILED);
    noticed = count > 0;
    if (root) { if (count) root.dataset.imageryFailed = String(count); else delete root.dataset.imageryFailed; }
  };
  scene.toolbar.append(box);

  const mark = (kind: ImageryKind) => {
    buttons.forEach((b, k) => {
      b.className = k === kind ? "u-on" : "";
      b.setAttribute("aria-checked", String(k === kind));
    });
    if (select) select.value = kind;
  };

  const retexture = (chunk: Chunk, texture: CanvasTexture | null, uv?: (x: number, y: number) => [number, number],
                     lit = false) => {
    chunk.setTexture(texture, uv, lit);
    textures.get(chunk)?.dispose();
    if (texture) textures.set(chunk, texture); else textures.delete(chunk);
  };

  // The 2D map's terrain colour (tokens.css, under the page's .ui root) where a tile is missing
  const fillColour = () => getComputedStyle(scene.toolbar).getPropertyValue("--terrain").trim() || "#bba680";

  // A chunk shaded: with uncertain shore (`hatched`) the terrain's colour with the hatching as a texture that
  // multiplies the shading (lit); else no texture
  const shade = (chunk: Chunk, k: number, hatched: boolean, fill: string) => {
    const hatch = hatched ? hatchOf(k) : undefined, plan = plans[k];
    if (!hatch || !plan) { retexture(chunk, null); return; }
    const canvas = document.createElement("canvas");
    canvas.width = plan.width;
    canvas.height = plan.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) { retexture(chunk, null); return; }
    ctx.fillStyle = fill;
    ctx.fillRect(0, 0, plan.width, plan.height);
    hatch(ctx);
    const texture = new CanvasTexture(canvas);
    texture.colorSpace = SRGBColorSpace;
    texture.minFilter = LinearMipmapLinearFilter;
    texture.generateMipmaps = true;
    texture.flipY = true;
    retexture(chunk, texture, uvOf(meta.affine, plan), true);
  };

  const imagery: Imagery = {
    available,
    current: available[0],
    async set(kind: ImageryKind) {
      if (!available.includes(kind)) return;
      loader?.stop();
      const changed = imagery.current !== kind;
      imagery.current = kind;
      mark(kind);
      if (root) root.dataset.imagery = kind;
      const credit = kind === "edges" ? null : imageryCredits(kind, ortho);
      if (credit) scene.credits.set(IMAGERY_CREDITS, credit, IMAGERY_ORDER); else scene.credits.remove(IMAGERY_CREDITS);
      failed(0, 0, false);
      if (kind === "shaded" || kind === "edges") {
        loader = null;
        scene.activity.clear(ACTIVITY);
        const fill = fillColour();
        // Shaded: the chunks with uncertain shore hatched; the others, and the Edges look, without a texture
        scene.chunks.forEach((chunk, k) => shade(chunk, k, kind === "shaded", fill));
        if (available.includes("edges")) scene.setEdges(kind === "edges");
        if (changed) for (const fn of [...listeners]) fn(kind);
        scene.invalidate();
        return;
      }
      if (available.includes("edges")) scene.setEdges(false);
      if (changed) for (const fn of [...listeners]) fn(kind);
      const mine = loader = new Loader(), fill = fillColour(), start = performance.now();
      // Every chunk's tiles first, so the pill counts them all from the start (at most every COUNT_MS: it is a
      // live region)
      const work = order.map((k) => {
        const plan = plans[k], chunk = scene.chunks[k];
        const draws = !plan ? [] : kind === "esri" ? esriDraws(options.esriKey!, plan)
          : orthoDraws(ortho!, plan, chunk.hasLine ? corridor(plan.z) : null);
        return {k, plan, chunk, draws};
      });
      const tiles = work.reduce((n, w) => n + w.draws.length, 0);
      let loaded = 0, counted = 0;
      const count = () => {
        counted = performance.now();
        if (tiles) scene.activity.set(ACTIVITY, t("ui.view3d.activity_imagery", {done: loaded, total: tiles}), loaded / tiles);
        else scene.activity.clear(ACTIVITY);
      };
      const onTile = () => {
        if (loader !== mine) return;
        loaded++;
        if (loaded === tiles || performance.now() - counted >= COUNT_MS) count();
      };
      count();
      let missing = 0;
      // Chunk by chunk, the line's first; each keeps its last texture until its new one is ready
      await Promise.all(work.map(async ({k, plan, chunk, draws}) => {
        if (!plan) { retexture(chunk, null); return; }
        const composed = await compose(plan, draws, mine, fill, hatchOf(k), onTile);
        if (!composed || mine.stopped) return;
        missing += composed.failed;
        // none of its tiles came: shaded as the Shaded look draws it, not a flat picture of the terrain's colour
        if (draws.length && composed.failed === draws.length) { shade(chunk, k, true, fill); scene.invalidate(); return; }
        const canvas = composed.canvas;
        const texture = new CanvasTexture(canvas);
        texture.colorSpace = SRGBColorSpace;
        texture.minFilter = LinearMipmapLinearFilter;
        texture.generateMipmaps = true;
        texture.flipY = true;  // uvOf: v = 1 at the canvas's top
        retexture(chunk, texture, uvOf(meta.affine, plan));
        scene.invalidate();
      }));
      if (loader === mine) {
        scene.activity.clear(ACTIVITY);
        loader = null;
        failed(missing, tiles, mine.refused);
        measure("fal:3d:imagery", start, {kind, tiles, failed: missing});
      }
    },
    onChange(fn) {
      listeners.add(fn);
      return () => { listeners.delete(fn); };
    },
    dispose() {
      listeners.clear();
      loader?.stop();
      loader = null;
      scene.activity.clear(ACTIVITY);
      failed(0, 0, false);
      for (const chunk of [...textures.keys()]) retexture(chunk, null);
      scene.credits.remove(IMAGERY_CREDITS);
      scene.credits.remove(DATA_CREDITS);
      box.remove();
      if (root) delete root.dataset.imagery;
    },
  };
  mark(imagery.current);
  void imagery.set(imagery.current);
  return imagery;
}
