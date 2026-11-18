// A run's own map (map.html, from the app's server or a share link): the result as the app shows it by default
// (result/view/ResultColumns: C's columns, on phones a map with a sheet). map.html loads this bundle after the list
// of runs (../runs.js: window.FINDALINE_RUNS, none on a share link); the bundle loads the run's store beside it
// (result/load.ts: fetched with a progress bar). The lines of other runs come from their store (Compare). The
// load's failures are shown in their own words (too large, a newer store, a store not loaded: a run without one
// too). The selected line is the hash, #line=lat1,lon1,lat2,lon2 (keys.ts lineCoords), so a copied link opens it.
//
// The disk notice (store wave 4: docs/line-volume/spec-store.md 1.2): a map.html written since then carries it
// (mapping.MAP_HTML, the element NOTICE after this bundle's script). Over http(s) the page is marked served by the
// bundle's first module (./served, before any other import runs), before the notice is parsed, and notice.css hides
// it under that mark (viewer.css is loaded in the head), so no frame shows it; it is removed once the page is parsed.
// From disk (file://) no run loads (store wave 4's item 5): the bundle waits for the parse and leaves the
// notice shown, in the stored theme; a page written before (no notice) gets the same notice built here
// (diskNotice: the run's id from the page's folder, its name from the list of runs or the page's title).

import { served } from "./served";  // first: marks a served page before any other module runs
import "../leaflet";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import "../app/base.css";
import "./notice.css";
import { t } from "../i18n";
import { loadRunFrom, NewerStore, StoreFailed, TooLarge, type LoadProgress } from "../result/load";
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

/** The way back: the app on its server, none on a share link. */
function backOf(runId: string): BackAction | undefined {
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
  const [data, setData] = useState<RunData | null>(null);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    loadRunFrom("./", "map", setProgress)
      .then(setData, (e) => setError(e instanceof TooLarge || e instanceof NewerStore || e instanceof StoreFailed
        ? e.message : t("ui.result.store_failed")));
  }, []);
  if (data) return <RunMap data={data} />;
  return <Screen theme={storedTheme()}><RunLoading progress={progress} error={error} /></Screen>;
}

/** mapping.DISK_NOTICE: the id of the disk notice in a run's map.html. */
export const NOTICE = "disk-notice";

/** The disk notice of a map.html written before store wave 4 (it has none): mapping.MAP_HTML's markup, the run's id
 *  from the page's folder, its name from the list of runs (../runs.js) when it names the run, else from the page's
 *  title (mapping: "<name> - Find-a-Line"), the sentence from the catalogue. */
function diskNotice(): HTMLElement {
  const parts = location.pathname.split("/"), id = decodeURIComponent(parts[parts.length - 2] || "");
  const name = (window.FINDALINE_RUNS || []).find((r) => r.id === id)?.name ?? document.title.replace(/ - Find-a-Line$/, "");
  const element = <K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text = "") => {
    const e = document.createElement(tag);
    e.className = cls;
    e.textContent = text;
    return e;
  };
  const notice = element("main", "ui fal-disk"), box = element("div", "fal-disk-box");
  const command = element("pre", "fal-disk-command");
  command.append(element("code", "", "findaline.py view " + id));
  notice.id = NOTICE;
  notice.dataset.run = id;
  box.append(element("h1", "fal-disk-name", name), element("p", "fal-disk-text", t("ui.map.disk_notice")), command);
  notice.append(box);
  document.body.append(notice);
  return notice;
}

/** Over http(s) the notice goes once the page is parsed; from disk it stays (built for a page without one), in the
 *  stored theme, and no run loads. */
function start() {
  const notice = document.getElementById(NOTICE);
  if (served) {
    notice?.remove();
    return;
  }
  const shown = notice ?? diskNotice(), theme = storedTheme();
  if (theme !== "auto") shown.dataset.theme = theme;
}

if (served) render(<LoadedMap />, document.getElementById("map")!);
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
else start();
