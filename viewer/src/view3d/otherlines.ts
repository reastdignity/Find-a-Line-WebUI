// Several lines in one view (docs/3d-view-contract.md, "Round 2", point 7): besides the active line, the 3D view
// shows the lines the 2D result handed over in the address (`&also=`, the other lines of the opened line's spot) and,
// with the tool "Saved lines" (order 4, a switch, off at the start, not kept), the user's other favourites of the run
// that lie in the patch. Each is its unloaded webbing alone (2 px, about 60 %: muted, or the colour of its verdict
// where it is known: a line that was the active one) with a label at about 70 % of the line, placed after every frame
// drawn, hidden outside the orbit view (others.css). A click on a label makes that line the active one
// (`Edit.setAnchors(anchors, key)`: the walker, the handles, the profile of that key, saving shows it saved when it
// is a favourite); the line that was active, when it has a key, is drawn among the others from then on, and "Back to
// the found line" works as before. Nothing is stored and nothing is asked: the favourites are those `createSave`
// already has. The root's data-others is the number of other lines drawn. The pure parts are others.ts.

import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { t } from "../i18n";
import type { Anchor3d } from "./decode";
import type { Edit } from "./edit";
import { raised, type Webbing } from "./geometry";
import type { LineView } from "./line";
import { chooseOthers, labelPoint, type Candidate, type Placed } from "./others";
import "./others.css";
import { OTHERS_MAX, canonicalKey, currentPage, type PageRequest } from "./page";
import type { Current, Favourites } from "./save";
import type { SceneCore } from "./scene";
import { overlayOf, place, toScreen } from "./screen";
import { resample, verdictOf, webbing, type Verdict } from "./webbing";

/** The tool's icon: two curves one above the other (the `d` of a path in a 16 × 16 box). */
export const OTHERS_ICON = "M1.5 5.5q6.5 3 13 0M1.5 10.5q6.5 3 13 0";

/** How many lines that were the active one stay among the others (the newest first). */
export const KEPT_MAX = 5;

export interface OthersOptions {
  /** The page's own request (default: `currentPage()`): the found line and the lines of the address. */
  page?: PageRequest;
  /** `save.ts` `currentOf`: the key of the line shown. */
  current: Current;
  /** `createSave`'s answer: the user's favourites of the run. */
  favourites: Favourites;
  /** Where the note "no other saved line in this view" goes (before `before` of `parent`, null: last). */
  notes: {parent: HTMLElement; before: Element | null};
}

export interface Others {
  /** The keys of the other lines drawn now (canonical), in the order they are labelled. */
  drawn(): string[];
  /** The lines of the address and those that were the active one (canonical keys, the newest first), without the line
   *  shown: what "Copy link" carries as `&also=` (page.ts `viewUrl`'s fourth argument). */
  also(): string[];
}

interface Built {
  placed: Placed;
  webbing: Webbing;
  line: Line2;
  span: number;
  at: [number, number, number];
}

