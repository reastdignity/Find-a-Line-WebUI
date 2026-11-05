// The page's chrome over the stage (docs/3d-view-contract.md, "Round 2"): the activity pill (what is loading or
// being computed, with a spinner; or a notice of something that went wrong, with an action) and the tool strip
// (the controls of round 2). Plain DOM, no style attributes (the CSP's style-src 'self'): classes of view3d.css,
// sizes through the CSSOM.

import { t } from "../i18n";
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
  // its cross is drawn by view3d.css: the pill's text stays the message alone
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
