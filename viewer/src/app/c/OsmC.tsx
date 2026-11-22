// The OpenStreetMap extracts (#osm, from the account; the local app and administrators): the
// Geofabrik regions at the map's centre to download, so the coastline and the cliffs come from the
// disk instead of the (often overloaded) Overpass API, and the downloaded extracts to update.

import { useEffect, useState } from "preact/hooks";
import { Button } from "../../ui/components";
import { api, type OsmState } from "../api";
import type { PlaceMap } from "../PlaceMap";
import { day } from "../../time";
import { parts, t } from "../../i18n";
import { Rich } from "../../ui/Intro";

export function OsmC({place, onStarted}: {place: PlaceMap; onStarted(): void}) {
  const [state, setState] = useState<OsmState | null>(null);
  const [error, setError] = useState("");
  const [where, setWhere] = useState("");

  const look = () => {
    const c = place.map.getCenter();
    setWhere(`${c.lat.toFixed(4)}, ${c.lng.toFixed(4)}`);
    setError("");
    api.osm(c.lat, c.lng).then(setState, (e) => setError(e.message));
  };
  useEffect(look, [place]);

  const start = (action: "download" | "update", region: string) =>
    api.osmJob(action, region).then(onStarted, (e) => setError(e.message));

  return <div class="c-osm">
    <p class="u-small"><Rich text={t("ui.osm.intro", {mode: t("intro.search.mode_cliffs")})} /></p>
    <h2 class="u-h4">{t("ui.osm.here")}</h2>
    <div class="c-admin-tools"><span class="u-small u-mono">{where}</span>
      <Button kind="ghost" icon="locate" onClick={look}>{t("ui.osm.again")}</Button></div>
    {error && <p class="c-error" role="alert">{error}</p>}
    {state && (state.regions.length ? <ul class="c-admin-list">{state.regions.map((r) => <li key={r.id} class="c-admin-row">
      <div class="c-admin-head"><b>{r.name}</b><span class="u-small u-mono">{r.id}</span>
        {r.downloaded ? <span class="u-badge">{t("ui.osm.downloaded")}</span>
          : <Button icon="download" onClick={() => start("download", r.id)}>{t("ui.osm.download")}</Button>}</div>
    </li>)}</ul> : <p class="u-small">{t("ui.osm.none_here")}</p>)}
    <h2 class="u-h4">{t("ui.osm.downloaded_title")}</h2>
    {state && (state.extracts.length ? <ul class="c-admin-list">{state.extracts.map((e) => <li key={e.id} class="c-admin-row">
      <div class="c-admin-head"><b>{e.id}</b>
        <Button kind="ghost" icon="refresh" onClick={() => start("update", e.id)}>{t("ui.osm.update")}</Button></div>
      <div class="u-small">{parts("ui.osm.meta", {mb: e.mb, data: day(e.data, "?"), checked: day(e.checked, "?")})}</div>
    </li>)}</ul> : <p class="u-small">{t("ui.osm.none")}</p>)}
  </div>;
}
