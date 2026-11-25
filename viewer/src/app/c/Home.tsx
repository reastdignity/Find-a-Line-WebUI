// C's home (c1, c4 on phones): "New search", an example run, the user's searches as cards (the jobs of
// useJobs merged with the saved runs: status, progress, mini map, a menu), the favourite lines as a
// trip list, the area searched (Searched.tsx) and the usage meters aside (on phones the area under the cards).

import { useEffect, useRef, useState } from "preact/hooks";
import { Button, Chip, Chips, IconButton, Panel, Progress, StatusChip } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { LinkField, Popover } from "../../result/view";
import { count } from "../../result/view/common";
import { forgetRun, forgetRunList } from "../../result/load";
import { RenameForm } from "../../result/view/RunRename";
import { canReport, openReport } from "../../report";
import { UsageMeters, type UsageState } from "../../search";
import { api, jobError, user, type Job, type RunListed, type Usage } from "../api";
import { errorText, parts, t } from "../../i18n";
import { beingSaved, jobProgress, type JobsState, type JobView } from "../useJobs";
import { editHash, runHash } from "./route";
import { Thumb, ThumbCredit, type ThumbSource } from "./Thumb";
import { Trip } from "./Trip";
import { SearchedCard } from "./Searched";
import { timeOf, when } from "../../time";
import { sizeText } from "../../size";

export interface RunsState {
  runs: RunListed[] | null;
  public: boolean;
  error: string;
  reload(): void;
  change(id: string, change: Partial<RunListed> | null): void;  // null: removed
}

/** A card: a job, its run, or both (a finished job's run). */
export interface Card {
  key: string;
  job?: JobView;
  run?: RunListed;
  created: string;
}

/** The jobs and the user's own runs as cards, newest first; no card for a job its owner removed or whose run is
 *  gone (an administrator's list, and the local app's, still has those). */
export function cardsOf(jobs: JobView[], runs: RunListed[], publicSite: boolean): Card[] {
  const own = runs.filter((r) => r.own || !publicSite);
  const byId = new Map(own.map((r) => [r.id, r]));
  const used = new Set<string>();
  const cards: Card[] = jobs.filter((job) => !job.removed_at && !job.run_gone).map((job) => {
    const run = job.run_id ? byId.get(job.run_id) : undefined;
    if (run) used.add(run.id);
    return {key: "job:" + job.id, job, run, created: run?.created || job.created};
  });
  for (const run of own) {
    if (!used.has(run.id) && !beingSaved(run, jobs)) cards.push({key: "run:" + run.id, run, created: run.created});
  }
  return cards.sort((a, b) => timeOf(b.created) - timeOf(a.created));
}


/** "27 Oct 2026, 10:41" from an ISO time (as written, no time zone arithmetic). */

/** "1 spot", "1 162 480 lines": a count with its plural form from the catalogue, its thousands grouped as in the
 *  result view (common.tsx count). */
const spots = (n: number) => t("ui.result.spots", {count: n, n: count(n)});
const lines = (n: number) => t("ui.result.lines", {count: n, n: count(n)});

/** `counts`: a finished run's card, whose `meta` is its counts: the card writes them as a line of their own, over
 *  the line of the time and the size. */
type CardState = {status: "running" | "waiting" | "done" | "failed" | "cancelled" | "shared"; chip: string;
                  meta: string; fraction: number | null; step: string; unfinished: boolean; counts?: boolean};

function stateOf(card: Card): CardState {
  const {job, run} = card;
  if (job && job.status !== "done") {
    const p = jobProgress(job);
    if (p.state === "cancelled") {  // the user's own act: a quiet state, not a failure; the chip says it (no meta)
      return {status: "cancelled", chip: t("ui.kit.status.cancelled"), unfinished: false, meta: "", fraction: null, step: ""};
    }
    if (p.state === "failed") {
      return {status: "failed", chip: t("ui.kit.status.failed"), unfinished: false,
              meta: jobError(job) || t("ui.kit.status.failed"), fraction: null, step: ""};
    }
    const pct = p.fraction === null ? "" : ` ${Math.round(p.fraction * 100)}%`;
    return {status: p.state === "running" ? "running" : "waiting", unfinished: true,
            chip: p.state === "running" ? t("ui.kit.status.running") + pct : t("ui.kit.status.waiting"),
            meta: p.state === "running" ? p.label : job.status === "ready" ? p.label : t("ui.card.queued"),
            fraction: p.fraction, step: p.step};
  }
  if (run) {
    return {status: run.shared ? "shared" : "done", chip: t(run.shared ? "ui.kit.status.shared" : "ui.kit.status.done"),
            unfinished: false, meta: `${spots(run.summary.spots)} · ${lines(run.summary.lines)}`,
            fraction: null, step: "", counts: true};
  }
  return {status: "done", chip: t("ui.kit.status.done"), meta: t(job?.run_id ? "ui.card.saved" : "ui.card.finished"),
          fraction: null, step: "", unfinished: false};
}

