// The actions of a run: Measure (two points on the map; the profile opens in ProfileDock), Compare
// (other runs nearby shown with this one), Share (the public site: a link shown once) and Download
// (the run's lines as CSV and GeoJSON, made by the worker from the run's store for each download, where the page can
// ask for it: mayExport; no run keeps the files since store wave 4).

import type L from "leaflet";
import { useEffect, useRef, useState } from "preact/hooks";
import { Button, IconButton } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { api, ApiError, canChange, user, type RunListed } from "../../app/api";
import { t } from "../../i18n";
import { listOthers, NEARBY_KM, colorOf } from "../../others";
import type { Line, RunData, RunInfo } from "../../types";
import { loadOtherRun, loadRunList } from "../load";
import type { ResultModel } from "../model";
import { LinkField } from "./LineDetails";
import { Popover, Swatch, useModel } from "./common";
import { day } from "../../time";

/** What the run's actions need of the map: Measure's mode and its two points, Compare's box of the run's area. */
export interface RunActionsMap {
  readonly isMeasuring: boolean;
  onMeasuring(listener: (measuring: boolean) => void): () => void;
  startMeasure(done: (a: L.LatLng, b: L.LatLng) => void): void;
  cancelMeasure(): void;
  clearMeasure(): void;
  areaBounds(): L.LatLngBounds;
}

export interface RunActionsProps {
  model: ResultModel;
  view?: RunActionsMap | null;
  /** A measured line (or null when measuring starts again or fails): the shell shows it in ProfileDock. */
  onMeasured?(line: Line | null): void;
  /** Buttons with icons only (phones). */
  compact?: boolean;
  /** Which actions (default all that can work here). */
  show?: ("measure" | "compare" | "share" | "download")[];
  /** The folder of the runs' folders (default "/runs/"). */
  base?: string;
}

/** Measure: the next two clicks on the map; the profile between them is computed by the server. */
function Measure({model, view, onMeasured, compact}: RunActionsProps) {
  // The map's mode, not a copy: a phone turned round draws another RunActions while measuring goes on
  const [measuring, setMeasuring] = useState(!!view?.isMeasuring);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!view) return;
    setMeasuring(view.isMeasuring);
    return view.onMeasuring(setMeasuring);
  }, [view]);
  if (!view || !model.canCompute) return null;
  const toggle = () => {
    if (measuring) { view.cancelMeasure(); view.clearMeasure(); return; }
    setError("");
    onMeasured?.(null);
    view.startMeasure((a, b) => {
      model.measure([a.lat, a.lng], [b.lat, b.lng]).then((l) => onMeasured?.(l), (e) => {
        view.clearMeasure();
        setError("Not computed: " + e.message);
      });
    });
  };
  const label = measuring ? "Cancel measuring" : "Measure";
  return <span class="r-act">
    {compact ? <IconButton icon="ruler" label={label} on={measuring} onClick={toggle} />
      : <Button icon="ruler" class={measuring ? "r-on" : ""} aria-pressed={measuring} onClick={toggle}>
          {measuring ? "Cancel" : "Measure"}</Button>}
    {measuring && <span class="r-tip u-small">Click two points on the map</span>}
    {error && <span class="r-tip r-error u-small" role="alert">{error}
      <button type="button" class="r-note-x" aria-label="Close the message" onClick={() => setError("")}>
        <Icon name="close" /></button></span>}
  </span>;
}

interface OtherItem { run: RunInfo; km: number; status: "off" | "loading" | "on" | "error" }

