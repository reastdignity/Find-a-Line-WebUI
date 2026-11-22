// The admin page of the public site (#admin, from the account): the
// server (workers, free disk, queue), the users (approve, block, without limits, end their sessions),
// every search with its owner (cancel), every run (open, the demo flag), the users' problem reports (done,
// delete) and a link to the OpenStreetMap extracts (their own page: they need a map). Every request is an
// administrator's only (web.py).

import { Fragment } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { Button, Panel, Stat, Stats, StatusChip, type Status } from "../../ui/components";
import { api, type AdminReport, type AdminRun, type AdminStatus, type AdminUser, type Job } from "../api";
import { runHash } from "./route";
import { day, when } from "../../time";
import { parts, t } from "../../i18n";

const JOBS_SHOWN = 50;
const at = (iso: string | null | undefined, empty = "?") => when(iso, empty);

/** A word of the server's (a job's, a user's or a report's status, a report's kind) from the catalogue: `prefix` and
 *  the value as its key, the value itself where the catalogue has none (a newer server's). */
const word = (prefix: string, value: string) => t(`${prefix}.${value}`, {defaultValue: value});

/** A job's status as a chip: its kind and its word (ui.admin.job.<status>). */
function jobStatus(job: Job): [Status, string] {
  const text = word("ui.admin.job", job.status);
  if (job.status === "done") return ["done", text];
  if (job.status === "failed" || job.status === "cancelled") return [job.status, text];
  if (job.status === "queued" || job.status === "ready") return ["waiting", text];
  return ["running", text];
}

/** One question of a list open at a time ("Block…", "Unblock…", "Delete…"), by its key ("<id> <act>"): `keep` closes
 *  it and puts the focus back on the button that opened it (the one whose data-asks is the key). */
function useQuestion() {
  const [asking, setAsking] = useState<string | null>(null);
  const [back, setBack] = useState<string | null>(null);
  useEffect(() => {
    if (back === null) return;
    document.querySelector<HTMLElement>(`[data-asks="${back}"]`)?.focus();
    setBack(null);
  }, [back]);
  return {asking, open: setAsking, done: () => setAsking(null), keep: () => { setBack(asking); setAsking(null); }};
}

/** A question in place of its row's tools: the act and "Keep", and nothing else in the row, so no neighbour above,
 *  under or beside it takes a finger's tap that misses (the browsers' touch adjustment). The focus goes to "Keep"
 *  when it opens; Escape is "Keep". */
function Question({act, kind, cls, title, onAct, onKeep}: {act: string; kind: "danger" | "primary"; cls: string;
                                                         title?: string; onAct(): void; onKeep(): void}) {
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => { box.current?.querySelector<HTMLElement>(".c-ask-keep")?.focus(); }, []);
  // .c-ask-pad: a press that does nothing, around and between the two buttons (c.css): a finger's tap there lands on it,
  // which the touch adjustment would otherwise move to the nearest button
  return <span ref={box} class="c-ask" onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onKeep(); } }}>
    <span class="c-ask-pad" aria-hidden="true" onClick={() => undefined} />
    <Button kind={kind} class={cls} title={title} onClick={onAct}>{act}</Button>
    <Button kind="ghost" class="c-ask-keep" onClick={onKeep}>{t("ui.admin.keep")}</Button>
  </span>;
}

/** A user's state as a badge's soft fill of its colour (the kit's .u-badge states); an administrator's neutral. */
const STATE_TONE: Record<string, string> = {approved: " u-ok", pending: " u-warn", blocked: " u-bad"};

