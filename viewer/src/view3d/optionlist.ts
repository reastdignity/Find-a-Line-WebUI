// The list of the lines from a point (docs/3d-view-contract.md, "Round 2", point 9): a panel at the stage's right
// with the title (their number), a table (length, clearance, height difference, over trees; a click on a column's
// head sorts by it) and a row for each line: hovering or focusing a row marks its webbing, a click or Enter
// chooses the line. The panel stands under the activity pill (top 52 px), keeps clear of the tool strip by its
// width and of the credits and the card by its height (measured from `.v3-bottom` after every frame and resize),
// and scrolls inside itself.
//
// The clearance is shown as an upper bound ("≤ 1.5 m"): the mask keeps ceil(clearance / quantum) steps, so the
// real clearance lies up to one quantum (0.5 m) below the number.

import { t } from "../i18n";
import { signedMetres, sortOptions, type Option, type SortKey } from "./options";
import type { SceneCore } from "./scene";
import { metres } from "./webbing";
import "./point.css";

export interface ListHandlers {
  hover(rank: number | null): void;
  choose(rank: number): void;
}

export interface OptionList {
  readonly element: HTMLElement;
  /** Only the note (the hint, a wait). */
  note(text: string): void;
  /** A failure's text in the note (role alert). */
  fail(text: string): void;
  /** The title and the rows for `options`; `quantum` (metres) is the clearance's resolution. */
  show(options: readonly Option[], quantum: number): void;
  /** Mark the row of rank `rank` (null: none); `reveal`: scroll the list to it. */
  highlight(rank: number | null, reveal?: boolean): void;
  hide(): void;
  /** The rows' ranks in the order shown (for tests). */
  order(): number[];
}

/** Each column's first click sorts the way that shows its best first. */
export const FIRST_DESCENDING: Record<SortKey, boolean> = {rank: false, length: true, clear: true, dh: false, trees: false};

const COLUMNS: {key: SortKey; head: string}[] = [
  {key: "length", head: "ui.view3d.point_length"}, {key: "clear", head: "ui.view3d.point_clear"},
  {key: "dh", head: "ui.view3d.point_dh"}, {key: "trees", head: "ui.view3d.point_trees"},
];

