// A run's own map (map.html, from disk, from the app's server or a share link): the result as the app
// shows it by default (result/view/ResultColumns: C's columns, on phones a map with a sheet). map.html
// loads this bundle after the list of runs (../runs.js: window.FINDALINE_RUNS, none on a share link); the
// bundle loads the run's data.js beside it (result/load.ts: fetched with a progress bar from a server, a
// script from disk), or takes window.FINDALINE_RUN of a map.html written before 2026-11-04, which loaded
// data.js by a tag before it. The lines of other runs come from their lines.js (Compare). The selected line
// is the hash, #line=lat1,lon1,lat2,lon2 (keys.ts lineCoords), so a copied link opens it.

import "../leaflet";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import "../app/base.css";
import { loadRunFrom, type LoadProgress } from "../result/load";
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
  // Compare needs other runs with lines in the list of runs, which a share link has none of
  const others = (window.FINDALINE_RUNS || []).some((r) => r.id !== data.run.id && r.has_lines);
  const show = others ? undefined : (["measure", "share", "download"] as const).slice();
  return <Screen theme={storedTheme()}>
    <ResultColumns data={data} runId={data.run.id} line={route.line} nav={route.nav} wide={wide} back={backOf(data.run.id)}
                   hashOf={hashOf} linkOf={linkOf} base="../" folder="" show={show} />
  </Screen>;
}

/** The map once its data is in; meanwhile the load's progress (RunLoading), or its error. */
function LoadedMap() {
  const [data, setData] = useState<RunData | null>(window.FINDALINE_RUN ?? null);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (data) return;
    loadRunFrom("data.js", "map", setProgress)
      .then(setData, () => setError("The run's data (data.js) could not be loaded."));
  }, []);
  if (data) return <RunMap data={data} />;
  return <Screen theme={storedTheme()}><RunLoading progress={progress} error={error} /></Screen>;
}

render(<LoadedMap />, document.getElementById("map")!);
