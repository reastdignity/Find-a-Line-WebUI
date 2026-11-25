// A size in bytes as a person reads it (line volume's round 7, step 2d as reduced): a run's size as stored on
// Home's card and the two numbers of the line shown while a run downloads, cut the same way so the card and the
// line show the same number. A MB is 10^6 bytes and a GB 10^9 (the units a disk and a download are sold in). The
// cut (the user's answer 2 a, 2026-11-24, as the accepted mock-up draws it): one decimal below 10 MB, whole MB up
// to 999, then GB with one decimal, each rounded; "under 0.1 MB" where one decimal would read "0.0" (below 50 000
// bytes). The line of a download whose total is that small writes both numbers in MB with two decimals ("0.02 of
// 0.04 MB": the user's answer 3 of 2026-11-25, "Two decimals … only for runs this small"); the card keeps "under
// 0.1 MB". A size never breaks inside: the catalogue's texts join its number and its unit (and "under") with
// no-break spaces, so a line that is too long breaks beside the size, not in it.

import { t } from "./i18n";

const MB = 1e6, GB = 1e9;
/** Below this one decimal of a MB reads "0.0": the card says "under 0.1 MB", a download's line two decimals. */
const UNDER = 0.05 * MB;
/** From here a size reads in whole MB (9.95 MB rounds to "10 MB"). */
const WHOLE_MB = 9.95 * MB;
/** From here a size reads in GB (999.5 MB rounds to "1.0 GB"). */
const IN_GB = 999.5 * MB;

/** How a size is cut: the bytes of its unit, the unit's word and its number's decimals (0, 1; 2 only for a
 *  download's tiny total: `tiny`). */
interface Cut { bytes: number; unit: string; decimals: number }

function cutOf(bytes: number): Cut {
  const gb = bytes >= IN_GB;
  return {bytes: gb ? GB : MB, unit: t(gb ? "ui.size.gb" : "ui.size.mb"), decimals: gb || bytes < WHOLE_MB ? 1 : 0};
}

/** A download's total under UNDER: both numbers in MB with two decimals. */
const tiny = (): Cut => ({bytes: MB, unit: t("ui.size.mb"), decimals: 2});

/** A number in its cut, rounded. Two decimals are counted on the bytes (a hundredth of a MB is 10 000 bytes, so a
 *  half is exact and goes up: 15 000 bytes "0.02", where toFixed of 0.015's double would give "0.01"). */
const numberIn = (bytes: number, cut: Cut): string => cut.decimals === 2
  ? (Math.round(bytes / (cut.bytes / 100)) / 100).toFixed(2)
  : cut.decimals ? (bytes / cut.bytes).toFixed(1) : String(Math.round(bytes / cut.bytes));

/** A size in words: "247 MB", "0.6 MB", "1.8 GB", "under 0.1 MB" (0 bytes too); "" for no size (null: a run saved
 *  without the number; also a number that is none: negative, not finite). */
export function sizeText(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < UNDER) return t("ui.size.under");
  const cut = cutOf(bytes);
  return t("ui.size.value", {n: numberIn(bytes, cut), unit: cut.unit});
}

/** The numbers of a download for its line: `done` and `total` bytes both in the total's unit and with the total's
 *  cut ("41" of "247" "MB", "0.4" of "1.8" "GB", "0.3" of "0.6" "MB"), so the line ends at the card's number; a
 *  total under 50 000 bytes (the card's "under 0.1 MB") both in MB with two decimals ("0.02" of "0.04" "MB"; a
 *  total under 5 000 bytes "0.00"). A total not known (null): `done` with its own cut, `total` "". Never "under". */
export function downloadSizes(done: number, total: number | null): {done: string; total: string; unit: string} {
  const cut = total !== null && total < UNDER ? tiny() : cutOf(total ?? done);
  return {done: numberIn(done, cut), total: total === null ? "" : numberIn(total, cut), unit: cut.unit};
}