/** Compare: other runs with lines, nearest first (the ones within NEARBY_KM unfolded). */
function Compare({model, view, compact, base = "/runs/"}: RunActionsProps) {
  const [items, setItems] = useState<OtherItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [farOpen, setFarOpen] = useState<boolean | null>(null);  // null: open when one of them is shown
  const load = () => {
    if (items) return;
    setFailed(false);
    loadRunList(base + "runs.js").then((runs) => {
      const b = view ? view.areaBounds() : null;
      const box = b ? [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
        : model.data.run.bbox || [model.data.center[1], model.data.center[0], model.data.center[1], model.data.center[0]];
      setItems(listOthers(runs.filter((r) => r.has_map !== false), model.runId, box)
        .map(({run, km}) => ({run, km, status: model.others.has(run.id) ? "on" : "off"})));
    }, () => setFailed(true));
  };
  const change = (item: OtherItem, status: OtherItem["status"]) =>
    setItems((all) => all && all.map((i) => i.run.id === item.run.id ? {...i, status} : i));
  const toggle = (item: OtherItem) => {
    if (item.status === "on" || item.status === "loading") { model.removeRun(item.run.id); change(item, "off"); return; }
    change(item, "loading");
    // its store's lines.arrow (load.ts loadOtherRun)
    loadOtherRun(item.run, base).then((lines) => { model.addRun(item.run, lines); change(item, "on"); },
                                      () => change(item, "error"));
  };
  const row = (item: OtherItem) => <label class="r-check r-other" key={item.run.id} title={item.run.description}>
    <input type="checkbox" checked={item.status === "on" || item.status === "loading"} onChange={() => toggle(item)} />
    <Swatch color={colorOf(item.run.id)} />
    <span class="u-grow">{item.run.name}<span class="u-small"> · {day(item.run.created)} · {item.km < 1 ? "here"
      : num0(item.km) + " km"}{item.status === "loading" ? " · loading…" : item.status === "error" ? " · no lines" : ""}</span></span>
  </label>;
  return <Popover label="Compare with other runs" align="right"
                  button={(open, toggleOpen) => compact
                    ? <IconButton icon="compare" label="Compare" expanded={open} onClick={() => { load(); toggleOpen(); }} />
                    : <Button icon="compare" aria-expanded={open} onClick={() => { load(); toggleOpen(); }}>Compare</Button>}>
    {() => {
      if (failed) return <p class="u-small r-error">The list of runs could not be loaded.{" "}
        <button type="button" class="r-link" onClick={load}>Try again</button></p>;
      if (!items) return <p class="u-small">Loading the runs…</p>;
      if (!items.length) return <p class="u-small">No other runs with lines.</p>;
      const near = items.filter((i) => i.km <= NEARBY_KM), far = items.filter((i) => i.km > NEARBY_KM);
      return <div class="r-others">
        <b class="u-h4">Show other runs with this one</b>
        {near.length ? near.map(row) : <p class="u-small">None within {NEARBY_KM} km.</p>}
        {far.length > 0 && <details open={farOpen ?? far.some((i) => i.status !== "off")}
                                    onToggle={(e) => setFarOpen((e.currentTarget as HTMLDetailsElement).open)}>
          <summary class="u-small">Farther away ({far.length})</summary>{far.map(row)}</details>}
      </div>;
    }}
  </Popover>;
}

const num0 = (v: number) => v.toFixed(0);

/** Share (the public site, the owner's runs): a link that opens the run's map for anyone who has it;
 *  nothing unless the run is the user's own. */
function Share({model, compact}: RunActionsProps) {
  const runId = model.runId;
  const [run, setRun] = useState<RunListed | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (user.local) return;
    api.runs().then((r) => setRun(r.public ? r.runs.find((x) => x.id === runId && x.own && x.has_map) || null
      : null), () => {});
  }, [runId]);
  if (!run || user.local) return null;
  const changed = (shared: boolean) => setRun({...run, shared});
  const share = () => api.share(run.id).then((r) => { setUrl(r.url); setError(""); changed(true); },
                                             (e) => setError(e.message));
  const stop = () => api.unshare(run.id).then(() => { setUrl(""); setError(""); changed(false); },
                                              (e) => setError(e.message));
  return <Popover label="Share" align="right"
                  button={(open, toggle) => compact ? <IconButton icon="share" label="Share" expanded={open} onClick={toggle} />
                    : <Button icon="share" aria-expanded={open} onClick={toggle}>Share</Button>}>
    <div class="r-share">
      <b class="u-h4">Share this run</b>
      <p class="u-small">A link opens the run's map for anyone who has it. It is shown once: copy it now.</p>
      {url && <LinkField text={url} />}
      <div class="u-row">
        <Button kind={run.shared ? "default" : "primary"} icon="link" onClick={share}>
          {run.shared ? "New link" : "Make a link"}</Button>
        {run.shared && <Button kind="danger" onClick={stop}>Stop sharing</Button>}
      </div>
      {run.shared && !url && <p class="u-small">Shared by a link. A new link replaces the old one.</p>}
      {error && <p class="r-error u-small" role="alert">{error}</p>}
    </div>
  </Popover>;
}

