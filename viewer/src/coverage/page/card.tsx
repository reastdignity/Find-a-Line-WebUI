// The card of an area (a country, a region, a country's rest or the rest of the world) and the legend,
// both in the quality scale the reader chose: words (the default), everyday sizes or stars.
import { COVERAGE, areaOf, regionsOf } from "../data";
import { areaName, ct, noteText, resText, surveyText, type Lang } from "../i18n";
import type { Level } from "../types";
import { parseKey } from "./geo";

export type Scale = "words" | "life" | "stars";
export const SCALES: Scale[] = ["words", "life", "stars"];

// The icons of the facts (stroke in currentColor, as ui/icons.tsx)
const ICONS: Record<string, string> = {
  grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  tree: '<path d="M12 3l5 7h-3l4 6H6l4-6H7z"/><path d="M12 16v5"/>',
  notree: '<path d="M12 3l5 7h-3l4 6H6l4-6H7z"/><path d="M12 16v5M4 4l16 16"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  hole: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6v6H9z" stroke-dasharray="2 2"/>',
  ruler: '<path d="M3 15l12-12 6 6-12 12z"/><path d="M7 11l2 2M10 8l2 2M13 5l2 2"/>',
  db: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
};
const FactIcon = ({name}: {name: string}) =>
  <svg class="cov-ficon" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{__html: ICONS[name]}} />;

// The everyday sizes drawn to one scale: a person (1.75 m) next to a doormat, a car's space, a court
const LIFE: Record<Level, string> = {
  1: '<rect class="cov-f1" x="18" y="31" width="14" height="5" rx="1"/><circle class="cov-ink" cx="40" cy="20" r="2.2"/>' +
     '<path class="cov-stroke" d="M40 22.5v8M40 30.5l-2 5M40 30.5l2 5M40 25l-3 3M40 25l3 3"/>',
  2: '<rect class="cov-f2" x="4" y="18" width="34" height="18" rx="2"/><path class="cov-car" d="M10 30h22l-3-6H13z"/>' +
     '<circle class="cov-ink" cx="46" cy="20" r="2.2"/><path class="cov-stroke" d="M46 22.5v8M46 30.5l-2 5M46 30.5l2 5"/>',
  3: '<rect class="cov-f3 cov-stroke" x="2" y="8" width="50" height="28" rx="2"/><path class="cov-stroke" d="M27 8v28"/>' +
     '<circle class="cov-stroke" cx="27" cy="22" r="4"/><circle class="cov-ink" cx="44" cy="30" r=".9"/><path class="cov-stroke" d="M44 31v3"/>',
};
const LifeIcon = ({level}: {level: Level}) =>
  <svg class="cov-life" viewBox="0 0 54 40" aria-hidden="true"
       dangerouslySetInnerHTML={{__html: LIFE[level]}} />;

export const Stars = ({level}: {level: Level}) =>
  <span class="cov-stars" role="img" aria-label={`${4 - level}/3`}>{"★".repeat(4 - level)}
    <span class="cov-off">{"★".repeat(level - 1)}</span></span>;

/** The resolutions of a level as the legend tags them. */
export const LEVEL_TAGS: Record<Level, string> = {1: "≤ 1 m", 2: "2–5 m", 3: "30 m"};
const tagOf = (level: Level, lang: Lang) => (lang === "pl" ? LEVEL_TAGS[level].replace(".", ",") : LEVEL_TAGS[level]);

/** The level's name in a scale (the stars' own words, the everyday sizes, or the words). */
export function levelName(level: Level, scale: Scale, lang: Lang): string {
  return ct(lang, scale === "life" ? `life.${level}` : scale === "stars" ? `stars.${level}` : `level.${level}`);
}

function LevelBlock({level, res, scale, lang}: {level: Level; res: string; scale: Scale; lang: Lang}) {
  if (scale === "life") {
    return <div class="cov-lvl"><span class="cov-big">{res}</span>
      <span class="cov-lvl-text"><span class="cov-small cov-muted">{ct(lang, "life.head")}</span><b>{ct(lang, `life.${level}`)}</b></span>
      <LifeIcon level={level} /></div>;
  }
  if (scale === "stars") {
    return <div class="cov-lvl"><Stars level={level} /><span class="cov-big">{res}</span>
      <span class={`cov-pill cov-p${level}`}>{ct(lang, `stars.${level}`)}</span></div>;
  }
  return <div class="cov-lvl-words"><div class="cov-lvl"><span class="cov-big">{res}</span>
    <span class={`cov-pill cov-p${level}`}>{ct(lang, `level.${level}`)}</span></div>
    <p class="cov-small cov-muted">{ct(lang, `level.${level}.desc`)}</p></div>;
}

