// A run's own map (map.html, from the app's server or a share link): the result as the app shows it by default
// (result/view/ResultColumns: C's columns, on phones a map with a sheet). map.html loads this bundle after the list
// of runs (../runs.js: window.FINDALINE_RUNS, none on a share link); the bundle loads the run's store beside it
// (result/load.ts: fetched with a progress bar). The lines of other runs come from their store (Compare). The
// load's failures are shown in their own words (too large, a newer store, a store not loaded: a run without one
// too), with the way back to the app's first page ("/": Home when signed in, else the sign-in page; also while the
// run still loads) and, for a store not loaded, "Try again" (the store is loaded again in the page); a share
// link's visitor has no way back: "Try again" and a sentence. The selected line is the hash,
// #line=lat1,lon1,lat2,lon2 (keys.ts lineCoords), so a copied link opens it. The run's name is the page's title's
// (runs.MAP_HTML, which a rename rewrites; the store's head keeps the name of the saving).
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
import { failureOf, loadRunFrom, type LoadFailure, type LoadProgress } from "../result/load";
import type { ResultModel } from "../result/model";
import { ResultColumns, type BackAction } from "../result/view/ResultColumns";
import { RunLoading } from "../result/view/RunLoading";
import { Button, DESKTOP, Screen, useMedia } from "../ui/components";
import { storedTheme } from "../ui/choice";
import type { Line, RunData } from "../types";
import { lineHash, shareToken } from "../sharelink";
import { view3dLink } from "../view3d/page";

const hashOf = (_runId: string, line: string | null) => lineHash(line);
const here = () => location.href.replace(/#.*$/, "");

/** "Copy link": this map with the line, or the map of the other run the line is from. */
function linkOf(model: ResultModel, l: Line): string {
  const id = model.runOf(l), hash = hashOf(id, model.lineLink(l));
  return id === model.runId ? here() + hash : new URL("../" + encodeURIComponent(id) + "/map.html" + hash, here()).href;
}

/** A share link's page (/s/<token>/map.html): its visitor has no app to go back to. */
const shared = () => location.pathname.startsWith("/s/");

/** A line's 3D view: on a share link's page only, the link's own (view3d#run=…&line=…, relative: /s/<token>/view3d,
 *  which asks with the link's token); the owner's /runs/<id>/map.html and a map from disk have none. */
const view3dOf = shareToken() !== null ? view3dLink("view3d") : undefined;

/** The way back: the app on its server, none on a share link. */
function backOf(runId: string): BackAction | undefined {
  if (shared()) return undefined;
  return {label: t("ui.map.back"), onClick: () => { location.href = "/#run=" + encodeURIComponent(runId); }};
}

const TITLE_END = / - Find-a-Line$/;  // runs.MAP_HTML: "<name> - Find-a-Line"

/** The run's name as the page's title has it, or null for a title of another form. A rename (runs.rename_run)
 *  rewrites the title; the store's head keeps the name of the saving, and a share link's page has no list of runs. */
function titleName(): string | null {
  return TITLE_END.test(document.title) ? document.title.replace(TITLE_END, "") || null : null;
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
                   hashOf={hashOf} linkOf={linkOf} view3dOf={view3dOf} base="../" folder="" show={show} />
  </Screen>;
}

/** The map once its data is in; meanwhile the load's progress (RunLoading), or its error. While it loads and
 *  when it failed the way back leads to the app's first page (not to the run in the app, where the same store
 *  would fail again); none on a share link. A store that could not be loaded gets "Try again" (the load started
 *  again here: a failed load is not kept), on a share link with the sentence what else to do. */
function LoadedMap() {
  const [data, setData] = useState<RunData | null>(null);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    setProgress(null);
    setError(null);
    loadRunFrom("./", "map", setProgress).then((run) => {
      const name = titleName();
      if (name) run.run.name = name;
      setData(run);
    }, (e) => setError(failureOf(e, true)));
  }, [tries]);
  if (data) return <RunMap data={data} />;
  const link = shared();
  return <Screen theme={storedTheme()}>
    <RunLoading main progress={progress} error={error?.text} onRetry={error?.again ? () => setTries((n) => n + 1) : undefined}
                more={link && error?.again ? t("ui.result.store_failed_shared") : undefined}>
      {!link && <Button kind="ghost" icon="back" class="c-back" onClick={() => { location.href = "/"; }}>{t("ui.map.back")}</Button>}
    </RunLoading>
  </Screen>;
}

/** mapping.DISK_NOTICE: the id of the disk notice in a run's map.html. */
export const NOTICE = "disk-notice";

/** The disk notice of a map.html written before store wave 4 (it has none): mapping.MAP_HTML's markup, the run's id
 *  from the page's folder, its name from the list of runs (../runs.js) when it names the run, else from the page's
 *  title (mapping: "<name> - Find-a-Line"), the sentence from the catalogue. */
function diskNotice(): HTMLElement {
  const parts = location.pathname.split("/"), id = decodeURIComponent(parts[parts.length - 2] || "");
  const name = (window.FINDALINE_RUNS || []).find((r) => r.id === id)?.name ?? titleName() ?? document.title;
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