/** The panel's top (below the activity pill) and the gap it keeps from the bottom column. */
export const TOP_PX = 52;
export const GAP_PX = 8;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function createOptionList(scene: SceneCore, handlers: ListHandlers): OptionList {
  const panel = el("section", "v3-optlist v3-hidden"), title = el("h2", "v3-optlist-title v3-hidden");
  const note = el("p", "v3-optlist-note v3-hidden"), scroll = el("div", "v3-optlist-scroll v3-hidden");
  const table = el("table", "v3-optlist-table"), head = el("thead", ""), body = el("tbody", "");
  title.setAttribute("aria-live", "polite");
  panel.dataset.point = "list";
  const headRow = el("tr", "");
  const buttons = new Map<SortKey, HTMLButtonElement>();
  for (const c of COLUMNS) {
    const th = el("th", `v3-opt-${c.key}`), b = el("button", "v3-opt-sort", t(c.head));
    b.type = "button";
    b.dataset.sort = c.key;
    th.scope = "col";
    th.append(b);
    headRow.append(th);
    buttons.set(c.key, b);
  }
  head.append(headRow);
  table.append(head, body);
  scroll.append(table);
  panel.append(title, note, scroll);
  scene.stage.append(panel);

  let options: readonly Option[] = [], quantum = 0.5;
  let key: SortKey = "rank", descending = false, marked: number | null = null;
  const rows = new Map<number, HTMLTableRowElement>();

  const render = () => {
    rows.clear();
    body.replaceChildren();
    for (const o of sortOptions(options, key, descending)) {
      const tr = el("tr", "v3-opt-row" + (o.over ? " v3-over" : ""));
      tr.tabIndex = 0;
      tr.dataset.rank = String(o.rank);
      const length = el("td", "v3-opt-num", t("ui.view3d.point_m", {m: metres(o.len)}));
      const clear = el("td", "v3-opt-num", t("ui.view3d.point_clear_value", {m: metres(o.clr)}));
      clear.title = t("ui.view3d.point_clear_title", {m: metres(quantum)});
      const dh = el("td", "v3-opt-num", o.dh === null ? "–" : t("ui.view3d.point_m", {m: signedMetres(o.dh)}));
      const trees = el("td", "v3-opt-trees");
      if (o.over) {
        const dot = el("span", "v3-opt-over");
        dot.title = t("ui.view3d.over_trees");
        dot.setAttribute("role", "img");
        dot.setAttribute("aria-label", t("ui.view3d.over_trees"));
        trees.append(dot);
      }
      tr.append(length, clear, dh, trees);
      tr.addEventListener("pointerenter", () => handlers.hover(o.rank));
      tr.addEventListener("pointerleave", () => handlers.hover(null));
      tr.addEventListener("focus", () => handlers.hover(o.rank));
      tr.addEventListener("blur", () => handlers.hover(null));
      tr.addEventListener("click", () => handlers.choose(o.rank));
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handlers.choose(o.rank); }
      });
      rows.set(o.rank, tr);
      body.append(tr);
    }
    for (const [k, b] of buttons) {
      const th = b.parentElement!;
      if (k === key) th.setAttribute("aria-sort", descending ? "descending" : "ascending");
      else th.removeAttribute("aria-sort");
    }
    if (marked !== null) rows.get(marked)?.classList.add("v3-on");
  };
  for (const [k, b] of buttons) {
    b.addEventListener("click", () => {
      if (key === k) descending = !descending;
      else { key = k; descending = FIRST_DESCENDING[k]; }
      render();
    });
  }

  // The panel's height: from its top to the bottom column (credits, card)
  const fit = () => {
    if (panel.classList.contains("v3-hidden")) return;
    const bottom = scene.stage.querySelector<HTMLElement>(".v3-bottom"), stage = scene.stage.getBoundingClientRect();
    const floor = bottom && !bottom.classList.contains("v3-hidden") && bottom.offsetHeight
      ? bottom.getBoundingClientRect().top - stage.top : stage.height;
    const space = Math.max(80, Math.floor(floor - TOP_PX - GAP_PX));
    panel.style.maxHeight = `${space}px`;
  };
  scene.view.onDrawn(fit);
  addEventListener("resize", fit);
  scene.onDispose(() => { removeEventListener("resize", fit); panel.remove(); });

  const reveal = () => { panel.classList.remove("v3-hidden"); fit(); };
  return {
    element: panel,
    note(text) {
      note.textContent = text;
      note.removeAttribute("role");
      note.classList.remove("v3-failed");
      note.classList.toggle("v3-hidden", !text);
      title.classList.add("v3-hidden");
      scroll.classList.add("v3-hidden");
      options = [];
      rows.clear();
      body.replaceChildren();
      reveal();
    },
    fail(text) {
      this.note(text);
      note.setAttribute("role", "alert");
      note.classList.add("v3-failed");
    },
    show(next, q) {
      options = next;
      quantum = q;
      marked = null;
      key = "rank";
      descending = false;
      note.textContent = "";
      note.classList.add("v3-hidden");
      note.classList.remove("v3-failed");
      title.textContent = t("ui.view3d.point_title", {count: next.length});
      title.classList.remove("v3-hidden");
      scroll.classList.toggle("v3-hidden", !next.length);
      scroll.scrollTop = 0;
      render();
      reveal();
    },
    highlight(rank, reveal = false) {
      marked = rank;
      for (const [r, tr] of rows) tr.classList.toggle("v3-on", r === rank);
      const row = rank === null ? undefined : rows.get(rank);
      if (reveal && row) {  // by hand: scrollIntoView could move the stage, which clips but can be scrolled
        const top = row.offsetTop, bottom = top + row.offsetHeight;
        if (top - head.offsetHeight < scroll.scrollTop) scroll.scrollTop = top - head.offsetHeight;  // the sticky head covers the top
        else if (bottom > scroll.scrollTop + scroll.clientHeight) scroll.scrollTop = bottom - scroll.clientHeight;
      }
    },
    hide() {
      panel.classList.add("v3-hidden");
      options = [];
      rows.clear();
      body.replaceChildren();
    },
    order() { return [...rows.keys()]; },
  };
}