/** May this page ask the server to make this run's files (POST /api/runs/<id>/export)? The run was read from its
 *  store and the page can send changes: the app's page, where the user is signed in (or the local app's one user).
 *  A run's map.html has no token (a share link's page, a visitor's demo run, a run opened by its own address):
 *  the server would refuse, so a run with a store has no Download there. The one place of this rule. */
export const mayExport = (data: RunData): boolean => canChange && data.fromStore === true;

type Format = "csv" | "geojson";
const FORMATS: [Format, string, string][] = [["csv", "CSV", "table, every line"], ["geojson", "GeoJSON", "for GIS and map apps"]];
// Refusals the server words itself (their texts are the catalogue's, by the answer's code)
const WORDED = ["quick_waiting", "rate_export", "busy", "export_disk_full"];

/** The line a failed export shows: the two "no worker" cases in the export's own words, the server's text of a
 *  rate, a busy lane or a full disk, and one text for everything else (no network too). */
function exportError(e: unknown): string {
  const code = e instanceof ApiError ? e.info?.code : undefined;
  if (code === "no_worker") return t("ui.result.export_no_worker");
  if (code === "no_worker_local") return t("ui.result.export_no_worker_local");
  return e instanceof ApiError && code !== undefined && WORDED.includes(code) ? e.message : t("error.export_failed");
}

/** The browser saves the file at `url` (same origin, sent as an attachment): a link's click, never a fetch (a
 *  file may be over 1 GB), and the page stays whatever the address answers. */
