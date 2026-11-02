// The 3D view of a line (GET /view3d#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>, web.VIEW3D_HTML): the patch of
// the run's elevation model around the line from /api/patch, decoded (decode.ts, its sha256 checked) and meshed
// into the scene (scene.ts, terrain.ts); then the imagery (imagery.ts) and the found line's profile from
// /api/profile (one request after the other) for the webbing's colour and the readout (line.ts); the walker's
// pin (pin.ts), the walk (walk.ts) and, at level full, the anchors' editing (edit.ts).
// Plain DOM, no Preact: the page is the canvas and a few controls. No style attributes (the CSP's
// style-src 'self'): classes of view3d.css. When the terrain is drawn and the profile is in, the root gets
// data-ready="1" (data-triangles: the last frame's; data-vertices: the meshes'; data-frames: the frames drawn),
// for tests.

import "./view3d.css";
import { detailMessage, t } from "../i18n";
import { esriKey } from "../layers";
import type { Profile } from "../types";
import { decodeValues, inflate, splitAnswer, toHeights, type Patch } from "./decode";
import { createEdit, type Edit } from "./edit";
import { createImagery, type Imagery } from "./imagery";
import { createLine } from "./line";
import { createPin } from "./pin";
import { backUrl, currentPage, patchUrl, type PageRequest } from "./page";
import { createRing, ringUrl, type Ring } from "./ring";
import { createScene, type SceneCore } from "./scene";
import { createWalk } from "./walk";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** The page's frame: the top bar with the way back, the stage of the canvas with its status and credits, the
 *  bar below with the toolbar's row, the readout and the preview's note. */
function frame(root: HTMLElement, page: PageRequest) {
  document.title = t("ui.view3d.title");
  const top = el("header", "v3-top");
  const back = el("a", "u-btn v3-back", t("ui.view3d.back"));
  back.href = backUrl(page);
  top.append(back, el("h1", "v3-title", t("ui.view3d.title")));
  const stage = el("div", "v3-stage"), status = el("div", "v3-status");
  status.setAttribute("role", "status");
  const credits = el("div", "v3-credits v3-hidden");
  credits.setAttribute("aria-label", t("ui.view3d.credits"));
  stage.append(status, credits);
  const bar = el("div", "v3-bar"), toolbar = el("div", "v3-toolbar"), readout = el("div", "v3-readout");
  readout.setAttribute("aria-live", "polite");
  const note = el("p", "v3-note", t("ui.view3d.preview_note"));
  bar.append(readout, toolbar, note);
  if (page.level === "phone") bar.append(el("p", "v3-note", t("ui.view3d.phone_level")));
  root.append(top, stage, bar);
  root.classList.toggle("v3-phone", page.level === "phone");
  return {
    stage, toolbar, credits, readout, bar, note,
    /** A message over the stage (none: hidden); `error`: with the error's title and a Reload button. */
    say(text: string | null, error = false) {
      status.replaceChildren();
      status.className = "v3-status" + (text === null ? " v3-hidden" : "") + (error ? " v3-error" : "");
      if (text === null) return;
      if (error) {
        status.setAttribute("role", "alert");
        status.append(el("b", "v3-error-title", t("ui.view3d.error_title")));
      } else status.append(el("span", "v3-spin"));
      status.append(el("p", "v3-message", text));
      if (error) {
        const reload = el("button", "u-btn", t("ui.view3d.reload"));
        reload.type = "button";
        reload.onclick = () => location.reload();
        status.append(reload);
      }
    },
  };
}

class PageError extends Error {}

async function sha256Hex(body: Uint8Array): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;  // not a secure context: left unchecked
  const digest = await crypto.subtle.digest("SHA-256", body as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function fetchPatch(page: PageRequest): Promise<Patch> {
  let response: Response;
  try {
    response = await fetch(patchUrl(page), {headers: {"X-Findaline-Patch": "1"}});
  } catch (e) {
    throw new PageError((e as Error).message);  // offline, or the server is gone
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new PageError(detailMessage(data.detail, response.statusText || String(response.status)));
  }
  const {meta, body} = splitAnswer(await response.arrayBuffer());
  const sha = await sha256Hex(body);
  if (sha !== null && sha !== meta.sha256) throw new PageError(t("error.patch_damaged"));
  const values = decodeValues(await inflate(body), meta.width, meta.height);
  return {meta, values, ...toHeights(values, meta.width, meta.height, meta.base_dm)};
}

/** A line's profile, `line` "lat1,lon1,lat2,lon2" (as result/model.ts fetchProfile, without the model's module). */
async function fetchProfile(run: string, line: string): Promise<Profile> {
  const response = await fetch("/api/profile?run=" + encodeURIComponent(run) + "&line=" +
                               encodeURIComponent(line), {headers: {"X-Findaline-Profile": "1"}});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailMessage(body.detail, response.statusText || "error"));
  return body as Profile;
}

async function start() {
  const root = document.getElementById("view3d");
  if (!root) return;
  const page = currentPage(), ui = frame(root, page);
  if (!page.run || !page.line) { ui.say(t("error.patch_line"), true); return; }
  ui.say(t("ui.view3d.loading_terrain"));
  let scene: SceneCore | null = null, imagery: Imagery | null = null, ring: Ring | null = null;
  const lost = () => ui.say(t("ui.view3d.context_lost"), true);
  addEventListener("pagehide", () => {
    ring?.dispose();
    ring = null;
    imagery?.dispose();
    imagery = null;
    scene?.dispose();
  });
  addEventListener("pageshow", (e) => { if (e.persisted) location.reload(); });  // back from the cache: disposed
  let patch: Patch;
  try {
    patch = await fetchPatch(page);
  } catch (e) {
    ui.say(e instanceof PageError ? e.message : t("error.patch_damaged"), true);
    console.error(e);
    return;
  }
  try {
    scene = createScene(patch, page.level, ui, lost);
  } catch (e) {
    ui.say(t("ui.view3d.no_webgl"), true);
    console.error(e);
    return;
  }
  const line = createLine(scene, ui.readout);
  let edit: Edit | null = null;
  if (line) {
    const walk = createWalk(scene, line, root);
    createPin(scene, line, root, () => walk.stop());
    edit = createEdit(scene, line, root, (l) => fetchProfile(page.run, l), () => walk.stop(),
                      {parent: ui.bar, before: ui.note.nextElementSibling});
  }
  root.dataset.vertices = String(scene.terrain.vertices);
  root.dataset.maxError = String(scene.terrain.maxError);
  let terrainDrawn = false, profileIn = false, frames = 0;
  const ready = () => { if (terrainDrawn && profileIn) root.dataset.ready = "1"; };
  scene.view.onDrawn(() => {
    root.dataset.triangles = String(scene!.view.renderer.info.render.triangles);
    root.dataset.frames = String(++frames);
    if (!terrainDrawn) {
      terrainDrawn = true;
      ui.say(null);
      imagery = createImagery(scene!, {runId: page.run, esriKey: esriKey()});
      const url = ringUrl();
      if (url) ring = createRing(scene!, imagery, url);
      ready();
    }
  });
  scene.invalidate();
  try {
    const profile = await fetchProfile(page.run, page.line);
    edit?.found(profile);
  } catch (e) {
    edit?.found(null);
    root.dataset.profileError = (e as Error).message;
    console.error(e);
  }
  profileIn = true;
  ready();
}

start();
