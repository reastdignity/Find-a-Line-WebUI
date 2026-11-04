// Which interface the app shows: ?ui=b|c|d|kit|kit-result|kit-search|kit-layer, remembered in localStorage (per browser) until
// another is chosen. C is the default (the old interface, ?ui=old, was removed: a browser that remembered it gets C).
// D was the default before C: a browser that remembered "d" from those days (often from a link that carried
// ?ui=d, as D's copied links did) forgets it once and lands on C; one that chose B keeps B, and an explicit
// ?ui=d is remembered again as before. The marker MIGRATED_KEY says that the forgetting was done.

export type UiChoice = "b" | "c" | "d" | "kit" | "kit-result" | "kit-search" | "kit-layer";
const CHOICES: UiChoice[] = ["b", "c", "d", "kit", "kit-result", "kit-search", "kit-layer"];
const STORAGE_KEY = "findaline-ui";
const MIGRATED_KEY = "findaline-ui-c-default";

/** Forgets a "d" remembered from before C was the default, once per browser (MIGRATED_KEY set afterwards). */
function forgetOldDefault() {
  try {
    if (localStorage.getItem(MIGRATED_KEY)) return;
    if (localStorage.getItem(STORAGE_KEY) === "d") localStorage.removeItem(STORAGE_KEY);
    localStorage.setItem(MIGRATED_KEY, "1");
  } catch { /* private window, blocked storage: nothing remembered anyway */ }
}

/** The interface of this page: the parameter (remembered), else the remembered one, else "c". */
export function chooseUi(search: string = location.search): UiChoice {
  forgetOldDefault();
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

/** This page's address (path and query) without ?ui=: a copied link opens whichever interface its reader
 *  uses (by default C), not the one it was copied from. */
export function hrefWithoutUi(): string {
  const params = new URLSearchParams(location.search);
  params.delete("ui");
  const query = params.toString();
  return location.pathname + (query ? `?${query}` : "");
}

/** The address of this page in another interface (the hash, a route of the new shells, is dropped). */
export function uiHref(choice: UiChoice): string {
  const params = new URLSearchParams(location.search);
  params.set("ui", choice);
  return `${location.pathname}?${params}`;
}

const THEME_KEY = "findaline-theme";

/** The remembered theme of the new interfaces ("auto" follows the system). */
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