/** Whether a removed search still counts toward the user's daily limit of searches, so Remove…'s question may say
 *  so: only when it is known true. The user has such a limit (the usage loaded and its jobs_day limit set: not on the
 *  local app, whose limits never count its searches, nor for administrators and accounts without limits), and the
 *  search started within the day's window (the usage's hours, jobs.DAY) by the page's clock now. */
export function countsToday(job: Job, usage: Usage | null, now = Date.now()): boolean {
  if (user.local || !usage || usage.usage.jobs_day.limit === null) return false;
  return now - timeOf(job.created) < usage.hours * 3600e3;
}

function thumbOf(card: Card): ThumbSource {
  if (card.run && card.run.has_map) return {kind: "run", id: card.run.id, lines: card.run.summary.lines};
  if (card.job) return {kind: "job", id: card.job.id};
  return {kind: "none"};
}

/** A search's card: the mini map and the name open a finished one; the menu edits, shares, deletes. */
/** ↑ ↓ Home End move the focus among the items of a menu. */
export function menuKeys(e: KeyboardEvent) {
  const items = Array.from((e.currentTarget as HTMLElement).querySelectorAll<HTMLElement>("[role=menuitem]"));
  const at = items.indexOf(document.activeElement as HTMLElement);
  const to = e.key === "ArrowDown" ? (at + 1) % items.length : e.key === "ArrowUp" ? (at - 1 + items.length) % items.length
    : e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : -1;
  if (to < 0 || !items.length) return;
  e.preventDefault();
  items[to].focus();
}

