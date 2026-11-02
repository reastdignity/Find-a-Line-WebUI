// The coverage map's page, /coverage (web.py): a placeholder until wave 1 (agent C) builds it.
import { COVERAGE } from "../data";
import { ct, pickLang } from "../i18n";

const lang = pickLang();
const root = document.getElementById("coverage");
if (root) root.textContent = ct(lang, "count.areas", {count: Object.keys(COVERAGE.areas).length});
