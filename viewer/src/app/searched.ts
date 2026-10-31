// The area of the user's finished searches (/api/usage `area`, docs/monitoring.md "The area searched"):
// grouped by day in the viewer's time zone, like every other time of the page, and formatted for people.
// No page state here (tests/test_viewer.py runs it in Node).

import type { AreaUsage } from "./api";
import { day } from "../time";

/** The days the server lists (`recent`): the last 30. */
export const DAYS = 30;

/** One day of the chart: its moment (local midnight), its key ("2026-10-31"), km² and searches. */
export interface Day { date: Date; key: string; km2: number; searches: number }

/** The last `DAYS` local days, oldest first, the last one today, with the searches finished on each. */
export function daysOf(area: AreaUsage, now: Date = new Date()): Day[] {
  const days: Day[] = [];
  for (let back = DAYS - 1; back >= 0; back--) {
    // Calendar arithmetic, not 24 h steps: a day of a clock change is 23 or 25 hours long
    const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back);
    days.push({date, key: day(date.toISOString()), km2: 0, searches: 0});
  }
  const byKey = new Map(days.map((d) => [d.key, d]));
  for (const [finished, km2] of area.recent) {
    const found = byKey.get(day(finished));
    if (found) { found.km2 += km2; found.searches += 1; }
  }
  return days;
}

/** The km² of the searches finished today (the viewer's day). */
export function todayKm2(area: AreaUsage, now: Date = new Date()): number {
  const today = day(now.toISOString());
  return area.recent.reduce((sum, [finished, km2]) => day(finished) === today ? sum + km2 : sum, 0);
}

/** An area for people: "0.07", "3.14", "12.5", "1,230" (km², the page's language). */
export function km2Text(value: number): string {
  if (value > 0 && value < 0.01) return "< 0.01";
  const digits = value < 10 ? 2 : value < 100 ? 1 : 0;
  return value.toLocaleString("en", {maximumFractionDigits: digits});
}

/** A count with thousands separators: "1,234". */
export const countText = (value: number): string => value.toLocaleString("en");

/** The name of a country of its ISO 3166-1 alpha-2 code ("pl": "Poland"); the code when the browser has none. */
export function countryName(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], {type: "region"}).of(code.toUpperCase()) || code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}
