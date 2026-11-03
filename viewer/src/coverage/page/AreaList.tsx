// Every area of the map as a table under it: what the colours say, in words, for screen readers and
// anyone who prefers reading (nothing on the page is told by colour alone). A row's name opens its card.
import { COVERAGE } from "../data";
import { areaName, ct, resText, type Lang } from "../i18n";
import type { Area, Level } from "../types";
import { levelName, type Scale } from "./card";

interface Row { key: string; name: string; level: Level; partial: boolean; res: number[]; trees: string; provider: string }

function rows(lang: Lang): Row[] {
  const name = (id: string) => {
    if (!id.includes("-")) return areaName(id, lang);
    return `${areaName(id, lang)} (${areaName(id.split("-")[0], lang)})`;
  };
  const listed = Object.entries(COVERAGE.areas).map(([id, area]: [string, Area]) => ({
    key: id, name: name(id), level: area.level, partial: area.partial, res: area.res, trees: area.trees, provider: area.provider,
  }));
  listed.sort((a, b) => a.name.localeCompare(b.name, lang));
  const world = COVERAGE.world;
  return [...listed, {key: "world", name: ct(lang, "world.name"), level: 3, partial: false, res: world.res,
                      trees: world.trees, provider: world.provider}];
}

export function AreaList({lang, scale, selected, onPick}:
                         {lang: Lang; scale: Scale; selected: string | null; onPick(key: string): void}) {
  return <section class="cov-list" aria-labelledby="cov-list-title">
    <h2 class="cov-h" id="cov-list-title">{ct(lang, "page.list.title")}</h2>
    <p class="cov-small cov-muted">{ct(lang, "page.list.lead")}</p>
    <table class="cov-table">
      <thead><tr>
        <th scope="col">{ct(lang, "page.col.area")}</th><th scope="col">{ct(lang, "level.of")}</th>
        <th scope="col">{ct(lang, "fact.res")}</th><th scope="col">{ct(lang, "fact.trees")}</th>
        <th scope="col">{ct(lang, "fact.data")}</th>
      </tr></thead>
      <tbody>{rows(lang).map(row =>
        <tr key={row.key} class={row.key === selected ? "cov-row-on" : undefined}>
          <th scope="row"><button type="button" class="cov-link" onClick={() => onPick(row.key)}>{row.name}</button></th>
          <td data-label={ct(lang, "level.of")}><span class={`cov-sw cov-sw${row.level}${row.partial ? " cov-swh" : ""}`} />
            <span>{levelName(row.level, scale, lang)}{row.partial && <span class="cov-muted"> · {ct(lang, "legend.partial")}</span>}</span></td>
          <td data-label={ct(lang, "fact.res")}>{resText(row.res, lang)}</td>
          <td data-label={ct(lang, "fact.trees")}>{ct(lang, `page.trees.${row.trees}`)}</td>
          <td data-label={ct(lang, "fact.data")}>{row.provider}</td>
        </tr>)}
      </tbody>
    </table>
  </section>;
}
