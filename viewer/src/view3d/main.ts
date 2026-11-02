// The 3D view of a line (GET /view3d#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>, web.VIEW3D_HTML): the patch of
// the run's elevation model around the line from /api/patch, decoded (decode.ts) and meshed (terrain.ts)
// into a three.js view (view.ts). Wave 1: the first chunk as a plain shaded mesh; the scene (all chunks,
// imagery, webbing, the walker, editing) comes as its own module. Plain DOM, no Preact: the page is the
// canvas and a few controls. No style attributes (the CSP's style-src 'self'): classes of view3d.css.

import "./view3d.css";
import { detailMessage, t } from "../i18n";
import { decodePatch, type Patch } from "./decode";
import { originOf, sampleXY, toScene } from "./geometry";
import { backUrl, currentPage, patchUrl, type PageRequest } from "./page";
import { chunkMesh } from "./terrain";
import { createView, terrainMesh, type View } from "./view";

/** Martini's error allowed per level, in metres. */
const MAX_ERROR = {full: 0.5, phone: 1.5};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** The page's frame: the top bar with the way back, the stage of the canvas and its status. */
function frame(root: HTMLElement, page: PageRequest) {
  document.title = t("ui.view3d.title");
  const top = el("header", "v3-top");
  const back = el("a", "u-btn v3-back", t("ui.view3d.back"));
  back.href = backUrl(page);
  top.append(back, el("h1", "v3-title", t("ui.view3d.title")));
  const stage = el("div", "v3-stage"), status = el("div", "v3-status");
  status.setAttribute("role", "status");
  stage.append(status);
  root.append(top, stage);
  return {
    stage,
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

class PatchError extends Error {}

async function fetchPatch(page: PageRequest): Promise<Patch> {
  let response: Response;
  try {
    response = await fetch(patchUrl(page), {headers: {"X-Findaline-Patch": "1"}});
  } catch (e) {
    throw new PatchError((e as Error).message);  // offline, or the server is gone
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new PatchError(detailMessage(data.detail, response.statusText || String(response.status)));
  }
  return decodePatch(await response.arrayBuffer());
}

/** The first chunk as a plain shaded mesh, the camera on its centre from the south-west. */
function draw(view: View, patch: Patch, page: PageRequest) {
  const origin = originOf(patch.meta);
  view.add(terrainMesh(chunkMesh(patch, origin, 0, 0, MAX_ERROR[page.level])));
  const last = Math.min(patch.meta.width, patch.meta.height, 513) - 1;
  const [x, y] = sampleXY(patch.meta, last / 2, last / 2);
  const {anchors} = patch.meta, h = (anchors[0].h + anchors[1].h) / 2;
  const target = toScene(origin, x, y, h), far = last * patch.meta.res * 0.9;
  view.look([target[0] - far * 0.6, target[1] + far * 0.6, target[2] + far * 0.6], target);
}

async function start() {
  const root = document.getElementById("view3d");
  if (!root) return;
  const page = currentPage(), ui = frame(root, page);
  if (!page.run || !page.line) { ui.say(t("error.patch_line"), true); return; }
  ui.say(t("ui.view3d.loading_terrain"));
  let view: View;
  try {
    view = createView(ui.stage, page.level, () => ui.say(t("ui.view3d.context_lost"), true));
  } catch {
    ui.say(t("ui.view3d.no_webgl"), true);
    return;
  }
  try {
    const patch = await fetchPatch(page);
    draw(view, patch, page);
    ui.say(null);
  } catch (e) {
    ui.say(e instanceof PatchError ? e.message : t("error.patch_damaged"), true);
    console.error(e);
  }
}

start();
