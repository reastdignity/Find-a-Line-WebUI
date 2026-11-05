// Saving the line of the 3D view into the favourites (docs/3d-view-contract.md, "Round 2", decision 5), and the
// key of the line shown: the found line's, as the address gives it (the 2D result's key, keys.ts lineCoords), or
// the moved anchors' once they were dragged. The values come from the line's profile (favouriteData of the
// measured line); the favourites are the 2D result's own (/api/runs/<run>/favourites), so a saved line shows in
// the list and on the map. Nothing new is stored or sent: a favourite's row as the map writes it.
//
// The pure parts (canonicalKey, lineOfKey, currentOf) are tested in Node (tests/test_view3d_profile.py).

import { favouriteData, loadRunFavourites, saveFavourite } from "../favourites";
import { t } from "../i18n";
import { measuredLine } from "../result/measured";
import type { Line, Profile } from "../types";
import { lineParam } from "./interact";
import type { LineView } from "./line";
import type { SceneCore } from "./scene";
import { readoutOf } from "./webbing";

/** A line's key as the 2D result writes it (JavaScript's numbers, keys.ts lineCoords): "50.1234500,19.5" is
 *  "50.12345,19.5". Both the found line's key and a moved line's go through it. */
export function canonicalKey(key: string): string {
  return key.split(",").map(Number).join(",");
}

/** The line of a key ("lat1,lon1,lat2,lon2") and its profile, as the measured line of the 2D result, `over` from the
 *  profile's verdict (clear over the terrain, not over trees and buildings); null when an anchor has no terrain data
 *  there. Its lineCoords is the key. */
export function lineOfKey(key: string, profile: Profile): Line | null {
  const [lat1, lon1, lat2, lon2] = key.split(",").map(Number);
  try {
    const line = measuredLine([lat1, lon1], [lat2, lon2], profile);
    line.over = readoutOf(profile).overTrees;
    return line;
  } catch {
    return null;
  }
}

/** What the page shows: its key, and its line once the profile is in (the same object while neither changes). */
export interface Current {
  key(): string;
  line(): Line | null;
}

/** The line of `view` (line.ts): the found line's `foundKey` as it is, or while moved the anchors' `lineParam`. */
export function currentOf(lonLat: (x: number, y: number) => [number, number],
                          view: Pick<LineView, "anchors" | "edited" | "profile"> & {key?: string | null},
                          foundKey: string): Current {
  const found = canonicalKey(foundKey);
  let cache: {key: string; profile: Profile; line: Line | null} | null = null;
  const key = () => {
    if (!view.edited) return found;
    if (view.key) return canonicalKey(view.key);  // a line taken from outside under its own key (line.ts)
    const [a, b] = view.anchors;
    return canonicalKey(lineParam(lonLat(a.x, a.y), lonLat(b.x, b.y)));
  };
  return {
    key,
    line() {
      const profile = view.profile;
      if (!profile) return null;
      const k = key();
      if (!cache || cache.key !== k || cache.profile !== profile) cache = {key: k, profile, line: lineOfKey(k, profile)};
      return cache.line;
    },
  };
}

const ICON = "M8 1.8l1.9 4 4.3.5-3.2 3 .9 4.3L8 11.4 4.1 13.6 5 9.3 1.8 6.3l4.3-.5z";

/** The tool `save` (order 6): a toggle for the current line. Hidden until the run's favourites are known, and for
 *  good if that request fails (signed out, a page without favourites). */
export function createSave(scene: SceneCore, view: LineView, runId: string, current: Current, readout: HTMLElement) {
  const button = scene.tools.add({id: "save", label: t("ui.view3d.save"), icon: ICON, order: 6, toggle: true,
                                  onClick: () => { void click(); }});
  button.element.classList.add("v3-hidden");
  const saved = new Set<string>();
  let busy = false, known = false;
  // A failure over the readout, apart from the profile's own (line.ts keeps that one)
  const failure = document.createElement("span");
  failure.className = "v3-read v3-failed v3-save-failed v3-hidden";
  failure.setAttribute("role", "alert");
  readout.append(failure);

  // The readout's "Anchors moved: not saved" becomes "Moved line saved" while the moved line is a favourite
  const edited = () => readout.querySelector<HTMLElement>(".v3-edited");
  const sentence = (savedNow: boolean) => {
    const box = edited();
    if (!box) return;
    const [long, short] = savedNow ? [t("ui.view3d.saved_moved"), t("ui.view3d.saved_moved_short")]
                                   : [t("ui.view3d.edited"), t("ui.view3d.edited_short")];
    const l = box.querySelector(".v3-long"), s = box.querySelector(".v3-short");
    if (l && l.textContent !== long) l.textContent = long;
    if (s && s.textContent !== short) s.textContent = short;
  };

  const refresh = () => {
    if (!known) return;
    const on = saved.has(current.key());
    button.setPressed(on);
    button.setLabel(on ? t("ui.view3d.saved") : view.edited ? t("ui.view3d.save_moved") : t("ui.view3d.save"));
    button.element.disabled = busy || (!on && !current.line());  // saving needs the profile's values
    button.element.dataset.saved = on ? "1" : "";
    sentence(on && view.edited);
  };

  async function click() {
    if (busy) return;
    const key = current.key(), on = !saved.has(key), line = on ? current.line() : null;
    if (on && !line) return;
    busy = true;
    failure.classList.add("v3-hidden");
    refresh();
    try {
      // A removal needs the key alone (saveFavourite writes lineCoords of the line it is given)
      const [lat1, lon1, lat2, lon2] = key.split(",").map(Number);
      await saveFavourite(runId, line ?? {lat1, lon1, lat2, lon2} as Line, on);  // the token of loadRunFavourites
      if (on) saved.add(key); else saved.delete(key);
    } catch (e) {
      failure.textContent = t("ui.view3d.save_failed", {message: (e as Error).message});
      failure.classList.remove("v3-hidden");
    }
    busy = false;
    refresh();
  }

  view.onAnchors(() => { failure.classList.add("v3-hidden"); refresh(); });
  view.onProfile(refresh);
  loadRunFavourites(runId).then((favourites) => {
    for (const k of favourites.lines) saved.add(canonicalKey(k));
    known = true;
    button.element.classList.remove("v3-hidden");
    refresh();
  }, () => button.remove());
  return {saved, refresh};
}
