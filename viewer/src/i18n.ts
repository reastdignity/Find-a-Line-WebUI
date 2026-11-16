// The texts of the interface: the message catalogue locales/<language>.json at the root of the
// repository, shared with the server (messages.py reads the same file and formats it the same way).
// Keys are flat and namespaced ("field.radius.label", "choice.nmpt.off", "ui.searched.today"); `{{name}}` is
// replaced by a value, and a key with `count` takes its plural form ("<key>_one", "<key>_other",
// "<key>_zero" for 0) where the catalogue has one. i18next's core only: no React bindings, the
// texts are read when a component draws.
import en from "../../locales/en.json";
import { detailText } from "./errors";
import { translator, type Texts } from "./translator";

export { translator };

// English only for now; a language would be chosen here later (`?lang=`, navigator.language) and its
// catalogue imported next to en.json, with English as the fallback.
export const t = translator(en as Texts);

/** The label of a field of the search (field.<name>.label). */
export const label = (field: string): string => t(`field.${field}.label`);

/** The parameters of a coded error or note (messages.py UserError, Note): {code, params}, and `key`: the
 *  catalogue key of the reading the server chose where it is not the code's own "error.<code>" (the public site's
 *  wording of a note: "error.access_skipped_public", with the params that reading takes). */
export interface ErrorInfo { code: string; params?: Record<string, unknown>; key?: string }

/** The text of a coded error in the page's language, as messages.Coded.web_text: the reading the server chose
 *  (`info.key`) when it names one and this page's catalogue has it, else the code's own ("error.<code>"); a
 *  parameter "field" gives the label ("label"), "advice" the text "advice_text". `fallback` (the
 *  server's English text) when the catalogue has no such code (a newer server), and when it lacks the reading the
 *  server chose: the info then carries that reading's params (none for a public one), not the code's own, so the
 *  code's text would show its placeholders. */
export function errorText(info: ErrorInfo, fallback?: string): string {
  const key = `error.${info.code}`;
  const params: Record<string, unknown> = {...(info.params || {})};
  if (typeof params.field === "string" && params.label === undefined) params.label = label(params.field);
  if (params.advice_text === undefined) params.advice_text = adviceText(params.advice);
  if (typeof info.key === "string" && info.key !== key) {
    const chosen = t(info.key, params);
    if (chosen !== info.key) return chosen;
    if (fallback) return fallback;  // a reading this catalogue lacks: the server's own text of it
  }
  const text = t(key, params);
  return text === key && fallback ? fallback : text;
}

/** The advice of a refusal for too many lines (messages.advice_text): its items ({key, values}) in
 *  "error.advice.list", or "error.advice.none" without any. */
function adviceText(advice: unknown): string {
  const items = Array.isArray(advice) ? advice as Record<string, unknown>[] : [];
  if (!items.length) return t("error.advice.none");
  return t("error.advice.list", {items: items.map(({key, ...values}) => t(`error.advice.${key}`, values)).join("; ")});
}

/** A value of a field with its unit as the texts write it (messages.quantity): "2000 m", "45°", "50". */
export function quantity(field: string, value: number): string {
  const unit = t(`field.${field}.unit`);
  if (!unit || unit === `field.${field}.unit`) return String(value);
  return unit === "°" ? `${value}${unit}` : `${value} ${unit}`;
}

/** The text of an error answer's detail (web.py error_detail) in the page's language: a coded one's
 *  text, else its message or the plain text (errors.ts detailText). */
export function detailMessage(detail: unknown, fallback = "error"): string {
  const coded = detail as {code?: unknown; params?: Record<string, unknown>; message?: string; key?: unknown} | null;
  if (coded && typeof coded === "object" && typeof coded.code === "string") {
    return errorText({code: coded.code, params: coded.params, key: typeof coded.key === "string" ? coded.key : undefined},
                     detailText(detail, fallback));
  }
  return detailText(detail, fallback);
}
