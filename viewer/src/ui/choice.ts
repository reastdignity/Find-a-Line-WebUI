// What the app shows: ?ui=c (the interface, the default) or a demo of the kit (?ui=kit|kit-result|kit-search|
// kit-layer), remembered in localStorage (per browser) until another is chosen. Interfaces that were removed
// (?ui=old, b, d), asked for or remembered, are not choices: the page shows C.

export type UiChoice = "c" | "kit" | "kit-result" | "kit-search" | "kit-layer";
const CHOICES: UiChoice[] = ["c", "kit", "kit-result", "kit-search", "kit-layer"];
const STORAGE_KEY = "findaline-ui";

/** What this page shows: the parameter (remembered), else the remembered choice, else "c". */
export function chooseUi(search: string = location.search): UiChoice {
  const asked = new URLSearchParams(search).get("ui") as UiChoice | null;
  if (asked && CHOICES.includes(asked)) {
    try { localStorage.setItem(STORAGE_KEY, asked); } catch { /* private window, blocked storage */ }
    return asked;
  }
  try {
    const kept = localStorage.getItem(STORAGE_KEY) as UiChoice | null;
    if (kept && CHOICES.includes(kept)) return kept;
  } catch { /* no storage */ }
  return "c";
}

/** This page's address (path and query) without ?ui=: a copied link opens the interface, not a demo of the
 *  kit it may have been copied from. */
export function hrefWithoutUi(): string {
  const params = new URLSearchParams(location.search);
  params.delete("ui");
  const query = params.toString();
  return location.pathname + (query ? `?${query}` : "");
}

/** The address of this page with another choice (the hash, a route of the interface, is dropped). */
export function uiHref(choice: UiChoice): string {
  const params = new URLSearchParams(location.search);
  params.set("ui", choice);
  return `${location.pathname}?${params}`;
}

const THEME_KEY = "findaline-theme";

/** The remembered theme of the interface and the kit ("auto" follows the system). */
export function storedTheme(): "auto" | "light" | "dark" {
  try {
    const kept = localStorage.getItem(THEME_KEY);
    if (kept === "light" || kept === "dark") return kept;
  } catch { /* no storage */ }
  return "auto";
}

export function storeTheme(theme: "auto" | "light" | "dark") {
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* no storage */ }
}
