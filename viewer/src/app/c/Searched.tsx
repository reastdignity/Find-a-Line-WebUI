// The area of the user's finished searches (app/searched.ts): a line in the account ("12 km² today ·
// 1,230 km² in 48 searches", the country from the browser's time zone) and the home page's card with the
// last 30 days as bars. Styles in c.css (c-searched-*).

import { useState } from "preact/hooks";
import { Panel, Stat, Stats } from "../../ui/components";
import { t } from "../../i18n";
import { dayMonth } from "../../time";
import type { Usage } from "../api";
import { countText, countryName, daysOf, km2Text, todayKm2, type Day } from "../searched";

/** The account's line; nothing before the first finished search (or from an older server). */
export function SearchedLine({usage}: {usage: Usage | null | undefined}) {
  const area = usage?.area;
  const country = usage?.country;
  if (!area?.searches && !country) return null;
  const today = area ? todayKm2(area) : 0;
  return <div class="c-searched-line u-small">
    {!!area?.searches && <span>
      {today > 0 && <>{t("ui.searched.today", {area: km2Text(today)})} · </>}
      {t("ui.searched.total", {count: area.searches, area: km2Text(area.total_km2), searches: countText(area.searches)})}
    </span>}
    {country && <span>{t("ui.searched.country", {country: countryName(country)})}</span>}
  </div>;
}

const dayText = (d: Day) => t("ui.searched.day", {count: d.searches, day: dayMonth(d.date), area: km2Text(d.km2),
                                                  searches: countText(d.searches)});

/** The 30 days as bars: hover, a tap or the arrow keys pick a day, whose numbers the line above them shows
 *  (a tap keeps its day until another tap or the focus leaves). */
function DayBars({days}: {days: Day[]}) {
  const [picked, setPicked] = useState<number | null>(null);
  const top = Math.max(...days.map((d) => d.km2));
  const month = days.reduce((sum, d) => sum + d.km2, 0);
  const at = (e: PointerEvent) => {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const i = Math.floor((e.clientX - box.left) / box.width * days.length);
    setPicked(Math.max(0, Math.min(days.length - 1, i)));
  };
  const keys = (e: KeyboardEvent) => {
    const last = days.length - 1, now = picked ?? last;
    const to = e.key === "ArrowLeft" ? Math.max(0, now - 1) : e.key === "ArrowRight" ? Math.min(last, now + 1)
      : e.key === "Home" ? 0 : e.key === "End" ? last : e.key === "Escape" ? null : undefined;
    if (to === undefined) return;
    e.preventDefault();
    setPicked(to);
  };
  return <div class="c-searched-chart">
    <div class="c-searched-readout" aria-live="polite">
      {picked === null ? t("ui.searched.month", {area: km2Text(month)}) : dayText(days[picked])}
    </div>
    <div class={`c-searched-bars${picked === null ? "" : " c-picked"}`} role="group" tabIndex={0}
         aria-label={t("ui.searched.chart")} onPointerMove={at} onPointerDown={at} onPointerLeave={(e) => { if (e.pointerType === "mouse") setPicked(null); }}
         onKeyDown={keys} onBlur={() => setPicked(null)}>
      <span class="c-searched-top u-small" aria-hidden="true">{top > 0 ? `${km2Text(top)} km²` : ""}</span>
      {days.map((d, i) => <span key={d.key} class={`c-searched-day${i === picked ? " u-on" : ""}${d.km2 ? "" : " c-zero"}`}>
        <i style={d.km2 ? {height: `${Math.max(3, d.km2 / top * 100)}%`} : undefined} /></span>)}
    </div>
    <div class="c-searched-axis u-small" aria-hidden="true">
      <span>{dayMonth(days[0].date)}</span><span>{t("ui.searched.today_axis")}</span>
    </div>
    <ul class="u-sr">{days.filter((d) => d.searches).map((d) => <li key={d.key}>{dayText(d)}</li>)}</ul>
  </div>;
}

/** The home page's card: the total, the searches and today, the last 30 days as bars; an empty state before the first. */
export function SearchedCard({usage}: {usage: Usage | null}) {
  const area = usage?.area;
  if (!area) return null;
  return <Panel title={t("ui.searched.title")} class="c-searched">
    {area.searches === 0 ? <p class="u-small c-searched-empty">{t("ui.searched.empty")}</p> : <>
      <Stats>
        <Stat value={km2Text(area.total_km2)} unit="km²" label={t("ui.searched.stat_total")} />
        <Stat value={countText(area.searches)} label={t("ui.searched.stat_searches", {count: area.searches})} />
        <Stat value={km2Text(todayKm2(area))} unit="km²" label={t("ui.searched.stat_today")} />
      </Stats>
      <DayBars days={daysOf(area)} />
    </>}
  </Panel>;
}
