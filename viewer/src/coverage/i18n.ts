// The coverage map's texts: its own catalogue, locales/coverage/<language>.json (English and Polish, the
// same keys: tests/test_coverage.py), apart from the app's English one. `ct`, not `t`: the keys the app's
// `t` asks for are checked against the app's catalogue (tests/test_units.py::test_viewer_keys_in_catalogue).
import type { TOptions } from "i18next";
import en from "../../../locales/coverage/en.json";
import pl from "../../../locales/coverage/pl.json";
import { translator, type Texts } from "../translator";
import type { Area, Note } from "./types";

export const LANGS = ["en", "pl"] as const;
export type Lang = (typeof LANGS)[number];

const TRANSLATORS: Record<Lang, (key: string, params?: TOptions) => string> = {
  en: translator(en as Texts, "en"),
  pl: translator(pl as Texts, "pl"),
};

/** A text of the coverage catalogue in `lang`. */
export const ct = (lang: Lang, key: string, params?: TOptions): string => TRANSLATORS[lang](key, params);

const LANG_KEY = "findaline.coverage.lang";

/** The language chosen before on this browser, else the browser's first of LANGS, else English. */
export function pickLang(): Lang {
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored && (LANGS as readonly string[]).includes(stored)) return stored as Lang;
  } catch { /* storage blocked: the browser's language */ }
  for (const tag of navigator.languages || [navigator.language]) {
    const base = (tag || "").slice(0, 2).toLowerCase();
    if ((LANGS as readonly string[]).includes(base)) return base as Lang;
  }
  return "en";
}

export function rememberLang(lang: Lang): void {
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* not remembered */ }
}

const NUMBER: Partial<Record<Lang, Intl.NumberFormat>> = {};

/** Metres as the language writes them, the number and its unit kept together: "2.5 m", "2,5 m". */
export function metres(value: number, lang: Lang): string {
  const format = NUMBER[lang] || (NUMBER[lang] = new Intl.NumberFormat(lang, {maximumFractionDigits: 2}));
  return `${format.format(value)} m`;
}

/** The resolutions of an area: "1 m", "1 m / 2 m / 30 m". */
export const resText = (res: number[], lang: Lang): string => res.map(r => metres(r, lang)).join(" / ");

/** Several resolutions as alternatives: "2 m or 30 m", "2 m lub 30 m". */
export function alternatives(res: number[], lang: Lang): string {
  const items = res.map(r => metres(r, lang));
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")}${ct(lang, "list.or")}${items[items.length - 1]}`;
}

const NAMES: Partial<Record<Lang, Intl.DisplayNames>> = {};

/** The name of an area: a region's from the catalogue (region.<id>), a country's from the browser
 *  (Intl.DisplayNames), else its code. */
export function areaName(id: string, lang: Lang): string {
  if (id.includes("-")) {
    const key = `region.${id}`, name = ct(lang, key);
    return name === key ? id.toUpperCase() : name;
  }
  try {
    const names = NAMES[lang] || (NAMES[lang] = new Intl.DisplayNames([lang], {type: "region"}));
    const name = names.of(id.toUpperCase());
    if (name && name.toLowerCase() !== id) return name;
  } catch { /* an unknown code */ }
  return id.toUpperCase();
}

/** The text of a note of an area: numbers in its params are metres; "mixed" takes the finest and the
 *  other resolutions from the area. */
export function noteText(note: Note, area: Area | null, lang: Lang): string {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(note.params || {})) {
    params[key] = Array.isArray(value) ? alternatives(value, lang) : typeof value === "number" ? metres(value, lang) : value;
  }
  if (note.code === "mixed" && area) {
    params.fine ??= metres(area.res[0], lang);
    params.rest ??= alternatives(area.res.slice(1), lang);
  }
  return ct(lang, `note.${note.code}`, params);
}

/** The survey of an area as a text: its years as they are, a code through the catalogue, "" for none. */
export function surveyText(survey: string, lang: Lang): string {
  if (!survey || /^\d{4}(–\d{4})?$/.test(survey)) return survey;
  return ct(lang, `survey.${survey}`);
}
