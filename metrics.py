"""
The metrics of the application for the monitoring of the public site (docs/monitoring.md, rows
F1-F17): `findaline.py web --public` serves them in the Prometheus text format on
its own port (--metrics-port, 8766; compose.yaml publishes it on the host's loopback only, and
nginx never proxies to it), read by Telegraf (deploy/monitoring/telegraf.conf) for the dashboard
and the alert rules of deploy/monitoring/grafana.

- One collector (Metrics) reads jobs.sqlite, accounts.sqlite and audit.sqlite at each scrape,
  through read-only connections of its own (aggregates only, short queries), the cache sizes
  the worker's housekeeping measures (jobs.write_cache_sizes) and the free disk. Totals are
  counted from the rows (COUNT, SUM), so they include what happened before the metrics; the
  answers of the quick lane, the requests per route and the open event streams are the web
  process's own counts since its start (web.RouteCounts, web.EventHub). The requests of the
  worker's processes to outside services are the running totals of the table service_requests
  (servicecounts); what the housekeeping removed and the coverage of the searches come from the
  files it writes (jobs.HOUSEKEEPING_FILE, jobs.COVERAGE_FILE), absent before its first round.
- Its own registry: only these metrics (no process or platform metrics of the client library).
- No label carries a user id, an IP address, a title, a place name or a path: statuses, phases,
  error codes, actions, countries (ISO 3166-1 alpha-2) and top-level cache folders only.
- The names are those of the contract with deploy/monitoring (grafana, telegraf.conf): renaming
  one breaks a panel or an alert rule there. A database that cannot be read (not there yet, or
  locked for longer than the timeout) leaves out its metrics in that scrape only.
"""

import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, Optional

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric, SummaryMetricFamily
from prometheus_client.registry import Collector, CollectorRegistry

import accounts as ac
import audit as au
import cache
import jobs as jb

SESSION_WINDOWS = {"15m": 15 * 60, "24h": 86400}  # findaline_sessions_active{window}
HOUR = 3600
QUICK_RESULTS = ("ok", "no_worker", "busy", "gone")  # web.QUICK_RESULTS
REFUSALS = ("rate", "quota", "other")
_FINISHED = "('done', 'failed', 'cancelled')"  # jobs.FINISHED in SQL
# The error of a failed job: the code of its error_info, else a category of its text (the messages of
# jobs.py: Scheduler._check, run_phase, INTERRUPTED); empty for a job that did not fail
ERROR_SQL = """CASE WHEN status != 'failed' THEN ''
    WHEN json_valid(error_info) AND json_extract(error_info, '$.code') IS NOT NULL
        THEN json_extract(error_info, '$.code')
    WHEN error LIKE 'time limit:%' THEN 'time_limit'
    WHEN error LIKE 'the worker stopped%' THEN 'worker_stopped'
    WHEN error LIKE 'internal error%' OR error LIKE '%(working grids kept in %' THEN 'internal'
    WHEN error LIKE 'interrupted%' THEN 'interrupted'
    ELSE 'other' END"""
# The phases of a job from the start times of migration 13 (rows from before have none): waiting for a
# download slot; downloading, until the computing starts (so with the wait for a compute slot in
# "ready") or the job ended in that phase; computing, until it ended. (start, end, which rows)
PHASES = {
    "waiting": ("created", "downloading_at", "downloading_at IS NOT NULL"),
    "download": ("downloading_at", "COALESCE(computing_at, finished)",
                 f"downloading_at IS NOT NULL AND (computing_at IS NOT NULL OR status IN {_FINISHED})"),
    "compute": ("computing_at", "finished", f"computing_at IS NOT NULL AND status IN {_FINISHED}"),
}


def _in(values) -> str:
    """Placeholders for an SQL IN (...) of these values."""
    return "(" + ", ".join("?" * len(values)) + ")"


