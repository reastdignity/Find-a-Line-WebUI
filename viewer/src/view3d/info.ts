// "About this view" on a phone (docs/3d-view-contract.md, "Step 3c, group B: the phone's layout"; the user,
// 2026-11-19: "A: info button beside \"Data credits\""): where the compact bar shows (the phone level, under
// 600 px, a touch screen at most 480 px high: view3d.css) the bar's notes that explain (the preview's note, the
// phone level's, the hints, what the imagery's control says is drawn) are not shown in the bar; one button in the
// credits' box opens a box over the stage with them. The bar keeps its height when the box opens and when the view
// changes. What failed stays in the bar (the notes of class `v3-alert`, the walk's and the motion's notes).
//
// The notes stay where their modules put them and keep their own state (`v3-hidden`, the views' rules of
// view3d.css); the box holds copies of them, made when it opens and again whenever the bar changes while it is
// open, each with its note's classes, so the same rules show and hide a copy. Closed, the box is empty.
// Plain DOM, no style attributes.

import { t } from "../i18n";
import { kitIcon } from "./icon";

/** The notes of the bar that go into the box. */
export const INFO_NOTES = ".v3-bar > .v3-note:not(.v3-alert), .v3-bar .v3-imagery-note";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export interface Info {
  /** The button, for the credits' box. */
  readonly button: HTMLButtonElement;
  readonly isOpen: boolean;
  open(): void;
  /** Close the box; `focus`: back to the button (a close by the keyboard or the box's own button). */
  close(focus?: boolean): void;
}

/** The button and its box (appended to `stage`), the box's lines copied from `bar`. */
export function createInfo(stage: HTMLElement, bar: HTMLElement): Info {
  const name = t("ui.view3d.info");
  const button = el("button", "u-btn v3-info");
  button.type = "button";
  button.append(kitIcon("info"));
  button.setAttribute("aria-label", name);
  button.title = name;
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", "v3-infobox");
  const box = el("section", "v3-infobox v3-hidden"), head = el("div", "v3-infobox-head");
  box.id = "v3-infobox";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", name);
  const shut = el("button", "u-btn v3-infobox-close");
  shut.type = "button";
  shut.append(kitIcon("close"));
  shut.setAttribute("aria-label", t("ui.view3d.info_close"));
  shut.title = t("ui.view3d.info_close");
  head.append(el("h2", "v3-infobox-title", name), shut);
  const lines = el("div", "v3-infobox-lines");
  box.append(head, lines);
  stage.append(box);

  let open = false;
  const copy = () => {
    lines.replaceChildren(...[...bar.querySelectorAll<HTMLElement>(INFO_NOTES)].map(
      (note) => el("p", "v3-infobox-line " + note.className, note.textContent ?? "")));
  };
  // the bar while the box is open: a note shown, hidden, added or reworded
  const watch = typeof MutationObserver === "function" ? new MutationObserver(copy) : null;
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !open) return;
    // the box first: the same press does not also end "Lines from a point" (point.ts listens on the window)
    e.preventDefault();
    e.stopPropagation();
    self.close(true);
  };
  const self: Info = {
    button,
    get isOpen() { return open; },
    open() {
      if (open) return;
      open = true;
      copy();
      watch?.observe(bar, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["class"]});
      box.classList.remove("v3-hidden");
      button.setAttribute("aria-expanded", "true");
      document.addEventListener("keydown", onKey, true);
      shut.focus();
    },
    close(focus = false) {
      if (!open) return;
      open = false;
      watch?.disconnect();
      document.removeEventListener("keydown", onKey, true);
      box.classList.add("v3-hidden");
      lines.replaceChildren();
      button.setAttribute("aria-expanded", "false");
      if (focus) button.focus();
    },
  };
  button.addEventListener("click", () => { if (open) self.close(); else self.open(); });
  shut.addEventListener("click", () => self.close(true));
  return self;
}
