// The page's chrome over the stage (docs/3d-view-contract.md, "Round 2"): the activity pill (what is loading or
// being computed, with a spinner) and the tool strip (the controls of round 2). Plain DOM, no style attributes
// (the CSP's style-src 'self'): classes of view3d.css, sizes through the CSSOM.

import type { Activity, ToolButton, Tools, ToolSpec } from "./scene-api";

const SVG = "http://www.w3.org/2000/svg";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  return e;
}

/** The activity pill in `box` (a `role="status"` element of the stage): the entry added last shows. */
export function createActivity(box: HTMLElement): Activity {
  const entries = new Map<string, {text: string; fraction: number | null}>();
  const text = el("span", "v3-activity-text"), meter = el("span", "u-prog v3-activity-meter"), fill = el("i", "");
  meter.append(fill);
  box.replaceChildren(el("span", "v3-spin"), text, meter);
  const render = () => {
    const shown = [...entries.values()].pop();
    box.classList.toggle("v3-hidden", !shown);
    if (!shown) return;
    text.textContent = shown.text;
    meter.classList.toggle("v3-hidden", shown.fraction === null);
    if (shown.fraction !== null) fill.style.width = `${Math.round(Math.min(1, Math.max(0, shown.fraction)) * 100)}%`;
  };
  render();
  return {
    set(id, t, fraction = null) {
      entries.set(id, {text: t, fraction});  // an entry set again keeps its place: a count's updates hide no later entry
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
        setLabel(t) { label.textContent = t; button.title = t; button.setAttribute("aria-label", t); },
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