def _seconds(start: str, end: str) -> str:
    """SQL: the seconds between two stored times (UTC ISO with offset, as the databases keep them)."""
    return f"(julianday({end}) - julianday({start})) * 86400.0"


def _read(path: Optional[str]) -> Optional[sqlite3.Connection]:
    """A read-only connection to a database, None when it does not exist."""
    if not path or not os.path.exists(path):
        return None
    return sqlite3.connect(Path(os.path.abspath(path)).as_uri() + "?mode=ro", uri=True, timeout=5)


def _family(kind, name: str, text: str, label: Optional[str], values: Dict, defaults: Iterable = ()) -> Metric:
    """A metric family of `kind` (GaugeMetricFamily, CounterMetricFamily) with one sample per entry of
    `values` ({label value: value}; without a label {"": value}) and 0 for the `defaults` missing in
    it, so a series exists before its first event."""
    family = kind(name, text, labels=[label] if label else [])
    for key in defaults:
        values.setdefault(key, 0)
    for key, value in sorted(values.items()):
        family.add_metric([key] if label else [], value)
    return family


def gauge(name: str, text: str, values, label: Optional[str] = None, defaults: Iterable = ()) -> Metric:
    return _family(GaugeMetricFamily, name, text, label, values if label else {"": values}, defaults)


def counter(name: str, text: str, values: Dict, label: str, defaults: Iterable = ()) -> Metric:
    return _family(CounterMetricFamily, name, text, label, values, defaults)


