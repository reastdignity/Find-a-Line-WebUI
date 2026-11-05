// The 3D view of a line (GET /view3d#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>, web.VIEW3D_HTML): the patch of
// the run's elevation model around the line from /api/patch, decoded (decode.ts, its sha256 checked) and meshed
// into the scene (scene.ts, terrain.ts); then the imagery (imagery.ts) and the found line's profile from
// /api/profile (one request after the other) for the webbing's colour and the readout (line.ts); the walker's
// pin (pin.ts), the walk (walk.ts), at level full the anchors' editing (edit.ts), and the walker's views
// (views.ts: orbit, the walker's eyes, behind the walker). Until the terrain is drawn the status over the stage
// names the loading's stage (Stage: the server, the download with its bytes, unpacking, building the mesh) with
// a bar; the imagery counts its tiles in the toolbar (imagery.ts).
// Plain DOM, no Preact: the page is the canvas and a few controls. No style attributes (the CSP's
// style-src 'self'): classes of view3d.css. When the terrain is drawn and the profile is in, the root gets
// data-ready="1" (data-triangles: the last frame's; data-vertices: the meshes'; data-frames: the frames drawn),
// for tests.

import "./view3d.css";
import { download } from "../download";
import { detailMessage, t } from "../i18n";
import { esriKey } from "../layers";
import { nextPaint } from "../paint";
import { measure, timed } from "../perf";
import type { Profile } from "../types";
import { decodeValues, inflate, splitAnswer, toHeights, type Patch } from "./decode";
import { createCanopy } from "./canopy";
import { createEdit, type Edit } from "./edit";
import { createImagery, type Imagery } from "./imagery";
import { createLine } from "./line";
import { createOthers } from "./otherlines";
import { createPin } from "./pin";
import { backUrl, currentPage, patchUrl, viewUrl, type PageRequest } from "./page";
import { createProfileCard } from "./profilecard";
import { createRing, ringUrl, type Ring } from "./ring";
import { createSave, currentOf } from "./save";
import { createScene, type SceneCore } from "./scene";
import { createViews } from "./views";
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
  const copy = el("button", "u-btn v3-copy", t("ui.view3d.copy_link"));
  copy.type = "button";
  top.append(back, el("h1", "v3-title", t("ui.view3d.title")), copy);
  const stage = el("div", "v3-stage"), status = el("div", "v3-status");
  status.setAttribute("role", "status");
  const credits = el("div", "v3-credits v3-hidden");
  credits.setAttribute("aria-label", t("ui.view3d.credits"));
  // Round 2's chrome over the stage (chrome.ts): the activity pill, the tool strip, and at the bottom the
  // credits with the card's slot under them (the card lies on the canvas: the canvas keeps its size)
  const activity = el("div", "v3-activity v3-hidden"), tools = el("div", "v3-tools");
  activity.setAttribute("role", "status");
  tools.setAttribute("role", "toolbar");
  tools.setAttribute("aria-label", t("ui.view3d.tools"));
  const bottom = el("div", "v3-bottom"), card = el("div", "v3-card");
  bottom.append(credits, card);
  stage.append(status, activity, tools, bottom);
  const bar = el("div", "v3-bar"), toolbar = el("div", "v3-toolbar"), readout = el("div", "v3-readout");
  readout.setAttribute("aria-live", "polite");
  const note = el("p", "v3-note", t("ui.view3d.preview_note"));
  bar.append(readout, toolbar, note);
  if (page.level === "phone") bar.append(el("p", "v3-note v3-phone-note", t("ui.view3d.phone_level")));
  root.append(top, stage, bar);
  root.classList.toggle("v3-phone", page.level === "phone");
  // The loading's message and bar while the status shows a stage (progress), made once and changed in place
  let staged: {message: HTMLElement; meter: HTMLElement; fill: HTMLElement} | null = null;
  return {
    stage, toolbar, credits, readout, bar, note, activity, tools, card, top, back, copy,
    /** A stage of the loading over the stage: its message and a bar of `fraction` (null: moving, the amount
     *  unknown; its width set through the CSSOM, which the CSP allows). The root's data-stage names it (tests). */
    progress(name: Stage, text: string, fraction: number | null) {
      root.dataset.stage = name;
      if (!staged) {
        status.replaceChildren();
        status.className = "v3-status";
        status.setAttribute("role", "status");
        const message = el("p", "v3-message"), meter = el("div", "u-prog v3-prog"), fill = el("i", "");
        meter.setAttribute("role", "progressbar");
        meter.setAttribute("aria-valuemin", "0");
        meter.setAttribute("aria-valuemax", "100");
        meter.append(fill);
        status.append(message, meter);
        staged = {message, meter, fill};
      }
      staged.message.textContent = text;
      staged.meter.classList.toggle("u-busy", fraction === null);
      staged.fill.style.width = fraction === null ? "" : `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`;
      if (fraction === null) staged.meter.removeAttribute("aria-valuenow");
      else staged.meter.setAttribute("aria-valuenow", String(Math.round(fraction * 100)));
    },
    /** A message over the stage (none: hidden); `error`: with the error's title and a Reload button. */
    say(text: string | null, error = false) {
      staged = null;
      if (text === null) root.dataset.stage = "done";
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

/** The link on the clipboard (inside the click: the browser asks for a gesture), the button saying so for a moment;
 *  a refusal (no permission, an insecure page) leaves it as it was. */
function copyLink(button: HTMLButtonElement, url: string) {
  navigator.clipboard?.writeText(url).then(() => {
    button.textContent = t("ui.view3d.link_copied");
    button.dataset.copied = "1";
    setTimeout(() => { button.textContent = t("ui.view3d.copy_link"); button.dataset.copied = ""; }, 2000);
  }, () => { /* refused */ });
}

async function sha256Hex(body: Uint8Array): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;  // not a secure context: left unchecked
  const digest = await crypto.subtle.digest("SHA-256", body as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** The stages of the loading (data-stage): the server computing the patch (its request until the answer's
 *  headers: the quick lane's queue and step 1), its body downloaded, checked and unpacked, the mesh built;
 *  "done" once the terrain is drawn. */
type Stage = "server" | "download" | "unpacking" | "building" | "done";
type OnStage = (name: Stage, text: string, fraction: number | null) => void;

const mb = (bytes: number) => (bytes / 2 ** 20).toFixed(1);

async function fetchPatch(page: PageRequest, onStage: OnStage): Promise<Patch> {
  const asked = performance.now();
  let answered = asked;
  const say = (done: number, total: number | null) => onStage("download", total
    ? t("ui.view3d.loading_download", {done: mb(done), total: mb(total)})
    : t("ui.view3d.loading_download_unknown", {done: mb(done)}), total ? Math.min(1, done / total) : null);
  onStage("server", t("ui.view3d.loading_server"), null);
  let answer;
  try {
    answer = await download(patchUrl(page), "arraybuffer", {
      headers: {"X-Findaline-Patch": "1"},
      onHeaders: (total) => { answered = performance.now(); measure("fal:3d:request", asked); say(0, total); },
      onBytes: say,
    });
  } catch (e) {
    throw new PageError((e as Error).message);  // offline, or the server is gone
  }
  if (answer.status !== 200) {
    let data: {detail?: unknown} = {};
    try { data = JSON.parse(new TextDecoder().decode(answer.body)); } catch { /* not JSON */ }
    throw new PageError(detailMessage(data.detail, String(answer.status)));
  }
  measure("fal:3d:body", answered, {bytes: answer.bytes});
  onStage("unpacking", t("ui.view3d.unpacking"), null);
  const start = performance.now();
  const patch = await decodeAnswer(answer.body);
  measure("fal:3d:decode", start, {width: patch.meta.width, height: patch.meta.height});
  return patch;
}

async function decodeAnswer(answer: ArrayBuffer): Promise<Patch> {
  const {meta, body} = splitAnswer(answer);
  // The heights, then the kinds of the uncertain shore when the meta names their bytes (decode.ts decodePatch
  // does the same without the sha256 checks): each block checked against its sha256
  const n = meta.shore_bytes ?? 0;
  if (n < 0 || n > body.byteLength) throw new PageError(t("error.patch_damaged"));
  const heights = n ? body.subarray(0, body.byteLength - n) : body;
  const shoreBlock = n ? body.subarray(body.byteLength - n) : null;
  const sha = await sha256Hex(heights);
  if (sha !== null && sha !== meta.sha256) throw new PageError(t("error.patch_damaged"));
  if (shoreBlock) {
    const shoreSha = await sha256Hex(shoreBlock);
    if (shoreSha !== null && shoreSha !== meta.shore_sha256) throw new PageError(t("error.patch_damaged"));
  }
  const values = decodeValues(await inflate(heights), meta.width, meta.height);
  const patch: Patch = {meta, values, ...toHeights(values, meta.width, meta.height, meta.base_dm)};
  if (shoreBlock) {
    const kinds = await inflate(shoreBlock);
    if (kinds.byteLength !== meta.width * meta.height) throw new PageError(t("error.patch_damaged"));
    if (kinds.some((k) => k !== 0)) patch.shore = kinds;
  }
  return patch;
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
    patch = await fetchPatch(page, ui.progress);
  } catch (e) {
    ui.say(e instanceof PageError ? e.message : t("error.patch_damaged"), true);
    console.error(e);
    return;
  }
  ui.progress("building", t("ui.view3d.building"), null);
  await nextPaint();  // the stage shown while the mesh is built (up to 1.6 s on a desktop, tools/perf_run_load.py)
  try {
    scene = timed("fal:3d:mesh", () => createScene(patch, page.level, ui, lost));
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
    createViews(scene, line, root, {parent: ui.bar, before: ui.note.nextElementSibling});
    // Round 2: the profile card and saving the line shown (the found line's key is the address's; a moved line's
    // the anchors'), and the links back to the map and to this view follow it
    const current = currentOf(scene.lonLat, line, page.line);
    if (typeof patch.meta.slope === "number" && typeof patch.meta.leash_fall === "number") {
      createProfileCard(scene, line, current, patch.meta);
    }
    const save = createSave(scene, line, page.run, current, ui.readout);
    // The other lines of the view (round 2, point 7): the address's and the user's other saved lines of the run
    const others = createOthers(scene, line, edit, root, {page, current, favourites: save,
                                                          notes: {parent: ui.bar, before: ui.note.nextElementSibling}});
    line.onAnchors(() => { ui.back.href = backUrl(page, current.key()); });
    ui.copy.addEventListener("click", () => copyLink(ui.copy, new URL(
      viewUrl(page, current.key(), location.search, others.also()), location.origin).href));
  } else ui.copy.classList.add("v3-hidden");
  root.dataset.vertices = String(scene.terrain.vertices);
  root.dataset.maxError = String(scene.terrain.maxError);
  let terrainDrawn = false, profileIn = false, frames = 0;
  const ready = () => { if (terrainDrawn && profileIn) root.dataset.ready = "1"; };
  scene.view.onDrawn(() => {
    root.dataset.triangles = String(scene!.view.renderer.info.render.triangles);
    root.dataset.frames = String(++frames);
    if (!terrainDrawn) {
      terrainDrawn = true;
      measure("fal:3d:first-frame", drawStart);
      ui.say(null);
      imagery = createImagery(scene!, {runId: page.run, esriKey: esriKey(), shore: patch.shore ?? null});
      const url = ringUrl();
      if (url) ring = createRing(scene!, imagery, url);
      createCanopy(scene!);  // round 2: trees and buildings, a tool only for a run with a surface model
      ready();
    }
  });
  const drawStart = performance.now();
  scene.invalidate();
  try {
    const profileStart = performance.now();
    const profile = await fetchProfile(page.run, page.line);
    measure("fal:3d:profile", profileStart);
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
