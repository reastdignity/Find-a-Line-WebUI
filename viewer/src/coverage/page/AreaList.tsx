// Every area of the map as a list under it: what the colours say, in words, for screen readers and anyone who
// prefers reading (nothing on the page is told by colour alone). On a wide screen a table, a row's name opening
// its card; on a phone (PHONE: the page's own breakpoint, page.css) one row per area, the whole row a 48 px
// button with the level's colour, the name and the resolution, the card holding the rest (the user's pick L1 b,
// 2026-11-19: docs/DESIGN.md, "The pilot's look", choice 60).
import { useMedia } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { COVERAGE } from "../data";
import { areaName, ct, resText, type Lang } from "../i18n";
import type { Area, Level } from "../types";
import { Stars, levelName, type Scale } from "./card";

/** The page's phone layout (page.css's `max-width: 699px` blocks). */
export const PHONE = "(max-width: 699px)";

interface Row { key: string; name: string; parent: string; level: Level; partial: boolean; res: number[]; trees: string; provider: string }

function rows(lang: Lang): Row[] {
  const listed = Object.entries(COVERAGE.areas).map(([id, area]: [string, Area]) => ({
    key: id, name: areaName(id, lang), parent: id.includes("-") ? areaName(id.split("-")[0], lang) : "",
    level: area.level, partial: area.partial, res: area.res, trees: area.trees, provider: area.provider,
  }));
  const full = (row: Row) => (row.parent ? `${row.name} (${row.parent})` : row.name);
  listed.sort((a, b) => full(a).localeCompare(full(b), lang));
  const world = COVERAGE.world;
  return [...listed, {key: "world", name: ct(lang, "world.name"), parent: "", level: 3, partial: false, res: world.res,
                      trees: world.trees, provider: world.provider}];
}

const swatch = (row: Row) => <span class={`cov-sw cov-sw${row.level}${row.partial ? " cov-swh" : ""}`} />;

export function AreaList({lang, scale, selected, onPick}:
                         {lang: Lang; scale: Scale; selected: string | null; onPick(key: string): void}) {
  const phone = useMedia(PHONE);
  const stars = scale === "stars";
  return <section class="cov-list" aria-labelledby="cov-list-title">
    <h2 class="cov-h" id="cov-list-title">{ct(lang, "page.list.title")}</h2>
    <p class="cov-small cov-muted">{ct(lang, "page.list.lead")}</p>
    {phone ? <ul class="cov-rows">{rows(lang).map(row =>
      <li key={row.key}><button type="button" class={row.key === selected ? "cov-row cov-row-on" : "cov-row"}
                                onClick={() => onPick(row.key)}>
        {swatch(row)}
        <span class="cov-rname">{row.name}{row.parent && <span class="cov-rparent"> ({row.parent})</span>}</span>
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
          <th scope="row"><button type="button" class="cov-link cov-name-link" onClick={() => onPick(row.key)}>
            {row.parent ? `${row.name} (${row.parent})` : row.name}</button></th>
          <td><span class="cov-level">{swatch(row)}{stars && <Stars level={row.level} small />}
            <span>{levelName(row.level, scale, lang)}{row.partial && <span class="cov-muted">, {ct(lang, "legend.partial").toLowerCase()}</span>}</span></span></td>
          <td>{resText(row.res, lang)}</td>
          <td>{ct(lang, `page.trees.${row.trees}`)}</td>
          <td>{row.provider}</td>
        </tr>)}
      </tbody>
    </table>}
  </section>;
}
