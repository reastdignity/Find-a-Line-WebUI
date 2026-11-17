// A run's own map (map.html, from disk, from the app's server or a share link): the result as the app
// shows it by default (result/view/ResultColumns: C's columns, on phones a map with a sheet). map.html
// loads this bundle after the list of runs (../runs.js: window.FINDALINE_RUNS, none on a share link); the
// bundle loads the run's store or data.js beside it (result/load.ts: fetched with a progress bar from a server,
// data.js as a script from disk), or takes window.FINDALINE_RUN of a map.html written before 2026-11-04, which
// loaded data.js by a tag before it. The lines of other runs come from their store or lines.js (Compare). The
// load's failures are shown in their own words (too large, a newer store, a store or data.js not loaded). The
// selected line is the hash, #line=lat1,lon1,lat2,lon2 (keys.ts lineCoords), so a copied link opens it.
//
// The disk notice (store wave 4: docs/line-volume/spec-store.md 1.2): a map.html written since then carries it
// (mapping.MAP_HTML, the element NOTICE after this bundle's script). Over http(s) the page is marked served at once,
// before the notice is parsed, and notice.css hides it under that mark (viewer.css is loaded in the head), so no frame
// shows it; it is removed once the page is parsed. From disk (file://) the bundle waits for the parse: a page with
// the notice loads nothing and leaves it shown, in the stored theme; a page without it (written before) loads its
// data.js as before.

import "../leaflet";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import "../app/base.css";
import "./notice.css";
import { t } from "../i18n";
import { columnsOf, loadRunFrom, NewerStore, StoreFailed, TooLarge, type LoadProgress } from "../result/load";
import type { ResultModel } from "../result/model";
import { ResultColumns, type BackAction } from "../result/view/ResultColumns";
import { RunLoading } from "../result/view/RunLoading";
import { DESKTOP, Screen, useMedia } from "../ui/components";
import { storedTheme } from "../ui/choice";
import type { Line, RunData } from "../types";

const hashOf = (_runId: string, line: string | null) => line ? "#line=" + encodeURIComponent(line) : "";
const here = () => location.href.replace(/#.*$/, "");

/** "Copy link": this map with the line, or the map of the other run the line is from. */
function linkOf(model: ResultModel, l: Line): string {
  const id = model.runOf(l), hash = hashOf(id, model.lineLink(l));
  return id === model.runId ? here() + hash : new URL("../" + encodeURIComponent(id) + "/map.html" + hash, here()).href;
}

/** The way back: the list of runs beside the map on disk, the app on its server, none on a share link. */
function backOf(runId: string): BackAction | undefined {
  if (location.protocol === "file:") return {label: "All runs", onClick: () => { location.href = "../index.html"; }};
  if (location.pathname.startsWith("/s/")) return undefined;
  return {label: "Find-a-Line", onClick: () => { location.href = "/#run=" + encodeURIComponent(runId); }};
}

function RunMap({data}: {data: RunData}) {
  const wide = useMedia(DESKTOP);
  const [route, setRoute] = useState({line: location.hash || null, nav: 0});
  useEffect(() => {
    const changed = () => setRoute((r) => ({line: location.hash || null, nav: r.nav + 1}));
    addEventListener("hashchange", changed);
    return () => removeEventListener("hashchange", changed);
  }, []);
  // Compare needs another run it can show (RunActions: one with a map; others.listOthers: with lines and a box) in the
  // list of runs, which a share link has none of
  const others = (window.FINDALINE_RUNS || []).some((r) => r.id !== data.run.id && r.has_lines && r.has_map !== false
                                                         && r.bbox);
  const show = others ? undefined : (["measure", "share", "download"] as const).slice();
  return <Screen theme={storedTheme()}>
    <ResultColumns data={data} runId={data.run.id} line={route.line} nav={route.nav} wide={wide} back={backOf(data.run.id)}
                   hashOf={hashOf} linkOf={linkOf} base="../" folder="" show={show} />
  </Screen>;
}

/** The map once its data is in; meanwhile the load's progress (RunLoading), or its error. */
function LoadedMap() {
  // data.js loaded by a tag before the bundle (a map.html of before 2026-11-04): its rows as columns, then dropped
  const [data, setData] = useState<RunData | null>(() => {
    const script = window.FINDALINE_RUN;
    if (!script) return null;
    delete window.FINDALINE_RUN;
    return columnsOf(script);
  });
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (data) return;
    loadRunFrom("data.js", "map", setProgress)
      .then(setData, (e) => setError(e instanceof TooLarge || e instanceof NewerStore ? e.message
        : e instanceof StoreFailed ? t("ui.result.store_failed") : "The run's data (data.js) could not be loaded."));
  }, []);
  if (data) return <RunMap data={data} />;
  return <Screen theme={storedTheme()}><RunLoading progress={progress} error={error} /></Screen>;
}

/** mapping.DISK_NOTICE: the id of the disk notice in a run's map.html. */
export const NOTICE = "disk-notice";
const served = location.protocol === "http:" || location.protocol === "https:";

/** The map over http(s); from disk once the page is parsed: the notice when the page has one, else the map. */
function start() {
  const notice = document.getElementById(NOTICE);
  if (served) {
    notice?.remove();
    return;
  }
  if (notice) {
    const theme = storedTheme();
    if (theme !== "auto") notice.dataset.theme = theme;
    return;
  }
  render(<LoadedMap />, document.getElementById("map")!);
}

if (served) {
  document.documentElement.classList.add("fal-served");  // before the notice is parsed: notice.css hides it
  render(<LoadedMap />, document.getElementById("map")!);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
else start();