const COLOUR_NAME: Record<Verdict | "none", string> = {fits: "clear", terrain_only: "trees", no_fit: "bad", none: "muted"};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** The other lines of `scene`, made active through `edit`; `root` is the page's root (data-others). */
export function createOthers(scene: SceneCore, line: LineView, edit: Edit, root: HTMLElement,
                             options: OthersOptions): Others {
  const page = options.page ?? currentPage(), { current, favourites, notes } = options;
  const found = page.line ? canonicalKey(page.line) : null;
  const address = page.also.slice(0, OTHERS_MAX);
  const kept: string[] = [];                    // lines that were the active one, the newest first
  const verdicts = new Map<string, Verdict>();  // what is known of a line's verdict (its profile was in)
  let activeOther: string | null = null;        // the line taken from the others, while it is the active one
  let favouritesOn = false;

  // The materials: one a colour (the unloaded webbing of line.ts: 2 px at 60 %)
  const materials = new Map<string, LineMaterial>();
  for (const name of Object.values(COLOUR_NAME)) {
    materials.set(name, new LineMaterial({color: scene.token("--" + name), linewidth: 2, transparent: true, opacity: 0.6}));
  }
  scene.view.onResize((size) => { for (const m of materials.values()) m.resolution.copy(size); });

  const container = el("div", "v3-others");
  overlayOf(scene).prepend(container);  // first, so the anchors' handles stand over the labels
  const note = el("p", "v3-note v3-others-note v3-hidden", t("ui.view3d.others_none"));
  note.setAttribute("role", "status");
  notes.parent.insertBefore(note, notes.before);

  const tool = scene.tools.add({id: "others", label: t("ui.view3d.others"), icon: OTHERS_ICON, order: 4, toggle: true,
                                onClick() { favouritesOn = !favouritesOn; refresh(); }});
  tool.element.classList.add("v3-hidden");  // offered once the run has another favourite
  root.dataset.others = "0";

  /** The key of the line shown when it is a known line: the found line's, or the one taken from outside; else null. */
  const activeKey = (): string | null => line.edited ? (line.key ? canonicalKey(line.key) : null) : found;
  const keep = (key: string | null) => {
    if (!key) return;
    const at = kept.indexOf(key);
    if (at >= 0) kept.splice(at, 1);
    kept.unshift(key);
    kept.length = Math.min(kept.length, KEPT_MAX);
  };
  const learn = () => {
    const key = activeKey(), p = line.profile;
    if (key && p) verdicts.set(key, verdictOf(p));
  };

  // What is built for a key (kept: the geometry is cheap, the heights never change) and what is shown now
  const built = new Map<string, Built | null>();
  const labels = new Map<string, {at: HTMLElement; button: HTMLButtonElement}>();
  let shown: Built[] = [];

  const build = (placed: Placed): Built | null => {
    const had = built.get(placed.key);
    if (had !== undefined) return had;
    const ends = raised(placed.anchors, scene.meta.lift);  // on the run's A-frames
    const w = webbing(ends, scene.meta.rigging);
    let made: Built | null = null;
    if (w) {
      const geometry = new LineGeometry(), flat: number[] = [];
      for (const p of resample(w.unloaded)) flat.push(...scene.toScene(...p).toArray());
      geometry.setPositions(flat);
      const l = new Line2(geometry, materials.get("muted")!);
      l.name = "other-line";
      made = {placed, webbing: w, line: l, span: w.span, at: labelPoint(w, ends)};
    }
    built.set(placed.key, made);
    return made;
  };

  const colourOf = (key: string) => COLOUR_NAME[verdicts.get(key) ?? "none"];
  const caption = (b: Built) => {
    const key = b.placed.key, m = String(Math.round(b.span));
    const label = labels.get(key)!;
    label.button.replaceChildren();
    if (favourites.saved.has(key)) label.button.append(el("span", "v3-other-star", "★"));
    label.button.append(el("span", "v3-other-text", t("ui.view3d.other_label", {m})));
    label.button.setAttribute("aria-label", t("ui.view3d.other_make", {m}));
    label.button.title = t("ui.view3d.other_make", {m});
    label.button.dataset.colour = colourOf(key);
    b.line.material = materials.get(colourOf(key))!;
  };

  function refresh() {
    const skip = new Set<string>([canonicalKey(current.key())]);
    const active = activeKey();
    if (active) skip.add(active);
    // the offer: another favourite than the line shown
    const others = favourites.known() && [...favourites.saved].some((k) => !skip.has(canonicalKey(k)));
    tool.element.classList.toggle("v3-hidden", !others);
    tool.setPressed(favouritesOn);
    const candidates: Candidate[] = [
      ...kept.map((key): Candidate => ({key, source: "kept"})),
      ...address.map((key): Candidate => ({key, source: "address"})),
      ...(favouritesOn && favourites.known() ? [...favourites.saved].map((key): Candidate => ({key, source: "favourite"})) : []),
    ];
    const [a, b] = line.anchors;
    const chosen = chooseOthers(candidates, {
      frame: scene.meta, heightAt: (x, y) => scene.heightAt(x, y), exclude: skip, max: OTHERS_MAX,
      middle: {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2},
    });
    const next = chosen.map(build).filter((x): x is Built => x !== null);
    const nextKeys = new Set(next.map((b) => b.placed.key));
    for (const b of shown) {
      if (nextKeys.has(b.placed.key)) continue;
      scene.remove(b.line);
      const label = labels.get(b.placed.key);
      label?.at.remove();
      labels.delete(b.placed.key);
    }
    for (const b of next) {
      const key = b.placed.key;
      if (!labels.has(key)) {
        scene.add(b.line);
        const at = el("div", "v3-other-at v3-hidden"), button = el("button", "v3-other");
        button.type = "button";
        button.dataset.other = key;
        button.addEventListener("click", () => activate(key));
        at.append(button);
        container.append(at);
        labels.set(key, {at, button});
      }
      caption(b);
    }
    shown = next;
    root.dataset.others = String(next.length);
    // the switch is on and none of the favourites lies in this view
    const favouritesDrawn = next.some((b) => favourites.saved.has(b.placed.key));
    note.classList.toggle("v3-hidden", !(favouritesOn && others && !favouritesDrawn));
    scene.invalidate();
  }

  function activate(key: string) {
    const b = built.get(key);
    if (!b) return;
    learn();
    const previous = activeKey(), pending = activeOther;
    if (found !== null && key === found && line.edited) {
      // the found line itself: the page's own way back (its exact anchors and profile, not an edit)
      keep(previous);
      keep(pending);
      activeOther = null;
      scene.toolbar.querySelector<HTMLButtonElement>(".v3-reset")?.click();
      refresh();
      return;
    }
    activeOther = key;
    if (!edit.setAnchors(b.placed.anchors.map((a): Anchor3d => ({...a})) as [Anchor3d, Anchor3d], key)) {
      activeOther = pending;
      return;
    }
    keep(previous);
    if (pending && pending !== key) keep(pending);
    refresh();
  }

  // The active line changed: a known line left is drawn among the others; a reset ends the stay of the one taken
  let identity = "";
  const identityOf = () => line.edited ? "e:" + (line.key ?? "") : "found";
  line.onAnchors((_anchors, edited) => {
    if (!edited && activeOther) { keep(activeOther); activeOther = null; }
    const now = identityOf();
    if (now === identity) return;  // the anchors of a dragged line moving: nothing to redo
    identity = now;
    refresh();
  });
  line.onProfile(() => { learn(); for (const b of shown) caption(b); scene.invalidate(); });
  favourites.onChange(refresh);

  // Labels follow the lines after each frame drawn
  scene.view.onDrawn(() => {
    for (const b of shown) {
      const label = labels.get(b.placed.key);
      if (label) place(label.at, toScreen(scene, scene.toScene(...b.at)));
    }
  });

  identity = identityOf();
  refresh();
  scene.onDispose(() => {
    for (const b of built.values()) b?.line.geometry.dispose();
    for (const m of materials.values()) m.dispose();
    container.remove();
    note.remove();
    tool.remove();
  });
  return {
    drawn: () => shown.map((b) => b.placed.key),
    also() {
      const skip = new Set([canonicalKey(current.key())]);
      const active = activeKey();
      if (active) skip.add(active);
      const out: string[] = [];
      for (const key of [...kept, ...address]) if (!skip.has(key) && !out.includes(key)) out.push(key);
      return out.slice(0, OTHERS_MAX);
    },
  };
}
