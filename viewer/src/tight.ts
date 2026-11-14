// The mark of a tight line: a clearance under TIGHT metres (a working value, docs/line-volume/spec-view.md A.2).
// The mark hides nothing and is not drawn on the map: it is a ring with "!" before the clearance in the rows of
// the result (result/view/common.tsx TightMark) and a line in a line's details.

import { shortMetres } from "./endzone";
import { t } from "./i18n";

/** m: a line whose clearance is under this is tight. */
export const TIGHT = 1;

/** Is a line with this clearance tight. */
export const isTight = (clr: number): boolean => clr < TIGHT;

/** A clearance as the screen shows it, with one decimal: a tight line's is rounded down to 0.1 m, so that no
 *  marked row reads "1.0 m"; any other's as before. */
export function clearanceText(clr: number): string {
  if (!isFinite(clr)) return "–";
  return (isTight(clr) ? Math.floor(clr * 10 + 1e-4) / 10 : clr).toFixed(1);
}

/** The key of the mark (under a list that holds a tight row, and the ring's title): with the run's A-frame
 *  height `lift` (m) when it has A-frames, else without that clause. */
export function tightKey(lift?: number | null): string {
  return lift ? t("ui.tight.key_lift", {m: TIGHT, lift: shortMetres(lift)}) : t("ui.tight.key", {m: TIGHT});
}

/** The details' line of a tight line (its clearance as clearanceText writes it). */
export function tightLine(clr: number, lift?: number | null): string {
  const shown = clearanceText(clr);
  return lift ? t("ui.tight.line_lift", {clr: shown, lift: shortMetres(lift)}) : t("ui.tight.line", {clr: shown});
}
