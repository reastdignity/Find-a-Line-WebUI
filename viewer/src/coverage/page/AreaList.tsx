// Every area of the map as a list under it: what the colours say, in words, for screen readers and anyone who
// prefers reading (nothing on the page is told by colour alone). On a wide screen a table, a row's name opening
// its card; on a phone (PHONE: the page's own breakpoint, page.css) one row per area, the whole row a 48 px
// button with the level's colour, the name and the resolution, the card holding the rest (the user's pick L1 b,
// 2026-11-19: docs/DESIGN.md, "The pilot's look", choice 60); the level's word and "only in parts" are in the
// row's accessible name, not drawn. A country covered only in some regions (coverage.json's `partly`) has a row
// too, "<country> (rest of the country)" at the world's level: the way to its card, which lists its regions, by
// keyboard and where its shape is too small to tap.
import { useMedia } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { COVERAGE } from "../data";
import { areaName, ct, resText, type Lang } from "../i18n";
import type { Area, Level } from "../types";
import { Stars, levelName, type Scale } from "./card";

/** The page's phone layout: the list as rows and the card as a sheet (page.css's `max-width: 699px` blocks; the
 *  header's own phone test there is wider: .claude/rules/coverage-map.md). */
export const PHONE = "(max-width: 699px)";

/** `note`: what follows the name in brackets (a region's country, "rest of the country"). */
interface Row { key: string; name: string; note: string; level: Level; partial: boolean; res: number[]; trees: string; provider: string }

function rows(lang: Lang): Row[] {
  const world = COVERAGE.world;
  const rest = {level: 3 as Level, partial: false, res: world.res, trees: world.trees, provider: world.provider};
  const listed: Row[] = Object.entries(COVERAGE.areas).map(([id, area]: [string, Area]) => ({
    key: id, name: areaName(id, lang), note: id.includes("-") ? areaName(id.split("-")[0], lang) : "",
    level: area.level, partial: area.partial, res: area.res, trees: area.trees, provider: area.provider,
  }));
  for (const id of Object.keys(COVERAGE.partly)) {
    if (!COVERAGE.areas[id]) listed.push({key: id, name: areaName(id, lang), note: ct(lang, "page.list.rest"), ...rest});
  }
  listed.sort((a, b) => fullName(a).localeCompare(fullName(b), lang));
  return [...listed, {key: "world", name: ct(lang, "world.name"), note: "", ...rest}];
}

const fullName = (row: Row) => (row.note ? `${row.name} (${row.note})` : row.name);
const swatch = (row: Row) => <span class={`cov-sw cov-sw${row.level}${row.partial ? " cov-swh" : ""}`} />;

/** `onPick(key, true)`: a row was pressed (the page keeps the list's place and comes back to the row). */
export function AreaList({lang, scale, selected, onPick}:
                         {lang: Lang; scale: Scale; selected: string | null; onPick(key: string, fromList: boolean): void}) {
  const phone = useMedia(PHONE);
  const stars = scale === "stars";
  const partly = `, ${ct(lang, "legend.partial").toLowerCase()}`;
  return <section class="cov-list" aria-labelledby="cov-list-title">
    <h2 class="cov-h" id="cov-list-title">{ct(lang, "page.list.title")}</h2>
    <p class="cov-small cov-muted">{ct(lang, "page.list.lead")}</p>
    {phone ? <ul class="cov-rows">{rows(lang).map(row =>
      <li key={row.key}><button type="button" class={row.key === selected ? "cov-row cov-row-on" : "cov-row"}
                                data-row={row.key} onClick={() => onPick(row.key, true)}>
        {swatch(row)}
        <span class="cov-rname">{row.name}{row.note && <span class="cov-rparent"> ({row.note})</span>}
          <span class="u-sr">, {levelName(row.level, scale, lang)}{row.partial ? partly : ""},</span></span>
        <span class="cov-rdet">{stars && <Stars level={row.level} small />}{resText(row.res, lang)}</span>
        <Icon name="next" />
      </button></li>)}
    </ul> : <table class="cov-table">
      <thead><tr>
        <th scope="col">{ct(lang, "page.col.area")}</th><th scope="col">{ct(lang, "level.of")}</th>
        <th scope="col">{ct(lang, "fact.res")}</th><th scope="col">{ct(lang, "fact.trees")}</th>
        <th scope="col">{ct(lang, "fact.data")}</th>
      </tr></thead>
      <tbody>{rows(lang).map(row =>
        <tr key={row.key} class={row.key === selected ? "cov-row-on" : undefined}>
          <th scope="row"><button type="button" class="u-link cov-link cov-name-link" data-row={row.key}
                                  onClick={() => onPick(row.key, true)}>{fullName(row)}</button></th>
          <td><span class="cov-level">{swatch(row)}{stars && <Stars level={row.level} small />}
            <span>{levelName(row.level, scale, lang)}{row.partial && <span class="cov-muted">{partly}</span>}</span></span></td>
          <td>{resText(row.res, lang)}</td>
          <td>{ct(lang, `page.trees.${row.trees}`)}</td>
          <td>{row.provider}</td>
        </tr>)}
      </tbody>
    </table>}
  </section>;
}