function Users({users, onChange, onError}: {users: AdminUser[]; onChange(): void; onError(e: Error): void}) {
  // Block and Unblock ask first, as a report's "Delete…" does
  const q = useQuestion();
  const change = (p: Promise<unknown>) => p.then(onChange, onError);
  const status = (u: AdminUser, to: "approved" | "blocked") => { q.done(); change(api.adminSetUser(u.id, {status: to})); };
  if (!users.length) return <p class="u-small">{t("ui.admin.no_users")}</p>;
  return <ul class="c-admin-list">{users.map((u) => <li key={u.id} class="c-admin-row">
    <div class="c-admin-head">
      <b>{u.name}</b><span class="u-small u-mono">{u.provider}:{u.subject}</span>
      <span class={`u-badge c-user-${u.admin ? "admin" : u.status}${u.admin ? "" : STATE_TONE[u.status] ?? ""}`}>
        {u.admin ? t("ui.account.administrator") : word("ui.admin.user", u.status)}</span>
      {u.unlimited && !u.admin && <span class="u-badge">{t("ui.admin.without_limits")}</span>}
    </div>
    {/* labelled values, each word and value a text node of its own as before (a browser places the glyphs by them) */}
    <div class="u-small">{`${t("ui.admin.since")} `}{day(u.created, "?")}{` · ${t("ui.admin.last_sign_in")} `}
      {at(u.last_login, t("ui.admin.never"))}{" · "}{u.sessions} {t("ui.admin.sessions", {count: u.sessions})}</div>
    {/* the buttons first, the checkbox last: on a touch screen it stands on a line of its own (c.css .c-check) */}
    {!u.admin && <div class="c-admin-tools">
      {q.asking === `${u.id} block`
        ? <Question act={t("ui.admin.block_yes")} kind="danger" cls="c-user-block" title={t("ui.admin.block_title")}
                    onAct={() => status(u, "blocked")}
                    onKeep={q.keep} />
        : q.asking === `${u.id} unblock`
        ? <Question act={t("ui.admin.unblock_yes")} kind="primary" cls="c-user-unblock" onAct={() => status(u, "approved")}
                    onKeep={q.keep} />
        : <>
          {u.status === "pending" && <Button kind="primary" onClick={() => status(u, "approved")}>{t("ui.admin.approve")}</Button>}
          {u.status === "blocked" && <Button kind="primary" data-asks={`${u.id} unblock`}
            onClick={() => q.open(`${u.id} unblock`)}>{t("ui.admin.unblock")}</Button>}
          {u.status !== "blocked" && <Button kind="danger" title={t("ui.admin.block_title")} data-asks={`${u.id} block`}
            onClick={() => q.open(`${u.id} block`)}>{t("ui.admin.block")}</Button>}
          {u.sessions > 0 && <Button kind="ghost" title={t("ui.admin.end_title")}
            onClick={() => change(api.adminRevoke(u.id))}>{t("ui.admin.end")}</Button>}
          <label class="c-check"><input type="checkbox" class="u-check" checked={u.unlimited}
            onChange={(e) => change(api.adminSetUser(u.id, {unlimited: e.currentTarget.checked}))} />
            {t("ui.admin.without_limits_box")}</label>
        </>}
    </div>}
  </li>)}</ul>;
}

function Runs({runs, names, onChange, onError}: {runs: AdminRun[]; names: Map<number, string>; onChange(): void;
                                                onError(e: Error): void}) {
  if (!runs.length) return <p class="u-small">{t("ui.admin.no_runs")}</p>;
  return <ul class="c-admin-list">{runs.map((r) => <li key={r.run_id} class="c-admin-row">
    <div class="c-admin-head">
      <b>{r.name || r.run_id}</b>
      {r.shared && <StatusChip status="shared">{t("ui.admin.shared")}</StatusChip>}
      {r.visibility === "demo" && <span class="u-badge">{t("ui.admin.demo")}</span>}
    </div>
    <div class="u-small">{names.get(r.user_id ?? -1) || t("ui.admin.nobody")} · {(r.bytes / 1e6).toFixed(1)} MB · {at(r.created)}</div>
    <div class="c-admin-tools">
      {r.has_map && <Button kind="ghost" iconRight="next" href={runHash(r.run_id)}>{t("ui.common.open")}</Button>}
      <label class="c-check"><input type="checkbox" class="u-check" checked={r.visibility === "demo"}
        onChange={(e) => api.setDemo(r.run_id, e.currentTarget.checked).then(onChange, onError)} />
        {t("ui.admin.demo_box")}</label>
    </div>
  </li>)}</ul>;
}

function Reports({reports, onChange, onError}: {reports: AdminReport[]; onChange(): void; onError(e: Error): void}) {
  const q = useQuestion();
  const change = (p: Promise<unknown>) => p.then(onChange, onError);
  if (!reports.length) return <p class="u-small">{t("ui.admin.no_reports")}</p>;
  return <ul class="c-admin-list">{reports.map((r) => {
    const c = r.context;
    return <li key={r.id} class={"c-admin-row c-report" + (r.status === "done" ? " c-report-done" : "")} data-report={r.id}>
      <div class="c-admin-head">
        <span class="u-badge">{word("ui.admin.kind", r.category)}</span>
        <StatusChip status={r.status === "done" ? "done" : "waiting"}>{word("ui.admin.report", r.status)}</StatusChip>
        <b>{r.user_name || "?"}</b><span class="u-small">{at(r.created)}</span>
      </div>
      <p class="c-report-text">{r.text}</p>
      <div class="u-small c-report-context">
        {[c.run && (r.run_name
            ? <a href={runHash(c.run, c.line || null)}>{r.run_name}{c.line ? `, ${t("ui.admin.the_line")}` : ""}</a>
            : <span>{parts("ui.admin.run_deleted", {run: c.run})}</span>),
          c.page && <span>{parts("ui.admin.context_page", {page: c.page})}</span>,
          c.ui && <span>{parts("ui.admin.context_ui", {ui: c.ui})}</span>,
          c.viewport && <span>{parts("ui.admin.context_window", {viewport: c.viewport})}</span>]
          .filter(Boolean).map((part, i) => <Fragment key={i}>{i > 0 && "; "}{part}</Fragment>)}
        {c.user_agent && <div class="u-mono c-report-agent">{c.user_agent}</div>}
      </div>
      <div class="c-admin-tools">
        {q.asking === `${r.id} delete`
          ? <Question act={t("ui.admin.delete_yes")} kind="danger" cls="c-report-delete"
                      onAct={() => { q.done(); change(api.adminDeleteReport(r.id)); }} onKeep={q.keep} />
          : <>
            <Button kind={r.status === "open" ? "primary" : "default"}
                    onClick={() => change(api.adminReportStatus(r.id, r.status === "open" ? "done" : "open"))}>
              {t(r.status === "open" ? "ui.admin.report_done" : "ui.admin.reopen")}</Button>
            <Button kind="ghost" data-asks={`${r.id} delete`} onClick={() => q.open(`${r.id} delete`)}>
              {t("ui.common.delete_ask")}</Button>
          </>}
      </div>
    </li>;
  })}</ul>;
}

