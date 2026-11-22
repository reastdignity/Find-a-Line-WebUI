// "About this view" on a phone (docs/3d-view-contract.md, "Step 3c, group B: the phone's layout"; the user,
// 2026-11-19: "A: info button beside \"Data credits\""): on phones (the phone level, a touch screen at most
// 600 px wide or at most 480 px high: view3d.css; never a mouse window at the full level, which keeps its lines) the
// bar's notes that explain (the preview's note, the
// phone level's, the hints, what the imagery's control says is drawn) are not shown in the bar; one button in the
// credits' box opens a box over the stage with them. The bar keeps its height when the box opens and when the view
// changes. What failed stays in the bar (the notes of class `v3-alert`, the walk's and the motion's notes), and so
// does the preview note's safety sentence "Check every line on the spot" (the user, 2026-11-20: "Keep that one
// sentence in the bar"), one line under the controls.
//
// The notes stay where their modules put them and keep their own state (`v3-hidden`, the views' rules of
// view3d.css); the box holds copies of them, made when it opens and again whenever the bar changes while it is
// open, each with its note's classes, so the same rules show and hide a copy. Closed, the box is empty. Open, it
// is as high as its notes, and the credits' box is hidden where the box would overlap it (the class `v3-covered`).
// Plain DOM, no style attributes.

import { t } from "../i18n";
import { kitIcon } from "./icon";

/** The notes of the bar that go into the box, and the part of a note that stays in the bar instead (the preview's
 *  note keeps its sentence "Check every line on the spot" in sight: the box's copy is without it, so nothing is
 *  said twice). */
export const INFO_NOTES = ".v3-bar > .v3-note:not(.v3-alert), .v3-bar .v3-imagery-note";
export const INFO_KEPT = ".v3-check";

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
  box.tabIndex = -1;  // a press on the box's own text keeps the focus in the box
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", name);
  const shut = el("button", "u-ib u-x v3-infobox-close");
  shut.type = "button";
  shut.append(kitIcon("close"));
  shut.setAttribute("aria-label", t("ui.view3d.info_close"));
  shut.title = t("ui.view3d.info_close");
  head.append(el("h2", "v3-infobox-title", name), shut);
  const lines = el("div", "v3-infobox-lines");
  box.append(head, lines);
  stage.append(box);

  let open = false;
  // The box and the credits' box both stand in the stage's bottom right corner (view3d.css). While the box is open,
  // the credits' box is hidden where the box would overlap it, so the box's edge cuts no line of the credits and the
  // box stays as high as its notes (the design review's P9: it grew to the credits' top before, up to 439 px for three
  // sentences); where the credits stand clear above the box (above an open card) they stay, with the pressed button.
  // Hidden by `visibility` (the class v3-covered): their place and size stay, so the test cannot feed itself and
  // what is placed by their box (optionlist.ts fit, the pin) does not move; their controls leave the Tab order
  const hide = () => {
    const c = button.closest<HTMLElement>(".v3-credits");
    if (!c) return;
    let over = false;
    if (open) {
      const a = c.getBoundingClientRect(), b = box.getBoundingClientRect();
      over = a.height > 0 && b.height > 0 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5 &&
        Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5;
    }
    c.classList.toggle("v3-covered", over);
  };
  // What the page shows changed while the box is open: the box no longer shown (the window grew past the phone's
  // width, a turn: view3d.css hides it) closes, so no Escape is spent on a box out of sight; else the credits are
  // tested again (the credits opened or folded, the card, a turn). In the next frame, never inside the observer's
  // own call
  let frame = 0;
  const sizes = typeof ResizeObserver === "function" ? new ResizeObserver(() => {
    if (!frame) frame = requestAnimationFrame(() => {
      frame = 0;
      if (open && !box.getClientRects().length) self.close(); else hide();
    });
  }) : null;
  const copy = () => {
    lines.replaceChildren(...[...bar.querySelectorAll<HTMLElement>(INFO_NOTES)].map((note) => {
      const line = el("p", "v3-infobox-line " + note.className), parts = note.cloneNode(true) as HTMLElement;
      for (const kept of parts.querySelectorAll(INFO_KEPT)) kept.remove();
      line.textContent = (parts.textContent ?? "").trim();
      return line;
    }));
    hide();
  };
  // the bar while the box is open: a note shown, hidden, added or reworded
  const watch = typeof MutationObserver === "function" ? new MutationObserver(copy) : null;
  // Whether the latest press was on the box or its button (a key ends that): the focus may seem to leave the box
  // with such a press (where a press moves no focus, as in Safari), and the box stays
  let pressing = false;
  const onPress = (e: PointerEvent) => {
    const at = e.target;
    pressing = at instanceof Node && (box.contains(at) || button.contains(at));
    if (!pressing) self.close();  // a press beside the box closes it (the pressed control still gets its press)
  };
  const onKey = (e: KeyboardEvent) => {
    pressing = false;
    // Shift+Tab out of the box (from "Close", its first control, or the box itself): closed, the focus back on its
    // button, as Tab out of it closes it and goes on (the credits hidden under the box are out of the Tab order
    // until it closes, so the browser's own step went past the button, to the strip's last tool)
    if (open && e.key === "Tab" && e.shiftKey && (document.activeElement === shut || document.activeElement === box)) {
      e.preventDefault();
      self.close(true);
      return;
    }
    if (e.key !== "Escape" || !open) return;
    if (!box.getClientRects().length) { self.close(); return; }  // not shown: the press is for what is
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
      box.classList.remove("v3-hidden");
      copy();
      watch?.observe(bar, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["class"]});
      const credits = button.closest(".v3-credits");
      for (const e of [stage, credits, box]) if (e) sizes?.observe(e);  // the credits opened or folded, the card, a turn
      button.setAttribute("aria-expanded", "true");
      document.addEventListener("keydown", onKey, true);
      document.addEventListener("pointerdown", onPress, true);
      shut.focus();
    },
    close(focus = false) {
      if (!open) return;
      open = false;
      watch?.disconnect();
      sizes?.disconnect();
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPress, true);
      box.classList.add("v3-hidden");
      lines.replaceChildren();
      hide();  // the credits back before the focus goes to the button in them
      button.setAttribute("aria-expanded", "false");
      if (focus) button.focus();
    },
  };
  button.addEventListener("click", () => { if (open) self.close(); else self.open(); });
  shut.addEventListener("click", () => self.close(true));
  // The focus leaving the box by the keyboard closes it: Tab from "Close" goes on to the control Tab meant, which
  // the box may cover (a focused control out of sight). Not with a press on the box or the info button (onPress:
  // the button's own click closes the box, a press on the box's text keeps it and puts the focus on the box), nor
  // when the window loses the focus
  box.addEventListener("pointerup", () => { if (open && !box.contains(document.activeElement)) box.focus({preventScroll: true}); });
  box.addEventListener("focusout", (e) => {
    const to = e.relatedTarget;
    if (!open || pressing || (to instanceof Node && box.contains(to)) || !document.hasFocus()) return;
    self.close();
  });
  return self;
}