function SearchCard({card, runs, jobs, publicSite, highlight, usage, onGone}:
                    {card: Card; runs: RunsState; jobs: JobsState; publicSite: boolean; highlight: boolean;
                     usage: Usage | null; onGone(listed: Promise<boolean>): void}) {
  const {job, run} = card;
  const st = stateOf(card);
  const [panel, setPanel] = useState<"" | "share" | "rename" | "delete" | "remove">("");
  const [counts, setCounts] = useState(false);  // Remove…'s question says the search still counts (countsToday)
  const [menu, setMenu] = useState(false);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { if (highlight) ref.current?.scrollIntoView?.({block: "nearest"}); }, [highlight]);
  // A panel opened from the menu takes the focus (the safe choice of a confirmation) and is scrolled into view
  // whole (its scroll-margin keeps it above the phones' bottom bar, which lies over the scrolling page); closed,
  // the focus goes back to the menu's button
  const hadPanel = useRef(false);
  useEffect(() => {
    const card = ref.current;
    if (!card) return;
    if (panel) {
      const box = card.querySelector<HTMLElement>(".c-card-panel");
      box?.querySelector<HTMLElement>(".c-panel-first")?.focus({preventScroll: true});
      box?.scrollIntoView?.({block: "nearest"});
    } else if (hadPanel.current) card.querySelector<HTMLElement>(".c-card-menu")?.focus();
    hadPanel.current = !!panel;
  }, [panel]);
  // The panel again when a line is added to it (a refused name): on a low phone the line would stand under the bar
  const showPanel = () => ref.current?.querySelector<HTMLElement>(".c-card-panel")?.scrollIntoView?.({block: "nearest"});
  // The menu too is scrolled into view whole when it opens (a card low on a phone's screen: its last items lay
  // under the bottom bar)
  useEffect(() => {
    if (menu) ref.current?.querySelector<HTMLElement>(".r-pop")?.scrollIntoView?.({block: "nearest"});
  }, [menu]);
  const panelKeys = (e: KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setPanel(""); setUrl(""); }
  };
  const open = run && run.has_map ? runHash(run.id) : null;
  const name = run?.name || job?.title || t("ui.card.unnamed");
  const canShare = publicSite && !!run && run.own && run.has_map;
  const canDelete = publicSite && !!run && run.own;
  const canRename = publicSite && !!run && run.own;  // the owner's (a demo run's owner too); the server refuses anyone else
  const act = (then: () => void) => () => { setMenu(false); setError(""); then(); };
  // Renamed (the form, also one no longer drawn: another panel was opened while it waited): the card shows the
  // name as stored
  const renamed = (stored: string) => { runs.change(run!.id, {name: stored}); setPanel((now) => now === "rename" ? "" : now); };
  const share = () => api.share(run!.id).then((r) => { setUrl(r.url); runs.change(run!.id, {shared: true}); },
                                              (e) => setError(e.message));
  const unshare = () => api.unshare(run!.id).then(() => { setUrl(""); runs.change(run!.id, {shared: false}); },
                                                  (e) => setError(e.message));
  // The job that saved the run is then listed as one whose run is gone: listed again, its card goes with the run
  // (onGone with the listing: Home moves the focus on once the card is gone, and forgets it if the listing fails)
  const remove = () => api.deleteRun(run!.id).then(() => { forgetRun(run!.id); forgetRunList(); runs.change(run!.id, null);
                                                           onGone(jobs.refresh()); },
                                                   (e) => setError(e.message));
  const cancel = () => api.cancel(job!.id).then(() => jobs.refresh(), (e) => setError(e.message));
  const removeJob = () => api.removeJob(job!.id).then(() => onGone(jobs.refresh()), (e) => setError(e.message));
  const canRemove = !!job && job.status === "cancelled" && job.own === true;  // not another user's (an administrator's Home)
  const items = [
    open && <a key="open" role="menuitem" class="u-item c-menu-item" href={open}><Icon name="layers" />{t("ui.card.open")}</a>,
    job && <a key="edit" role="menuitem" class="u-item c-menu-item" href={editHash(job.id)}><Icon name="refresh" />{t("ui.app.edit_again")}</a>,
    canShare && <button key="share" type="button" role="menuitem" class="u-item c-menu-item" onClick={act(() => setPanel("share"))}>
      <Icon name="share" />{t("ui.card.share")}</button>,
    canRename && <button key="rename" type="button" role="menuitem" class="u-item c-menu-item" onClick={act(() => setPanel("rename"))}>
      <Icon name="edit" />{t("ui.card.rename")}</button>,
    job && st.unfinished && <button key="cancel" type="button" role="menuitem" class="u-item c-menu-item" onClick={act(cancel)}>
      <Icon name="stop" />{t("ui.card.cancel")}</button>,
    canReport() && <button key="report" type="button" role="menuitem" class="u-item c-menu-item"
                           onClick={act(() => openReport({about: name, context: run ? {run: run.id} : {}}))}>
      <Icon name="warn" />{t("ui.card.report")}</button>,
    canDelete && <button key="delete" type="button" role="menuitem" class="u-item c-menu-item c-danger" onClick={act(() => setPanel("delete"))}>
      <Icon name="bin" />{t("ui.common.delete_ask")}</button>,
    canRemove && <button key="remove" type="button" role="menuitem" class="u-item c-menu-item"
                         onClick={act(() => { setCounts(countsToday(job!, usage)); setPanel("remove"); })}>
      <Icon name="bin" />{t("ui.card.remove")}</button>,
  ].filter(Boolean);

  // Under the name a finished run has two fixed lines: its counts, then the time and its size as stored (none for
  // a run saved without the number); any other card one line as before
  const body = <>
    <span class="c-card-name">{name}</span>
    {st.counts && run ? <>
      <span class="u-small c-card-meta c-card-meta2">{st.meta}</span>
      <span class="u-small c-card-meta c-card-meta2">{[when(card.created), sizeText(run.bytes)].filter(Boolean).join(" · ")}</span>
    </> : <span class="u-small c-card-meta">{[st.meta, !st.unfinished && when(card.created)].filter(Boolean).join(" · ")}</span>}
  </>;
  return <article ref={ref} class={`c-card${highlight ? " c-card-new" : ""}`} data-job={job?.id} data-run={run?.id}
                  data-status={st.status}>
    {open ? <a class="c-card-thumb" href={open} tabIndex={-1} aria-hidden="true"><Thumb source={thumbOf(card)} /></a>
      : <div class="c-card-thumb"><Thumb source={thumbOf(card)} /></div>}
    <div class="c-card-body">
      <div class="c-card-head">
        <StatusChip status={st.status}>{st.chip}</StatusChip>
        {run?.demo && <span class="u-badge" title={t("ui.card.example_title")}>{t("ui.card.example")}</span>}
        <span class="u-grow" />
        {items.length > 0 && <Popover label={t("ui.card.actions_title")} align="right" open={menu} onOpen={setMenu}
                                      button={(on, toggle) => <IconButton icon="more" label={t("ui.card.actions")} plain expanded={on}
                                                                          class="c-card-menu" onClick={toggle} />}>
          <div class="c-menu" role="menu" onKeyDown={menuKeys}>{items}</div>
        </Popover>}
      </div>
      {open ? <a class="c-card-open" href={open}>{body}</a> : <div class="c-card-open">{body}</div>}
      {st.unfinished && <Progress value={st.status === "running" ? st.fraction : null} label={st.step || undefined} />}
      {error && <p class="c-error u-small" role="alert">{error}</p>}
    </div>
    {/* The panels under the thumbnail and the body, not in the body: on phones (a row) the card grows below
        its mini map, which keeps its size and zoom */}
    {panel === "share" && run && <div class="c-card-panel" role="dialog" aria-label={t("ui.card.share_title")} onKeyDown={panelKeys}>
      <span class="u-small">{t("ui.card.share_text")}</span>
      {url && <LinkField text={url} />}
      <div class="u-row">
        <Button kind={run.shared ? "default" : "primary"} icon="link" class="c-panel-first" onClick={share}>
          {t(run.shared ? "ui.card.share_new" : "ui.card.share_make")}</Button>
        {run.shared && <Button kind="danger" onClick={unshare}>{t("ui.card.share_stop")}</Button>}
        <Button kind="ghost" onClick={() => { setPanel(""); setUrl(""); }}>{t("ui.common.close")}</Button>
      </div>
    </div>}
    {panel === "rename" && run && <div class="c-card-panel" role="dialog" aria-label={t("ui.rename.title")} onKeyDown={panelKeys}>
      <RenameForm id={run.id} name={run.name} onRenamed={renamed} onClose={() => setPanel("")} onLine={showPanel} />
    </div>}
    {panel === "delete" && run && <div class="c-card-panel c-confirm" role="alertdialog" aria-label={t("ui.card.delete_title")}
                                       onKeyDown={panelKeys}>
      <span>{parts("ui.card.delete_ask", {name: run.name})}</span>
      <div class="u-row">
        <Button kind="danger" class="c-confirm-delete" onClick={remove}>{t("ui.common.delete")}</Button>
        <Button kind="ghost" class="c-panel-first" onClick={() => setPanel("")}>{t("ui.card.keep")}</Button>
      </div>
    </div>}
    {/* asks as Delete… does, but in the panel's own grey (not Delete…'s red): nothing but the card goes */}
    {panel === "remove" && job && <div class="c-card-panel c-remove-ask" role="alertdialog"
                                       aria-label={t("ui.card.remove_title")} onKeyDown={panelKeys}>
      <span>{t("ui.card.remove_ask", {name})}{counts && ` ${t("ui.card.remove_counts")}`}</span>
      <div class="u-row">
        <Button class="c-confirm-remove" onClick={removeJob}>{t("ui.card.remove_yes")}</Button>
        <Button kind="ghost" class="c-panel-first" onClick={() => setPanel("")}>{t("ui.card.keep")}</Button>
      </div>
    </div>}
  </article>;
}

