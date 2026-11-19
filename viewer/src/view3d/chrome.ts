// The page's chrome over the stage (docs/3d-view-contract.md, "Round 2"): the activity pill (what is loading or
// being computed, with a spinner; or a notice of something that went wrong, with an action) and the tool strip
// (the controls of round 2). Plain DOM, no style attributes (the CSP's style-src 'self'): classes of view3d.css,
// sizes through the CSSOM.

import { t } from "../i18n";
import { kitIcon } from "./icon";
import type { Activity, ActivityAction, ToolButton, Tools, ToolSpec } from "./scene-api";

const SVG = "http://www.w3.org/2000/svg";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  return e;
}

interface Entry { text: string; fraction: number | null; notice: boolean; action: ActivityAction | null }

/** The activity pill in `box` (a `role="status"` element of the stage): the wait added last shows; without a
 *  wait, the notice added last (no spinner, the warning's colour, its action's button and one to dismiss it). */
export function createActivity(box: HTMLElement): Activity {
  const entries = new Map<string, Entry>();
  const spin = el("span", "v3-spin"), text = el("span", "v3-activity-text");
  const meter = el("span", "u-prog v3-activity-meter"), fill = el("i", "");
  const action = el("button", "u-btn v3-activity-action"), dismiss = el("button", "u-btn v3-activity-dismiss");
  action.type = dismiss.type = "button";
  // the kit's "close" icon: the pill's text stays the message alone
  dismiss.append(kitIcon("close"));
  dismiss.setAttribute("aria-label", t("ui.view3d.dismiss"));
  dismiss.title = t("ui.view3d.dismiss");
  meter.append(fill);
  box.replaceChildren(spin, text, meter, action, dismiss);
  let shownId: string | null = null;
  const render = () => {
    const all = [...entries.entries()];
    const [id, shown] = all.filter(([, e]) => !e.notice).pop() ?? all.pop() ?? [null, null];
    shownId = id;
    box.classList.toggle("v3-hidden", !shown);
    if (!shown) return;
    box.classList.toggle("v3-activity-notice", shown.notice);
    box.dataset.activity = id ?? "";
    spin.classList.toggle("v3-hidden", shown.notice);
    text.textContent = shown.text;
    meter.classList.toggle("v3-hidden", shown.fraction === null);
    if (shown.fraction !== null) fill.style.width = `${Math.round(Math.min(1, Math.max(0, shown.fraction)) * 100)}%`;
    action.classList.toggle("v3-hidden", !shown.action);
    action.textContent = shown.action?.label ?? "";
    dismiss.classList.toggle("v3-hidden", !shown.notice);
  };
  action.addEventListener("click", () => { if (shownId !== null) entries.get(shownId)?.action?.onClick(); });
  dismiss.addEventListener("click", () => { if (shownId !== null && entries.delete(shownId)) render(); });
  render();
  return {
    set(id, label, fraction = null) {
      // an entry set again keeps its place: a count's updates hide no later entry
      entries.set(id, {text: label, fraction, notice: false, action: null});
      render();
    },
    notice(id, label, act = null) {
      entries.set(id, {text: label, fraction: null, notice: true, action: act});
      render();
    },
    clear(id) { if (entries.delete(id)) render(); },
  };
}

/** The gap the card's slot keeps from the tool strip (CSS pixels). */
export const ASIDE_GAP_PX = 8;

/** The card steps aside (docs/3d-view-contract.md, "Step 3c, group B: the phone's layout"): where the open card in
 *  `card` (its slot) would reach the tool strip `tools` (its top less than ASIDE_GAP_PX under the strip's foot) and
 *  the strip shows icons alone, `stage` gets the class `v3-aside` and the slot starts right of the strip
 *  (view3d.css); `--v3-strip` on the stage is the strip's right edge and the gap whenever the strip has a tool (the
 *  tools' own boxes are measured: a second column lies outside the strip's box). The test is made with the class
 *  off, in one pass without a frame between: at the card's full width, so the narrower, higher card never feeds the
 *  test that narrows it and the choice cannot undo itself; a card that becomes lower ("Rigging and layers" closed)
 *  gets its width back. Run when the stage, the strip or the slot changes its size (its own change of the slot
 *  brings one more run with the same answer), when a tool or the card comes or goes, and by `fit()`; `changed`
 *  after a change (the
 *  caller draws a frame, so what is placed by the bottom column's box is placed again). */