function save(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";  // the name is the answer's (Content-Disposition)
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// The exports of this page's life by run id, outside the component as Measure's mode is on the map: the page
// draws another RunActions when its layout changes at 768 px (a phone turned) and when another run opens, and the
// wait goes on. `busy`: the file asked for and not answered yet; `error`: the line of the last failure, kept until
// that run's menu is closed (a run not on the page keeps it for its next menu).
interface Wait { busy: Format | null; error: string }
const IDLE: Wait = {busy: null, error: ""};
const waits = new Map<string, Wait>();
const drawn = new Set<() => void>();  // the mounted Exports: drawn again on a change
// The Download menu on the page, as its button last drew it: a failure of its run opens it through the button's toggle
let menu: {id: string; open: boolean; toggle(): void; of: object} | null = null;  // `of`: the Export that drew it

const waitOf = (id: string): Wait => waits.get(id) ?? IDLE;
function setWait(id: string, change: Partial<Wait>) {
  const next = {...waitOf(id), ...change};
  if (next.busy === null && !next.error) waits.delete(id);
  else waits.set(id, next);
  drawn.forEach((draw) => draw());
}

/** Something else has the person's attention: another menu of the actions is open, or the focus is in a field.
 *  A failure's line then waits for the Download menu's next opening (opening it would close that menu and take
 *  the focus). */
function elsewhere(): boolean {
  const at = document.activeElement;
  return document.querySelector(".r-pop") !== null
    || (at instanceof HTMLElement && (at.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(at.tagName)));
}

/** A run's file asked of the worker; one at a time for a run. Ready: the browser saves the answered address, if it
 *  is this run's export (anything else is a failure), also when the run is no longer on the page (it was asked
 *  for). A failure: its line into the run's wait, and its menu opened when it is on the page and closed and
 *  nothing else has the attention. */
function startExport(id: string, format: Format) {
  if (waitOf(id).busy) return;
  setWait(id, {busy: format, error: ""});
  const failed = (e: unknown) => {
    setWait(id, {busy: null, error: exportError(e)});
    if (menu && menu.id === id && !menu.open && !elsewhere()) menu.toggle();
  };
  api.exportRun(id, format).then((r) => {
    const url: unknown = r?.url;
    if (typeof url !== "string" || !url.startsWith(`/api/runs/${encodeURIComponent(id)}/export/`)) return failed(null);
    setWait(id, {busy: null});
    save(url);
  }, failed);
}

/** Download of a run read from its store: each row asks the worker for the file and waits ("Preparing the
 *  file…" in the pressed row, the other row off, the ring on the button), then the browser saves it; a failure is
 *  a red line under the rows, in a menu that opens again if it was closed (startExport). */
function Export({model, compact}: RunActionsProps) {
  const id = model.runId;
  const [, setDrawn] = useState(0);
  const self = useRef({id, open: false}).current;  // this Export's menu as its button last drew it
  useEffect(() => {
    const draw = () => setDrawn((n) => n + 1);
    drawn.add(draw);
    return () => {
      drawn.delete(draw);
      if (menu?.of === self) menu = null;
      // Gone with its menu open (the layout switched, another run opened): a line the person has seen is done,
      // as after a close; one not seen yet stays for the run's next menu
      if (self.open && waitOf(self.id).error) setWait(self.id, {error: ""});
    };
  }, []);
  const {busy, error} = waitOf(id);
  const ring = <span class="r-spin r-spin-ic" />;
  // One button in both states (the focus stays on it when the wait ends): the ring in the icon's place, and
  // its name says it waits. The phone's as IconButton draws its own, which takes an icon only.
  const button = (open: boolean, toggle: () => void) => {
    self.id = id;
    self.open = open;
    menu = {id, open, toggle, of: self};
    const mark = busy ? ring : <Icon name="download" />;
    const name = busy ? t("ui.result.export_preparing_label") : "Download";
    return compact
      ? <button type="button" class={open ? "u-ib u-on" : "u-ib"} aria-label={name} title={name} aria-expanded={open}
                onClick={toggle}>{mark}</button>
      : <Button aria-expanded={open} aria-label={busy ? name : undefined} onClick={toggle}>{mark}Download</Button>;
  };
  // A closed menu takes its failure's line with it
  return <Popover label="Download" align="right" onOpen={(now) => { if (!now && error) setWait(id, {error: ""}); }}
                  button={button}>
    <div class="r-downloads">
      <b class="u-h4">Download the lines</b>
      {FORMATS.map(([format, name, what]) =>
        <button type="button" class="u-btn" key={format} aria-busy={busy === format} disabled={busy !== null && busy !== format}
                onClick={() => startExport(id, format)}>{busy === format ? ring : <Icon name="download" />}
          {name} <span class="u-small">{busy === format ? t("ui.result.export_preparing") : what}</span></button>)}
      {error && <p class="u-small r-error" role="alert">{error}</p>}
    </div>
  </Popover>;
}

/** Download: the lines of the run as CSV and GeoJSON, made for each download where the page may ask (Export); no
 *  button elsewhere (a run's map.html, a share link). */
function Download(props: RunActionsProps) {
  return mayExport(props.model.data) ? <Export {...props} /> : null;
}

export function RunActions(props: RunActionsProps) {
  useModel(props.model);
  const show = props.show || ["measure", "compare", "share", "download"];
  return <div class="r-actions">
    {show.includes("measure") && <Measure {...props} />}
    {show.includes("compare") && <Compare {...props} />}
    {show.includes("share") && <Share {...props} />}
    {show.includes("download") && <Download {...props} />}
  </div>;
}