type Show = "all" | "running" | "shared";

export interface HomeProps {
  jobs: JobsState;
  runs: RunsState;
  usage: UsageState;
  highlight: string;
  wide: boolean;
}

export function Home({jobs, runs, usage, highlight, wide}: HomeProps) {
  const [show, setShow] = useState<Show>("all");
  useEffect(() => { runs.reload(); usage.refresh(); }, []);
  const listed = runs.runs || [];
  const cards = cardsOf(jobs.jobs, listed, runs.public);
  const running = cards.filter((c) => stateOf(c).unfinished);
  const shared = cards.filter((c) => c.run?.shared);
  const shown = show === "running" ? running : show === "shared" ? shared : cards;
  // A card removed or deleted takes the focus with it: once it is gone, the focus goes to the card that took its
  // place (the last one if it was last), or to "Your searches" when none is left
  const list = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const going = useRef<{key: string; at: number} | null>(null);
  const gone = (key: string, at: number, listed: Promise<boolean>) => {
    const mark = {key, at};
    going.current = mark;
    listed.then((ok) => { if (!ok && going.current === mark) going.current = null; });  // never a late jump
  };
  useEffect(() => { going.current = null; }, [show]);  // another filter: the card left the view, not the list
  useEffect(() => {
    const pending = going.current;
    if (!pending || shown.some((c) => c.key === pending.key)) return;
    going.current = null;
    const left = Array.from(list.current?.querySelectorAll<HTMLElement>(":scope > .c-card") ?? []);
    const next = left[Math.min(pending.at, left.length - 1)];
    (next ? next.querySelector<HTMLElement>("a.c-card-open") ?? next.querySelector<HTMLElement>(".c-card-menu")
      : heading.current)?.focus();
  });
  const example = runs.public ? listed.find((r) => r.demo && r.has_map)
    : listed.filter((r) => r.has_map).sort((a, b) => timeOf(b.created) - timeOf(a.created))[0];

  return <div class="c-home">
    <div class="c-home-main">
      {!jobs.worker && <p class="c-error c-no-worker" role="alert">
        {errorText({code: user.local ? "no_worker_local" : "no_worker"})}</p>}
      {jobs.error && <p class="c-error">{jobs.error}</p>}
      {runs.error && <p class="c-error">{runs.error}</p>}
      <div class="c-starts">
        <a class="c-new" href="#new">
          <span class="c-new-icon"><Icon name="plus" /></span>
          <span><span class="u-h c-new-title">{t("ui.app.new_search")}</span>
            {wide && <span class="c-new-text">{t("ui.home.new_text")}</span>}</span>
        </a>
        {example && wide && <a class="c-example" href={runHash(example.id)} data-run={example.id}>
          <span class="c-example-icon"><Icon name="rope" /></span>
          <span><b>{t(runs.public ? "ui.home.example" : "ui.home.latest")}</b>
            <span class="u-small">{example.name} · {lines(example.summary.lines)}</span></span>
        </a>}
      </div>
      <div class="c-section-head">
        <h1 class="u-h u-title" ref={heading} tabIndex={-1}>{t("ui.home.searches")}</h1>
        <span class="u-small">{cards.length}</span>
        <span class="u-grow" />
        {wide ? <Chips>
          <Chip on={show === "all"} onClick={() => setShow("all")}>{t("ui.home.show_all")}</Chip>
          <Chip on={show === "running"} onClick={() => setShow("running")}>{t("ui.kit.status.running")}{running.length ? ` (${running.length})` : ""}</Chip>
          <Chip on={show === "shared"} onClick={() => setShow("shared")}>{t("ui.kit.status.shared")}{shared.length ? ` (${shared.length})` : ""}</Chip>
        </Chips> : <select class="u-input c-show" aria-label={t("ui.home.show")} value={show}
                           onChange={(e) => setShow(e.currentTarget.value as Show)}>
          <option value="all">{t("ui.home.show_all")}</option><option value="running">{t("ui.kit.status.running")}</option>
          <option value="shared">{t("ui.kit.status.shared")}</option>
        </select>}
      </div>
      {runs.runs === null ? <p class="u-small">{t("ui.common.loading")}</p> : shown.length === 0
        ? <p class="u-small c-empty">{t(show === "all" ? "ui.home.empty" : show === "running" ? "ui.home.empty_running"
            : "ui.home.empty_shared")}</p>
        : <div class="c-cards" ref={list}>{shown.map((c, at) =>
            <SearchCard key={c.key} card={c} runs={runs} jobs={jobs} publicSite={runs.public} usage={usage.usage}
                        highlight={!!highlight && c.job?.id === highlight}
                        onGone={(listed) => gone(c.key, at, listed)} />)}</div>}
      {runs.runs !== null && shown.length > 0 && <ThumbCredit />}
      {!wide && <SearchedCard usage={usage.usage} />}
      {!wide && example && <a class="c-example c-example-phone" href={runHash(example.id)} data-run={example.id}>
        <span class="c-example-icon"><Icon name="rope" /></span>
        <span><b>{t(runs.public ? "ui.home.example" : "ui.home.latest")}</b>
          <span class="u-small">{example.name}</span></span></a>}
    </div>
    {wide && <aside class="c-home-aside">
      <Panel title={t("ui.app.favourite_lines")} class="c-favs"><Trip limit={8} /></Panel>
      <SearchedCard usage={usage.usage} />
      {usage.usage && <Panel title={t("ui.home.today")} class="c-usage"><UsageMeters usage={usage.usage} /></Panel>}
    </aside>}
  </div>;
}