function Fact({icon, label, warn, children}: {icon: string; label: string; warn?: boolean; children: preact.ComponentChildren}) {
  return <div class={warn ? "cov-fact cov-warn" : "cov-fact"}><FactIcon name={icon} />
    <div><div class="cov-k">{label}</div><div>{children}</div></div></div>;
}

const NOTE_ICON = (code: string) => (code === "short" ? "ruler" : code === "gaps" || code === "mixed" ? "hole" : "info");

/** The card of `key` ("world" for the rest of the world); `onPick` opens another area's card (the regions
 *  of a country covered in some of them). */
export function Card({areaKey, lang, scale, onClose, onPick}:
                     {areaKey: string; lang: Lang; scale: Scale; onClose(): void; onPick(key: string): void}) {
  const {id, rest} = parseKey(areaKey);
  const area = rest || areaKey === "world" ? null : areaOf(id);
  const name = areaKey === "world" ? ct(lang, "world.name") : areaName(id, lang);
  const close = <button type="button" class="cov-x" aria-label={ct(lang, "close")} onClick={onClose}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg></button>;
  if (!area) {
    const world = COVERAGE.world, regions = rest ? [] : regionsOf(id);
    return <div class="cov-card-body">
      <div class="cov-head"><h2 class="cov-h">{name}</h2>{close}</div>
      <LevelBlock level={3} res={resText(world.res, lang)} scale={scale} lang={lang} />
      <div class="cov-facts">
        {rest && <Fact icon="hole" label={ct(lang, "fact.notes")}>{ct(lang, "page.rest")}</Fact>}
        {regions.length > 0 && <Fact icon="grid" label={ct(lang, "partly.rest")}>
          <ul class="cov-regions">{regions.map(r =>
            <li key={r}><button type="button" class="cov-link" onClick={() => onPick(r)}>{areaName(r, lang)}</button></li>)}</ul>
        </Fact>}
        <Fact icon="tree" label={ct(lang, "fact.trees")}>{ct(lang, "trees.rough")}</Fact>
        <Fact icon="db" label={ct(lang, "fact.data")}>{world.provider}</Fact>
        <Fact icon="info" label={ct(lang, "fact.notes")} warn>{ct(lang, "note.world")}</Fact>
      </div>
    </div>;
  }
  const survey = surveyText(area.survey, lang);
  return <div class="cov-card-body">
    <div class="cov-head"><div class="cov-title"><h2 class="cov-h">{name}</h2>
      {area.partial && <span class="cov-pill cov-hatched">{ct(lang, "legend.partial")}</span>}</div>{close}</div>
    <LevelBlock level={area.level} res={resText(area.res, lang)} scale={scale} lang={lang} />
    <div class="cov-facts">
      <Fact icon={area.trees === "no" ? "notree" : "tree"} label={ct(lang, "fact.trees")} warn={area.trees === "no"}>
        {ct(lang, `trees.${area.trees}`)}</Fact>
      {survey && <Fact icon="cal" label={ct(lang, "fact.survey")}>{survey}</Fact>}
      {area.notes.filter(n => n.code !== "no_trees").map(n =>
        <Fact key={n.code} icon={NOTE_ICON(n.code)} label={ct(lang, "fact.notes")} warn>{noteText(n, area, lang)}</Fact>)}
      <Fact icon="db" label={ct(lang, "fact.data")}>{area.provider}</Fact>
    </div>
  </div>;
}

/** The legend: the three levels in the chosen scale and the hatch of "only in parts"; the scale's switch. */
export function Legend({lang, scale, onScale}: {lang: Lang; scale: Scale; onScale(scale: Scale): void}) {
  const levels: Level[] = [1, 2, 3];
  return <div class="cov-legend-body">
    <div class="cov-legend-head"><span class="cov-label">{ct(lang, scale === "life" ? "life.head" : "legend.title")}</span></div>
    <ul class="cov-items">
      {levels.map(level => <li key={level} class="cov-it">
        <span class={`cov-sw cov-sw${level}`} />
        <span>{scale === "stars" && <span class="cov-stars-s" aria-hidden="true">{"★".repeat(4 - level)} </span>}
          {levelName(level, scale, lang)} <span class="cov-tag">{tagOf(level, lang)}</span></span></li>)}
      <li class="cov-it"><span class="cov-sw cov-swh" /><span>{ct(lang, "legend.partial")}</span></li>
    </ul>
    <div class="cov-scale" role="radiogroup" aria-label={ct(lang, "page.scale")}>
      {SCALES.map(s => <button type="button" key={s} role="radio" aria-checked={s === scale} class={s === scale ? "cov-on" : ""}
                               onClick={() => onScale(s)}>{ct(lang, `scale.${s}`)}</button>)}
    </div>
  </div>;
}