export function AdminC({jobs}: {jobs: Job[]}) {
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [runs, setRuns] = useState<AdminRun[]>([]);
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [error, setError] = useState("");
  const onError = (e: Error) => setError(e.message);
  const load = () => {
    setError("");
    api.adminStatus().then(setStatus, onError);
    api.adminUsers().then((r) => setUsers(r.users), onError);
    api.adminRuns().then((r) => setRuns(r.runs), onError);
    api.adminReports().then((r) => setReports(r.reports), onError);
  };
  useEffect(load, []);
  const names = new Map(users.map((u) => [u.id, u.name]));
  const pending = users.filter((u) => u.status === "pending").length;
  return <div class="c-page c-admin">
    <h1 class="u-h u-title">{t("ui.app.admin")}</h1>
    {error && <p class="c-error" role="alert">{error}</p>}
    <Panel title={t("ui.admin.server")} actions={<Button kind="ghost" icon="refresh" onClick={load}>{t("ui.admin.refresh")}</Button>}>
      {status && <>
        <Stats>
          <Stat value={status.workers.length} label={t("ui.admin.workers", {count: status.workers.length})} />
          <Stat value={status.free_gb} unit="GB" label={t("ui.admin.free_disk")} />
          <Stat value={status.queue} unit={status.queue_max !== null ? `/ ${status.queue_max}` : undefined}
                label={t("ui.admin.queue")} />
        </Stats>
        {(status.free_gb_min !== null || status.queue_max !== null) && <p class="u-small c-admin-limits">
          {[status.free_gb_min !== null && t("ui.admin.limit_disk", {gb: status.free_gb_min}),
            status.queue_max !== null && t("ui.admin.limit_queue", {count: status.queue_max})]
            .filter(Boolean).join(" ")}</p>}
        {status.workers.length ? <ul class="c-admin-workers u-small">{status.workers.map((w) =>
            <li key={w.id}>{parts("ui.admin.worker", {id: w.id, time: at(w.started)})}</li>)}</ul>
          : <p class="c-error">{t("ui.admin.no_worker")}</p>}
      </>}
    </Panel>
    <Panel title={pending ? t("ui.admin.users_waiting", {n: pending}) : t("ui.admin.users")}>
      <Users users={users} onChange={load} onError={onError} />
    </Panel>
    <Panel title={t("ui.admin.searches")}>
      {jobs.length ? <ul class="c-admin-list">{jobs.slice(0, JOBS_SHOWN).map((j) => {
        const [st, text] = jobStatus(j);
        const finished = ["done", "failed", "cancelled"].includes(j.status);
        return <li key={j.id} class="c-admin-row c-admin-job">
          <div class="c-admin-head"><b>{j.title}</b><StatusChip status={st}>{text}</StatusChip>
            {/* the same chip as the status beside it, in its quiet grey (not a smaller badge) */}
            {(j.removed_at || j.run_gone) && <span class="c-admin-removed"><StatusChip status="cancelled">
              {t(j.removed_at ? "ui.card.removed" : "ui.card.run_deleted")}</StatusChip></span>}</div>
          <div class="u-small">{j.user_id === undefined ? "?" : names.get(j.user_id ?? -1) || t("ui.admin.nobody")} · {at(j.created)}</div>
          {!finished && <div class="c-admin-tools">
            <Button kind="danger" onClick={() => api.cancel(j.id).catch(onError)}>{t("ui.common.cancel")}</Button></div>}
        </li>;
      })}</ul> : <p class="u-small">{t("ui.admin.no_searches")}</p>}
    </Panel>
    <Panel title={reports.some((r) => r.status === "open")
      ? t("ui.admin.reports_open", {n: reports.filter((r) => r.status === "open").length}) : t("ui.admin.reports")}>
      <Reports reports={reports} onChange={load} onError={onError} />
    </Panel>
    <Panel title={t("ui.admin.runs")}>
      <Runs runs={runs} names={names} onChange={load} onError={onError} />
    </Panel>
    <Panel title={t("ui.app.osm")}>
      <p class="u-small">{t("ui.admin.osm_text")}</p>
      <div class="c-admin-tools"><Button icon="layers" href="#osm">{t("ui.app.osm")}</Button></div>
    </Panel>
  </div>;
}