class Metrics(Collector):
    """The collector of the application's metrics (see the module's docstring). `limits`: the web
    process's settings.Limits (queue_max, the worker's slots); `accounts_dir`: the folder of
    accounts.sqlite (None: the local app, no accounts); `quick_answers`: the web app's counts of
    the waits for the quick lane (web.create_app's app.state.quick_answers); `routes`: its
    web.RouteCounts; `event_streams`: the number of open event streams (web.EventHub)."""

    def __init__(self, data_dir: str, limits=None, accounts_dir: Optional[str] = None,
                 quick_answers: Optional[Dict[str, int]] = None, routes=None,
                 event_streams: Optional[Callable[[], int]] = None):
        self.data_dir = data_dir
        self.routes, self.event_streams = routes, event_streams
        self.limits = limits
        self.jobs = os.path.join(data_dir, "jobs.sqlite")
        self.accounts = os.path.join(accounts_dir, "accounts.sqlite") if accounts_dir else None
        self.audit = os.path.join(data_dir, "audit.sqlite")  # the public site's only
        self.quick_answers = quick_answers

    def describe(self):
        return []  # read at every scrape: nothing to check at registration

    def collect(self) -> Iterator[Metric]:
        yield gauge("findaline_build_info", "The version of the application", {cache.VERSION: 1}, "version")
        for part in (self._jobs, self._services, self._accounts, self._audit, self._disk, self._housekeeping,
                     self._coverage):
            try:
                yield from part()
            except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as e:  # this scrape goes on without them
                print(f"metrics: {part.__name__}: {type(e).__name__}: {e}", file=sys.stderr)
        if self.quick_answers is not None:
            yield counter("findaline_quick_answers", "Waits for the quick lane by how they ended, since the start",
                          dict(self.quick_answers), "result", QUICK_RESULTS)
        if self.routes is not None:
            yield from self._routes()
        if self.event_streams is not None:
            yield gauge("findaline_event_streams", "Open event streams of the web process", self.event_streams())

    def _routes(self) -> Iterator[Metric]:
        found, seconds = self.routes.snapshot()
        requests = CounterMetricFamily("findaline_http_requests", "Requests of the web process by route template, "
                                       "method and status class, since its start", labels=["route", "method", "status"])
        for (route, method, status), n in sorted(found.items()):
            requests.add_metric([route, method, status], n)
        yield requests
        times = SummaryMetricFamily("findaline_http_request_seconds", "Time until the answer's headers per route "
                                    "template (the event stream left out), since the start", labels=["route"])
        for route, (n, total) in sorted(seconds.items()):
            times.add_metric([route], n, total)
        yield times

    def _services(self) -> Iterator[Metric]:
        db = _read(self.jobs)
        if db is None:
            return
        try:
            rows = db.execute("SELECT host, outcome, requests, bytes, seconds FROM service_requests").fetchall()
        except sqlite3.OperationalError:  # a database from before migration 14 (the web process migrates it)
            return
        finally:
            db.close()
        requests = CounterMetricFamily("findaline_service_requests", "Requests of the worker to outside services by "
                                       "host and outcome (each retry is a request)", labels=["host", "outcome"])
        size: Dict[str, float] = {}
        seconds: Dict[str, float] = {}
        for host, outcome, n, b, s in sorted(rows):
            requests.add_metric([host, outcome], n)
            size[host] = size.get(host, 0) + b
            seconds[host] = seconds.get(host, 0.0) + s
        yield requests
        yield counter("findaline_service_bytes", "Bytes received from outside services by host", size, "host")
        yield counter("findaline_service_seconds", "Seconds of the requests to outside services by host", seconds,
                      "host")

    def _work_file(self, name: str) -> Optional[Dict]:
        path = os.path.join(self.data_dir, "work", name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _housekeeping(self) -> Iterator[Metric]:
        found = self._work_file(jb.HOUSEKEEPING_FILE)
        if found is None:  # no round yet
            return
        removed = {str(k): v for k, v in (found.get("removed") or {}).items() if isinstance(v, (int, float))}
        yield gauge("findaline_housekeeping_removed", "What the last round of the housekeeping removed", removed,
                    "what")
        yield gauge("findaline_housekeeping_last_run_timestamp_seconds", "When the last round of the housekeeping "
                    "ended (Unix time)", float(found["time"]))
        yield gauge("findaline_housekeeping_seconds", "How long the last round of the housekeeping took",
                    float(found.get("seconds") or 0.0))

    def _coverage(self) -> Iterator[Metric]:
        found = self._work_file(jb.COVERAGE_FILE)
        if found is None:
            return
        yield gauge("findaline_coverage_km2", "Square kilometres searched at least once (finished searches)",
                    float(found["km2"]))
        cells = GaugeMetricFamily("findaline_searches_by_cell", "Finished searches whose area touches a cell of "
                                  "0.25 degrees, by the cell's south-west corner", labels=["lat", "lon"])
        for lat, lon, n in found.get("cells") or []:
            cells.add_metric([f"{lat:.2f}", f"{lon:.2f}"], n)
        yield cells

    def _jobs(self) -> Iterator[Metric]:
        db = _read(self.jobs)
        if db is None:
            return
        metrics = []
        try:
            now = time.time()
            q = lambda sql, *args: db.execute(sql, args).fetchall()  # noqa: E731
            one = lambda sql, *args: db.execute(sql, args).fetchone()[0]  # noqa: E731
            metrics.append(gauge("findaline_workers_alive", "Workers holding a live lease",
                                 one("SELECT COUNT(*) FROM workers WHERE expires > ?", now)))
            newest = one("SELECT MAX(expires) FROM workers")
            if newest is not None:  # the lease is renewed for LEASE seconds at each heartbeat
                metrics.append(gauge("findaline_worker_lease_age_seconds", "Age of the newest heartbeat of a worker",
                                     max(0.0, now - (newest - jb.LEASE))))
            statuses = jb.WAITING + jb.ACTIVE
            metrics.append(gauge("findaline_jobs", "Jobs in a status now", dict(q(
                f"SELECT status, COUNT(*) FROM jobs WHERE status IN {_in(statuses)} GROUP BY status", *statuses)),
                "status", statuses))
            if self.limits is not None:
                if self.limits.queue_max is not None:
                    metrics.append(gauge("findaline_queue_max", "Searches waiting or running at once on the site, at "
                                                                "most", self.limits.queue_max))
                metrics.append(gauge("findaline_slots", "The worker's slots of each phase",
                                     {"download": self.limits.download_slots, "compute": self.limits.compute_slots},
                                     "phase"))
            age = _seconds("MIN(created)", "'now'")
            oldest = one(f"SELECT {age} FROM jobs WHERE status IN {_in(jb.WAITING)}", *jb.WAITING)
            metrics.append(gauge("findaline_job_oldest_waiting_seconds", "Age of the oldest waiting job (queued or "
                                                                         "ready), 0 when none", max(0.0, oldest or 0.0)))
            finished = CounterMetricFamily("findaline_jobs_finished", "Finished jobs by result and error",
                                           labels=["status", "error"])
            found = {(status, error): n for status, error, n in q(
                f"SELECT status, {ERROR_SQL}, COUNT(*) FROM jobs WHERE status IN {_FINISHED} GROUP BY 1, 2")}
            for status in ("done", "cancelled"):
                found.setdefault((status, ""), 0)
            for (status, error), n in sorted(found.items()):
                finished.add_metric([status, error], n)
            metrics.append(finished)
            duration = SummaryMetricFamily("findaline_job_duration_seconds", "Time from queueing to the end of "
                                           "finished jobs", labels=["status"])
            found = {s: (n, total or 0.0) for s, n, total in q(
                f"SELECT status, COUNT(*), SUM({_seconds('created', 'finished')}) FROM jobs WHERE status IN "
                f"{_FINISHED} AND finished IS NOT NULL AND created IS NOT NULL GROUP BY status")}
            for status in jb.FINISHED:
                n, total = found.get(status, (0, 0.0))
                duration.add_metric([status], n, total)
            metrics.append(duration)
            phases = SummaryMetricFamily("findaline_job_phase_seconds", "Time of the phases of jobs (from the times "
                                         "stored since migration 13)", labels=["phase"])
            for phase, (start, end, rows) in PHASES.items():
                n, total = db.execute(f"SELECT COUNT(*), SUM({_seconds(start, end)}) FROM jobs WHERE {rows}").fetchone()
                phases.add_metric([phase], n, total or 0.0)
            metrics.append(phases)
            waiting, first = db.execute("SELECT COUNT(*), MIN(created) FROM quick WHERE status = 'waiting'").fetchone()
            metrics.append(gauge("findaline_quick_waiting", "Tasks waiting in the quick lane", waiting))
            metrics.append(gauge("findaline_quick_oldest_waiting_seconds", "Age of the oldest waiting task of the "
                                 "quick lane, 0 when none", max(0.0, now - first) if first is not None else 0.0))
            metrics.append(gauge("findaline_users_searched_in", "Users with a finished search in a country", dict(q(
                "SELECT country, COUNT(DISTINCT user_id) FROM jobs WHERE status = 'done' AND country IS NOT NULL "
                "GROUP BY country")), "country"))
            areas = q("SELECT COALESCE(country, 'unknown'), SUM(area_km2), COUNT(*) FROM jobs WHERE status = 'done' "
                      "AND area_km2 IS NOT NULL GROUP BY 1")
            metrics.append(counter("findaline_area_km2", "Square kilometres of finished searches by the country of their area",
                                   {c: km2 for c, km2, _ in areas}, "country"))
            metrics.append(counter("findaline_searches", "Finished searches with an area by the country of their area",
                                   {c: n for c, _, n in areas}, "country"))
            metrics.append(gauge("findaline_reports_open", "Open problem reports",
                                 one("SELECT COUNT(*) FROM reports WHERE status = 'open'")))
            runs, size = db.execute("SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM runs").fetchone()
            metrics.append(gauge("findaline_runs", "Saved runs with an owner's row", runs))
            metrics.append(gauge("findaline_runs_bytes", "Bytes of the saved runs", size))
            metrics.append(gauge("findaline_favourites", "Favourite lines of all users",
                                 one("SELECT COUNT(*) FROM favourites")))
        finally:
            db.close()
        yield from metrics

    def _accounts(self) -> Iterator[Metric]:
        db = _read(self.accounts)
        if db is None:  # the local app: no accounts
            return
        try:
            q = lambda sql, *args: db.execute(sql, args).fetchall()  # noqa: E731
            metrics = [
                gauge("findaline_users", "Accounts by status", dict(q("SELECT status, COUNT(*) FROM users GROUP BY "
                                                                      "status")), "status", ac.STATUSES),
                gauge("findaline_users_by_country", "Accounts by the country of their browser's time zone", dict(q(
                    "SELECT COALESCE(country, 'unknown'), COUNT(*) FROM users GROUP BY 1")), "country"),
                gauge("findaline_sessions_active", "Sessions with a request within the window", {
                    window: db.execute("SELECT COUNT(*) FROM sessions WHERE seen > ?",
                                       (time.time() - seconds,)).fetchone()[0]
                    for window, seconds in SESSION_WINDOWS.items()}, "window"),
            ]
        finally:
            db.close()
        yield from metrics

    def _audit(self) -> Iterator[Metric]:
        db = _read(self.audit)
        if db is None:  # the local app keeps no audit log
            return
        try:
            since = cache.now_iso(ago=HOUR)
            events = dict(db.execute("SELECT action, COUNT(*) FROM audit WHERE at >= ? GROUP BY action",
                                     (since,)).fetchall())
            # web.refused and Jobs.use: {"reason": "<kind> rate" for a rate, a quota's text; "status"}
            refusals = dict(db.execute(
                "SELECT CASE WHEN json_extract(detail, '$.reason') LIKE '% rate' THEN 'rate' "
                "WHEN json_extract(detail, '$.status') = 429 THEN 'quota' ELSE 'other' END, COUNT(*) "
                "FROM audit WHERE action = 'refused' AND at >= ? AND json_valid(detail) GROUP BY 1", (since,)).fetchall())
        finally:
            db.close()
        yield gauge("findaline_audit_events_last_hour", "Events of the audit log in the last hour", events, "action",
                    au.ACTIONS)
        yield gauge("findaline_refusals_last_hour", "Refusals by a rate, a quota or a safeguard in the last hour",
                    refusals, "kind", REFUSALS)

    def _disk(self) -> Iterator[Metric]:
        yield gauge("findaline_free_disk_bytes", "Free bytes of the disk of the data folder",
                    shutil.disk_usage(self.data_dir).free)
        path = os.path.join(self.data_dir, "work", jb.CACHE_SIZES)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                folders = json.load(f).get("folders", {})
            yield gauge("findaline_cache_bytes", "Bytes of each top-level folder of the cache (measured by the "
                                                 "worker's housekeeping)",
                        {str(k): v for k, v in folders.items() if isinstance(v, (int, float))}, "folder")


def registry(data_dir: str, limits=None, accounts_dir: Optional[str] = None,
             quick_answers: Optional[Dict[str, int]] = None, routes=None,
             event_streams: Optional[Callable[[], int]] = None) -> CollectorRegistry:
    """A registry with the application's metrics only."""
    found = CollectorRegistry(auto_describe=False)
    found.register(Metrics(data_dir, limits, accounts_dir, quick_answers, routes, event_streams))
    return found


def serve(port: int, addr: str, data_dir: str, limits=None, accounts_dir: Optional[str] = None,
          quick_answers: Optional[Dict[str, int]] = None, routes=None,
          event_streams: Optional[Callable[[], int]] = None):
    """Serve the metrics on `addr`:`port` from a thread of this process (prometheus_client's own
    HTTP server, any path); returns (server, thread)."""
    from prometheus_client import start_http_server
    return start_http_server(port, addr=addr, registry=registry(data_dir, limits, accounts_dir, quick_answers,
                                                                routes, event_streams))
