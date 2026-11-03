// A `t` of a flat catalogue, without importing one: the app's catalogue (i18n.ts) and the coverage map's
// (coverage/i18n.ts) both make theirs here, so a bundle holds only the catalogues it uses.
import i18next, { type TOptions } from "i18next";

export type Texts = Record<string, string>;

/** A `t` of its own catalogue (tests give their own samples). Initialised synchronously: the texts
 * are in the bundle, so `t` works as soon as the module is loaded. */
export function translator(texts: Texts, language = "en"): (key: string, params?: TOptions) => string {
  const instance = i18next.createInstance();
  instance.init({
    lng: language, fallbackLng: "en", resources: {[language]: {translation: texts}},
    initAsync: false,
    keySeparator: false, nsSeparator: false,  // flat keys with dots, as Python reads them
    interpolation: {escapeValue: false},       // Preact escapes what it draws
    returnNull: false,
  });
  return (key, params) => instance.t(key, params) as string;
}