export function stepAside(stage: HTMLElement, tools: HTMLElement, card: HTMLElement, changed: () => void):
    {fit(): void; dispose(): void} {
  let was = "";
  const fit = () => {
    const box = stage.getBoundingClientRect();
    let foot = 0, right = 0, icons = true;
    for (const tool of tools.children) {
      const r = tool.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      foot = Math.max(foot, r.bottom - box.top);
      right = Math.max(right, r.right - box.left);
      if (tool.querySelector(".v3-tool-label")?.getClientRects().length) icons = false;
    }
    const strip = right ? Math.round(right + ASIDE_GAP_PX) : 0;
    if (strip) stage.style.setProperty("--v3-strip", `${strip}px`); else stage.style.removeProperty("--v3-strip");
    stage.classList.remove("v3-aside");
    const aside = icons && strip > 0 && !!card.firstElementChild &&
      card.getBoundingClientRect().top - box.top < foot + ASIDE_GAP_PX;
    stage.classList.toggle("v3-aside", aside);
    const now = `${aside}:${strip}`;
    if (now !== was) { was = now; changed(); }
  };
  // A change of size is answered before the next frame's layout, never inside the observer's own call (changing the
  // slot there ends the observer's round with "ResizeObserver loop completed with undelivered notifications"); a
  // card opened or closed and a tool added or removed are answered at once, before any frame shows them (the strip's
  // box does not grow with a second column, so its size alone would miss that tool)
  let frame = 0;
  const later = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; fit(); }); };
  const sizes = typeof ResizeObserver === "function" ? new ResizeObserver(later) : null;
  for (const e of [stage, tools, card]) sizes?.observe(e);
  const children = typeof MutationObserver === "function" ? new MutationObserver(fit) : null;
  // a tool shown or hidden by its class too ("Other saved lines"): WebKit kept the one column's 60 px beside two
  children?.observe(tools, {childList: true, subtree: true, attributes: true, attributeFilter: ["class"]});
  children?.observe(card, {childList: true});
  return {fit, dispose() { sizes?.disconnect(); children?.disconnect(); if (frame) cancelAnimationFrame(frame); }};
}

/** The tool strip in `box`: buttons of an icon and a label, in their `order`. */
export function createTools(box: HTMLElement): Tools {
  return {
    add(spec: ToolSpec): ToolButton {
      const button = el("button", "u-btn v3-tool");
      button.type = "button";
      button.dataset.tool = spec.id;
      button.style.order = String(spec.order);
      const svg = document.createElementNS(SVG, "svg"), path = document.createElementNS(SVG, "path");
      svg.setAttribute("viewBox", "0 0 16 16");
      svg.setAttribute("aria-hidden", "true");
      svg.classList.add("v3-tool-icon");
      path.setAttribute("d", spec.icon);
      svg.append(path);
      const label = el("span", "v3-tool-label");
      button.append(svg, label);
      const self: ToolButton = {
        element: button,
        setPressed(on) {
          button.classList.toggle("u-on", on);
          if (spec.toggle) button.setAttribute("aria-pressed", String(on));
        },
        setLabel(text) { label.textContent = text; button.title = text; button.setAttribute("aria-label", text); },
        setIcon(d) { path.setAttribute("d", d); },
        remove() { button.remove(); },
      };
      self.setLabel(spec.label);
      if (spec.toggle) self.setPressed(false);
      button.addEventListener("click", () => spec.onClick());
      box.append(button);
      return self;
    },
  };
}
