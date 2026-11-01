"""The application's metrics (metrics.py; docs/monitoring.md, rows F1-F19): the names and labels of
the contract with deploy/monitoring (Grafana's dashboard and alert rules, Telegraf), their values on
a scratch data folder, no personal data in any label, the port of `web --public`, the cache sizes,
what the worker's housekeeping removed and the coverage of the searches (with shapes of known
areas), and the requests per route of the web process."""

import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import accounts as ac  # noqa: E402
import audit  # noqa: E402
import cache  # noqa: E402
import jobs as jb  # noqa: E402
import metrics  # noqa: E402
import servicecounts  # noqa: E402
from settings import AccountSettings, Limits  # noqa: E402

pytest.importorskip("prometheus_client")
from prometheus_client import generate_latest  # noqa: E402
from prometheus_client.parser import text_string_to_metric_families  # noqa: E402

# The samples of the contract (sample name -> its labels); the dashboard and the alert rules use these
CONTRACT = {
    "findaline_build_info": {"version"},
    "findaline_workers_alive": set(),
    "findaline_worker_lease_age_seconds": set(),
    "findaline_jobs": {"status"},
    "findaline_queue_max": set(),
    "findaline_slots": {"phase"},
    "findaline_job_oldest_waiting_seconds": set(),
    "findaline_jobs_finished_total": {"status", "error"},
    "findaline_job_duration_seconds_sum": {"status"},
    "findaline_job_duration_seconds_count": {"status"},
    "findaline_job_phase_seconds_sum": {"phase"},
    "findaline_job_phase_seconds_count": {"phase"},
    "findaline_quick_waiting": set(),
    "findaline_quick_oldest_waiting_seconds": set(),
    "findaline_quick_answers_total": {"result"},
    "findaline_users": {"status"},
    "findaline_users_by_country": {"country"},
    "findaline_users_searched_in": {"country"},
    "findaline_sessions_active": {"window"},
    "findaline_audit_events_last_hour": {"action"},
    "findaline_refusals_last_hour": {"kind"},
    "findaline_reports_open": set(),
    "findaline_runs": set(),
    "findaline_runs_bytes": set(),
    "findaline_cache_bytes": {"folder"},
    "findaline_free_disk_bytes": set(),
    "findaline_area_km2_total": {"country"},
    "findaline_searches_total": {"country"},
    "findaline_favourites": set(),
    "findaline_service_requests_total": {"host", "outcome"},
    "findaline_service_bytes_total": {"host"},
    "findaline_service_seconds_total": {"host"},
    "findaline_http_requests_total": {"route", "method", "status"},
    "findaline_http_request_seconds_sum": {"route"},
    "findaline_http_request_seconds_count": {"route"},
    "findaline_event_streams": set(),
    "findaline_housekeeping_removed": {"what"},
    "findaline_housekeeping_last_run_timestamp_seconds": set(),
    "findaline_housekeeping_seconds": set(),
    "findaline_coverage_km2": set(),
    "findaline_searches_by_cell": {"lat", "lon"},
    "findaline_computed_mpx_total": {"resolution"},
    "findaline_computed_seconds_total": {"resolution"},
    "findaline_compute_step_seconds_sum": {"step"},
    "findaline_compute_step_seconds_count": {"step"},
    "findaline_compute_step_cpu_seconds_sum": {"step"},
    "findaline_compute_step_cpu_seconds_count": {"step"},
    "findaline_compute_stage_seconds_sum": {"stage"},
    "findaline_compute_stage_seconds_count": {"stage"},
    "findaline_compute_stage_cpu_seconds_sum": {"stage"},
    "findaline_compute_stage_cpu_seconds_count": {"stage"},
    "findaline_line_funnel_total": {"level"},
    **{f"{name}_total": {"layer", "role"} for name in metrics.LAYER_COUNTS},
}
# A square of about 1 km (0.009 degrees of latitude) in the cell of 50.00 N, 19.75 E
SQUARE = {"type": "Polygon", "coordinates": [[[19.80, 50.10], [19.81, 50.10], [19.81, 50.109], [19.80, 50.109],
                                              [19.80, 50.10]]]}
SECRET = {"title": "Secret Title of Zakopane", "name": "Secret Name", "run": "run-secret-4242", "user": 4242}
ACCOUNTS = AccountSettings(session_secret="s" * 40, github_client_id="id", github_client_secret="secret",
                           admins="github:1")


def _job(jobs, user_id, status, error=None, area=None, country=None, title="a search", phases=(), outline=None,
         resolution=None):
    job = jobs.add({"params": {}}, title, user_id)
    for waiting, working in phases:  # ("queued", "downloading"), ("ready", "computing")
        if waiting == "ready":
            jobs.set(job, "ready")
        assert jobs.claim(waiting, working, "w")["id"] == job
    if area is not None:
        jobs.set_area(job, area, country, outline)
    if resolution is not None:
        jobs.set_search(job, "poland", resolution)
    if status != "queued":
        jobs.set(job, status, error=error)
    return job


@pytest.fixture
def data(tmp_path):
    """A data folder with jobs of every kind, accounts, sessions, audit events, reports, runs,
    favourites, quick tasks and the cache sizes; returns (data folder, user ids)."""
    users = ac.Accounts(str(tmp_path), ACCOUNTS)
    ids = {}
    for subject, name, status, country in (("11", "a", "approved", "pl"), ("12", SECRET["name"], "approved", None),
                                           ("13", "c", "pending", "de"), ("14", "d", "blocked", None)):
        user = users.sign_in("github", subject, name)
        users.set_status(user.id, status)
        if country:
            users.set_country(user.id, country)
        ids[name] = user.id
    users.new_session(ids["a"])
    jobs = jb.Jobs(str(tmp_path), public=True)
    both = (("queued", "downloading"), ("ready", "computing"))
    first = _job(jobs, ids["a"], "done", area=10.5, country="pl", phases=both, outline=json.dumps(SQUARE),
                 resolution=1.0)
    _job(jobs, ids["a"], "done", area=4.5, country="pl", phases=both, resolution=5.0)
    _job(jobs, ids[SECRET["name"]], "done", area=2.0, country="sk", title=SECRET["title"], phases=both,
         resolution=0.5)
    jobs.set_steps(first, {"1": 2.5, "3": 1.0, "orthophoto": 4.0}, {"1": 9.5})  # the CPU of step 1 only
    jobs.set_stages(first, {"anchor pairs": (0.75, 6.0), "checking lines": (0.25, 1.5)})
    jobs.set_funnel(first, {"grids": 2, "anchors": 500, "open": 40, "lines": 7})
    _job(jobs, SECRET["user"], "done", area=1.0, phases=both)  # its country unknown
    _job(jobs, ids["a"], "done")  # no area (an OSM extract)
    _job(jobs, ids["a"], "failed", error="time limit: the compute phase was stopped after 7200 s", phases=both)
    _job(jobs, ids["a"], "failed", error="the worker stopped (exit code -9)", phases=both[:1])
    _job(jobs, ids["a"], "failed", error="internal error, ref 20261031-x")
    _job(jobs, ids["a"], "failed", error=jb.INTERRUPTED)
    _job(jobs, ids["a"], "failed", error="something else")
    _job(jobs, ids["a"], "failed", error=messages_error())
    _job(jobs, ids["a"], "cancelled")
    _job(jobs, ids["a"], "queued", phases=both[:1])  # downloading
    _job(jobs, ids["a"], "queued")
    jobs.register("worker-1")
    jobs.quick_add("estimate", {"params": {}}, ids["a"])
    jobs.add_run(SECRET["run"], ids["a"], 1234)
    jobs.add_run("run-2", ids["a"], 766)
    jobs.set_favourite(ids["a"], SECRET["run"], "1,2,3,4", {"len": 1})
    jobs.add_report(ids["a"], "results", "secret text", {"page": "#home"})
    log = audit.Audit(str(tmp_path))
    log.log("sign_in", ids["a"])
    log.log("refused", ids["a"], None, {"reason": "job rate", "status": 429})
    log.log("refused", ids["a"], None, {"reason": "at most 2 of your searches may wait or run at once", "status": 429})
    log.log("refused", ids["a"], None, {"reason": "the queue is full (50 searches): try again later", "status": 503})
    db = sqlite3.connect(tmp_path / "audit.sqlite")
    db.execute("INSERT INTO audit (at, action, user_id) VALUES (?, 'sign_in', ?)", (cache.now_iso(ago=7200), ids["a"]))
    db.commit()
    db.close()
    os.makedirs(tmp_path / "cache" / "poland" / "sheets")
    (tmp_path / "cache" / "poland" / "sheets" / "a.asc").write_bytes(b"x" * 1000)
    (tmp_path / "cache" / "LAYOUT").write_text("1\n")
    jobs.add_service_requests([("nominatim.openstreetmap.org", "ok", 3, 3000, 1.5),
                               ("nominatim.openstreetmap.org", "timeout", 1, 0, 30.0)])
    jobs.add_layer_downloads([("poland/nmt", "terrain", 2, 5, 8_000_000, 8.0, 40_000_000, 20.0, 1.5),
                              ("poland/nmt", "terrain", 1, 0, 4_000_000, 4.0, 20_000_000, 10.0, 0.5),
                              ("europe/copernicus", "gap fill", 0, 3, 0, 0.0, 0, 0.0, 0.0)])
    jb.Scheduler(jobs, limits=Limits()).housekeeping()  # the cache sizes, housekeeping.json, coverage.json
    return tmp_path, ids


def messages_error():
    import search
    return search.SearchError("Not enough steep terrain", "no_steep_terrain")


def scrape(data_dir, limits=None, accounts_dir=None, quick=None, routes=None, event_streams=None) -> str:
    return generate_latest(metrics.registry(str(data_dir), limits, accounts_dir, quick, routes,
                                            event_streams)).decode()


def route_counts():
    import web
    counts = web.RouteCounts()
    counts.add("/api/runs/{run}/favourites", "GET", 200, 0.25)
    counts.add("/api/runs/{run}/favourites", "GET", 404, 0.75)
    counts.add("/api/events", "GET", 200, 300.0)  # counted, but not in the time per route
    counts.add("unmatched", "BREW", 404, 0.01)
    return counts


def samples(text: str) -> dict:
    """{(sample name, frozenset of label items): value} of an exposition."""
    found = {}
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            found[(s.name, frozenset(s.labels.items()))] = s.value
    return found


def value(found: dict, name: str, **labels):
    return found[(name, frozenset(labels.items()))]


def test_names_labels_and_values(data):
    """Every metric of the contract with exactly its labels, and nothing else; the values counted from
    the rows of the databases."""
    data_dir, ids = data
    limits = Limits.load(public=True).model_copy(update={"compute_slots": 3, "download_slots": 2})
    text = scrape(data_dir, limits, str(data_dir), {"ok": 5, "no_worker": 1, "busy": 0, "gone": 2}, route_counts(),
                  lambda: 2)
    found = samples(text)
    names = {}
    for name, labels in found:
        names.setdefault(name, set()).update(k for k, _ in labels)
    assert names == CONTRACT, set(names) ^ set(CONTRACT)
    assert text.isascii()
    assert value(found, "findaline_build_info", version=cache.VERSION) == 1
    assert value(found, "findaline_workers_alive") == 1 and 0 <= value(found, "findaline_worker_lease_age_seconds") < 5
    assert {s: value(found, "findaline_jobs", status=s) for s in jb.WAITING + jb.ACTIVE} == {
        "queued": 1, "ready": 0, "downloading": 1, "computing": 0}
    assert value(found, "findaline_queue_max") == 50
    assert value(found, "findaline_slots", phase="compute") == 3 and value(found, "findaline_slots", phase="download") == 2
    assert 0 <= value(found, "findaline_job_oldest_waiting_seconds") < 60
    finished = {(dict(k)["status"], dict(k)["error"]): v for (n, k), v in found.items()
                if n == "findaline_jobs_finished_total"}
    assert finished == {("done", ""): 5, ("cancelled", ""): 1, ("failed", "time_limit"): 1,
                        ("failed", "worker_stopped"): 1, ("failed", "internal"): 1, ("failed", "interrupted"): 1,
                        ("failed", "other"): 1, ("failed", "no_steep_terrain"): 1}
    assert value(found, "findaline_job_duration_seconds_count", status="failed") == 6
    assert value(found, "findaline_job_duration_seconds_count", status="cancelled") == 1
    assert value(found, "findaline_job_duration_seconds_sum", status="done") >= 0
    # waiting: every claimed job; downloading: those that went on or ended; computing: those that ended
    assert value(found, "findaline_job_phase_seconds_count", phase="waiting") == 7
    assert value(found, "findaline_job_phase_seconds_count", phase="download") == 6
    assert value(found, "findaline_job_phase_seconds_count", phase="ready") == 5  # downloaded, then computed
    assert value(found, "findaline_job_phase_seconds_count", phase="compute") == 5
    assert value(found, "findaline_quick_waiting") == 1 and value(found, "findaline_quick_oldest_waiting_seconds") >= 0
    assert value(found, "findaline_quick_answers_total", result="ok") == 5
    assert value(found, "findaline_quick_answers_total", result="gone") == 2
    assert {s: value(found, "findaline_users", status=s) for s in ac.STATUSES} == {
        "pending": 1, "approved": 2, "blocked": 1}
    assert {dict(k)["country"]: v for (n, k), v in found.items() if n == "findaline_users_by_country"} == {
        "pl": 1, "de": 1, "unknown": 2}
    assert {dict(k)["country"]: v for (n, k), v in found.items() if n == "findaline_users_searched_in"} == {
        "pl": 1, "sk": 1}
    assert value(found, "findaline_sessions_active", window="15m") == 1
    assert value(found, "findaline_sessions_active", window="24h") == 1
    assert value(found, "findaline_audit_events_last_hour", action="sign_in") == 1  # not the one of 2 h ago
    assert value(found, "findaline_audit_events_last_hour", action="refused") == 3
    assert value(found, "findaline_audit_events_last_hour", action="country") == 0  # every action, 0 too
    assert {k: value(found, "findaline_refusals_last_hour", kind=k) for k in ("rate", "quota", "other")} == {
        "rate": 1, "quota": 1, "other": 1}
    assert value(found, "findaline_reports_open") == 1
    assert value(found, "findaline_runs") == 2 and value(found, "findaline_runs_bytes") == 2000
    assert value(found, "findaline_favourites") == 1
    assert value(found, "findaline_cache_bytes", folder="poland") == 1000
    assert value(found, "findaline_free_disk_bytes") > 0
    assert {dict(k)["country"]: v for (n, k), v in found.items() if n == "findaline_area_km2_total"} == {
        "pl": 15.0, "sk": 2.0, "unknown": 1.0}
    assert {dict(k)["country"]: v for (n, k), v in found.items() if n == "findaline_searches_total"} == {
        "pl": 2, "sk": 1, "unknown": 1}
    host = "nominatim.openstreetmap.org"
    assert value(found, "findaline_service_requests_total", host=host, outcome="ok") == 3
    assert value(found, "findaline_service_requests_total", host=host, outcome="timeout") == 1
    assert value(found, "findaline_service_bytes_total", host=host) == 3000
    assert value(found, "findaline_service_seconds_total", host=host) == 31.5
    route = "/api/runs/{run}/favourites"
    assert value(found, "findaline_http_requests_total", route=route, method="GET", status="2xx") == 1
    assert value(found, "findaline_http_requests_total", route=route, method="GET", status="4xx") == 1
    assert value(found, "findaline_http_requests_total", route="unmatched", method="other", status="4xx") == 1
    assert value(found, "findaline_http_request_seconds_count", route=route) == 2
    assert value(found, "findaline_http_request_seconds_sum", route=route) == 1.0
    assert ("findaline_http_request_seconds_count", frozenset({("route", "/api/events")})) not in found
    assert value(found, "findaline_event_streams") == 2
    assert {dict(k)["what"]: v for (n, k), v in found.items() if n == "findaline_housekeeping_removed"} == {
        "parts": 0, "events": 0, "quick": 0, "usage": 0, "audit": 0, "work": 0}
    assert abs(value(found, "findaline_housekeeping_last_run_timestamp_seconds") - time.time()) < 60
    assert 0 <= value(found, "findaline_housekeeping_seconds") < 60
    assert value(found, "findaline_coverage_km2") == pytest.approx(0.715 * 1.0, rel=0.01)
    assert {(dict(k)["lat"], dict(k)["lon"]): v for (n, k), v in found.items()
            if n == "findaline_searches_by_cell"} == {("50.00", "19.75"): 1}
    # Mpx = km2 / resolution^2 by the class of the resolution (the search of 1 km2 has none)
    assert {dict(k)["resolution"]: v for (n, k), v in found.items() if n == "findaline_computed_mpx_total"} == {
        "1": pytest.approx(10.5 + 2.0 / 0.25), "2": 0, "5": pytest.approx(4.5 / 25), "10": 0, "30": 0}
    assert value(found, "findaline_computed_seconds_total", resolution="1") >= 0
    assert value(found, "findaline_compute_step_seconds_count", step="orthophoto") == 1
    assert value(found, "findaline_compute_step_seconds_sum", step="1") == 2.5
    assert value(found, "findaline_compute_step_seconds_count", step="5") == 0  # every step, 0 too
    assert value(found, "findaline_compute_step_cpu_seconds_count", step="1") == 1
    assert value(found, "findaline_compute_step_cpu_seconds_sum", step="1") == 9.5
    assert value(found, "findaline_compute_step_cpu_seconds_count", step="3") == 0  # its CPU not known
    assert value(found, "findaline_compute_stage_seconds_sum", stage="anchor pairs") == 0.75
    assert value(found, "findaline_compute_stage_cpu_seconds_sum", stage="anchor pairs") == 6.0
    assert value(found, "findaline_compute_stage_cpu_seconds_count", stage="checking lines") == 1
    assert value(found, "findaline_compute_stage_seconds_count", stage="free directions") == 0
    assert {dict(k)["level"]: v for (n, k), v in found.items() if n == "findaline_line_funnel_total"} == {
        **dict.fromkeys(jb.FUNNEL_STEPS, 0), "grids": 2, "anchors": 500, "open": 40, "lines": 7}
    assert {dict(k)["stage"] for (n, k), _ in found.items() if n == "findaline_compute_stage_seconds_sum"} == set(
        jb.STAGE_KEYS)
    layer = {"layer": "poland/nmt", "role": "terrain"}
    assert value(found, "findaline_download_tiles_total", **layer) == 3
    assert value(found, "findaline_download_tiles_cached_total", **layer) == 5
    assert value(found, "findaline_download_pixels_total", **layer) == 12_000_000
    assert value(found, "findaline_download_km2_total", **layer) == 12.0
    assert value(found, "findaline_download_bytes_total", **layer) == 60_000_000
    assert value(found, "findaline_download_seconds_total", **layer) == 30.0
    assert value(found, "findaline_download_wait_seconds_total", **layer) == 2.0
    assert value(found, "findaline_download_tiles_cached_total", layer="europe/copernicus", role="gap fill") == 3


def test_no_personal_data_in_labels(data):
    """No label value is a user id, a name, a title, a run or a path: each label takes values of its
    own small set (statuses, phases, codes, actions, alpha-2 countries, cache folders, the catalogue's
    layers, roles, steps, classes of resolution)."""
    data_dir, ids = data
    text = scrape(data_dir, Limits.load(public=True), str(data_dir), dict.fromkeys(metrics.QUICK_RESULTS, 0),
                  route_counts(), lambda: 0)
    for secret in (SECRET["title"], SECRET["name"], SECRET["run"], "secret text", str(data_dir), "worker-1"):
        assert secret not in text, secret
    allowed = {
        "version": re.compile(r"[\w.+-]+"), "status": re.compile(r"queued|ready|downloading|computing|done|failed|"
                                                                   r"cancelled|pending|approved|blocked|[1-5]xx"),
        "phase": re.compile(r"waiting|download|ready|compute"), "error": re.compile(r"[a-z0-9_]*"),
        "result": re.compile("|".join(metrics.QUICK_RESULTS)), "country": re.compile(r"[a-z]{2}|unknown"),
        "window": re.compile(r"15m|24h"), "action": re.compile("|".join(audit.ACTIONS)),
        "kind": re.compile(r"rate|quota|other"), "folder": re.compile(r"[\w.-]+"),
        "host": re.compile(r"[a-z0-9.-]+"), "outcome": re.compile("|".join(servicecounts.OUTCOMES)),
        "route": re.compile(r"/[\w/{}.-]*|unmatched"), "method": re.compile(r"[A-Z]+|other"),
        "what": re.compile(r"parts|events|quick|usage|audit|work"), "lat": re.compile(r"-?\d+\.\d\d"),
        "lon": re.compile(r"-?\d+\.\d\d"), "layer": re.compile(r"[a-z0-9_.-]+(/[a-z0-9_.-]+)*"),
        "role": re.compile("|".join(servicecounts.ROLES)), "step": re.compile("|".join(jb.STEP_KEYS)),
        "resolution": re.compile("|".join(metrics.RESOLUTIONS)),
        "stage": re.compile("|".join(jb.STAGE_KEYS)), "level": re.compile("|".join(jb.FUNNEL_STEPS)),
    }
    for (name, labels), _ in samples(text).items():
        for label, label_value in labels:
            assert allowed[label].fullmatch(label_value), (name, label, label_value)
            if label not in ("step", "resolution"):  # fixed sets of small numbers, which ids may equal
                assert label_value not in {str(i) for i in [*ids.values(), SECRET["user"]]}, (name, label, label_value)


def test_parts_that_are_missing(tmp_path):
    """Without accounts and an audit log (the local app) the metrics of users, sessions and audit events
    are absent; without the cache sizes and without workers theirs too; an empty data folder still
    gives the version and the free disk."""
    found = {name for name, _ in samples(scrape(tmp_path))}
    assert found == {"findaline_build_info", "findaline_free_disk_bytes"}
    jb.Jobs(str(tmp_path))
    found = {name for name, _ in samples(scrape(tmp_path, Limits()))}
    assert "findaline_jobs" in found and "findaline_slots" in found and "findaline_workers_alive" in found
    for absent in ("findaline_users", "findaline_sessions_active", "findaline_audit_events_last_hour",
                   "findaline_cache_bytes", "findaline_queue_max", "findaline_worker_lease_age_seconds",
                   "findaline_quick_answers_total"):
        assert absent not in found, absent
    db = sqlite3.connect(tmp_path / "jobs.sqlite")  # a database that cannot be read: left out, no error
    db.execute("DROP TABLE favourites")
    db.commit()
    db.close()
    assert {name for name, _ in samples(scrape(tmp_path))} == {"findaline_build_info", "findaline_free_disk_bytes"}


def test_housekeeping_measures_the_cache(tmp_path):
    """The worker's housekeeping writes work/cache-sizes.json: the bytes of each top-level cache folder."""
    os.makedirs(tmp_path / "cache" / "osm" / "theme")
    os.makedirs(tmp_path / "cache" / "europe")
    (tmp_path / "cache" / "osm" / "theme" / "t.json").write_bytes(b"x" * 300)
    (tmp_path / "cache" / "osm" / "index.sqlite").write_bytes(b"x" * 20)
    (tmp_path / "cache" / "LAYOUT").write_text("1\n")
    jb.Scheduler(jb.Jobs(str(tmp_path)), limits=Limits()).housekeeping()
    with open(tmp_path / "work" / jb.CACHE_SIZES, encoding="utf-8") as f:
        sizes = json.load(f)
    assert sizes["folders"] == {"osm": 320, "europe": 0} and abs(sizes["time"] - time.time()) < 60
    assert not [n for n in os.listdir(tmp_path / "work") if n.endswith(".part")]


def test_metrics_server(tmp_path):
    """metrics.serve: prometheus_client's server in a thread, the text format at /metrics."""
    import socket
    jb.Jobs(str(tmp_path))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server, thread = metrics.serve(port, "127.0.0.1", str(tmp_path), Limits(), quick_answers={"ok": 0})
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=10) as answer:
            text = answer.read().decode()
        assert answer.status == 200 and "findaline_build_info{" in text and "findaline_jobs{" in text
    finally:
        server.shutdown()
        server.server_close()


def test_port_of_web_public(tmp_path, monkeypatch):
    """`web --public` serves the metrics on 8766 on every address of its container (--metrics-port 0:
    none) with the web app's own counts of the quick lane; the local app only when asked, on the
    loopback. The public app itself has no metrics route (nginx proxies to it)."""
    import uvicorn

    import web
    from fastapi.testclient import TestClient
    for key, val in {"FINDALINE_PUBLIC_URL": "https://lines.example.org", "FINDALINE_TRUSTED_PROXY": "172.30.0.2",
                     "FINDALINE_CONTACT": "admin@example.org", "FINDALINE_SESSION_SECRET": "s" * 40,
                     "FINDALINE_GITHUB_CLIENT_ID": "id", "FINDALINE_GITHUB_CLIENT_SECRET": "secret",
                     "FINDALINE_ADMINS": "github:1", "FINDALINE_ACCOUNTS_DIR": str(tmp_path / "accounts")}.items():
        monkeypatch.setenv(key, val)
    served, apps = [], []
    monkeypatch.setattr(metrics, "serve", lambda port, addr, data_dir, limits, **kw: served.append((port, addr, kw)))
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: apps.append(app))
    data_dir = str(tmp_path / "data")
    for args, expected in ((["--public"], (8766, "0.0.0.0")), (["--public", "--metrics-port", "0"], None),
                           ([], None), (["--metrics-port", "9100"], (9100, "127.0.0.1"))):
        served.clear()
        assert web.main(["--data-dir", data_dir, "--no-browser", "--no-worker", *args]) == 0
        assert [s[:2] for s in served] == ([expected] if expected else []), args
        if served:
            assert served[0][2]["quick_answers"] is apps[-1].state.quick_answers
            assert served[0][2]["accounts_dir"] == (str(tmp_path / "accounts") if "--public" in args else None)
    public_app = apps[0]
    assert not [r for r in public_app.routes if "metrics" in getattr(r, "path", "")]
    with TestClient(public_app, base_url="https://lines.example.org") as client:
        assert client.get("/metrics").status_code == 404


def test_housekeeping_writes_what_it_removed(tmp_path):
    """work/housekeeping.json: what the round removed (stale .part files, work folders of ended jobs,
    old quick answers, usage rows), when it ended and how long it took; replaced at once."""
    jobs = jb.Jobs(str(tmp_path))
    os.makedirs(tmp_path / "cache" / "europe")
    old = time.time() - 30 * 86400
    for name in ("a.tif.1-2.part", "b.tif.3-4.part"):
        (tmp_path / "cache" / "europe" / name).write_bytes(b"x")
        os.utime(tmp_path / "cache" / "europe" / name, (old, old))
    os.makedirs(tmp_path / "work" / "jobs" / "ended")
    os.utime(tmp_path / "work" / "jobs" / "ended", (old, old))
    os.makedirs(tmp_path / "work" / "estimates" / "left")
    os.utime(tmp_path / "work" / "estimates" / "left", (old, old))
    task = jobs.quick_add("estimate", {"params": {}})
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    db.execute("UPDATE quick SET status = 'done', created = ? WHERE id = ?", (old, task))
    db.execute("INSERT INTO usage (user_id, kind, at, amount) VALUES (1, 'km2', ?, 3)", (old,))
    db.commit()
    db.close()
    jb.Scheduler(jobs, limits=Limits()).housekeeping()
    with open(tmp_path / "work" / jb.HOUSEKEEPING_FILE, encoding="utf-8") as f:
        found = json.load(f)
    assert found["removed"] == {"parts": 2, "events": 0, "quick": 1, "usage": 1, "audit": 0, "work": 2}
    assert abs(found["time"] - time.time()) < 60 and 0 <= found["seconds"] < 60
    assert not [n for n in os.listdir(tmp_path / "work") if n.endswith(".part")]
    with open(tmp_path / "work" / jb.COVERAGE_FILE, encoding="utf-8") as f:
        assert json.load(f)["cells"] == []  # no finished searches yet


def _done(jobs, outline, status="done"):
    job = jobs.add({"params": {}}, "a search")
    jobs.set_area(job, 1.0, None, json.dumps(outline) if isinstance(outline, dict) else outline)
    jobs.set(job, status)
    return job


def _square(west, south, size, height=None):
    north = south + (size if height is None else height)
    return {"type": "Polygon", "coordinates": [[[west, south], [west + size, south], [west + size, north],
                                                [west, north], [west, south]]]}


def test_coverage_of_known_shapes(tmp_path):
    """jb.coverage: the union of the outlines of finished searches on the ellipsoid (a search repeated
    or overlapping counts its area once), the searches per cell of 0.25 degrees by its south-west
    corner (a shape across a cell border in both cells, every search counted), only status done,
    unreadable outlines left out."""
    import area as ar
    from pyproj import Geod
    from shapely.geometry import shape
    jobs = jb.Jobs(str(tmp_path))
    first = _square(19.80, 50.10, 0.01)
    _done(jobs, first)
    _done(jobs, first)  # repeated: area once, counted twice in its cell
    _done(jobs, _square(19.805, 50.10, 0.01))  # overlapping half of it
    _done(jobs, _square(19.995, 50.245, 0.01))  # across the corner of four cells
    _done(jobs, _square(-0.005, -0.005, 0.01))  # across the equator and the prime meridian
    _done(jobs, _square(10.0, 10.0, 1.0), status="failed")  # not finished: left out
    _done(jobs, "not geojson")
    circle = ar.Circle(-33.9, 151.2, 2000)
    _done(jobs, ar.outline_geojson(circle))
    found = jb.coverage(jobs)
    geod = Geod(ellps="WGS84")

    def km2(outline):
        return abs(geod.geometry_area_perimeter(shape(outline))[0]) / 1e6
    expected = km2(_square(19.80, 50.10, 0.015, 0.01)) + km2(_square(19.995, 50.245, 0.01)) \
        + km2(_square(-0.005, -0.005, 0.01)) + km2(json.loads(ar.outline_geojson(circle)))
    assert found["km2"] == pytest.approx(expected, rel=1e-6)
    assert km2(json.loads(ar.outline_geojson(circle))) == pytest.approx(3.14159 * 4, rel=0.03)  # simplified to 50 m
    assert {(lat, lon): n for lat, lon, n in found["cells"]} == {
        (50.0, 19.75): 4, (50.0, 20.0): 1, (50.25, 19.75): 1, (50.25, 20.0): 1,
        (-0.25, -0.25): 1, (-0.25, 0.0): 1, (0.0, -0.25): 1, (0.0, 0.0): 1, (-34.0, 151.0): 1}
    os.makedirs(tmp_path / "empty")
    assert jb.coverage(jb.Jobs(str(tmp_path / "empty"))) == {"time": pytest.approx(time.time(), abs=60),
                                                            "km2": 0.0, "cells": []}


def test_outline_of_every_area_kind(tmp_path):
    """area.outline_geojson: WGS84 GeoJSON simplified to about 50 m (a circle of 1 km keeps its area
    within a few per cent, far fewer points), coordinates of 6 decimals; jb.note_area stores it with
    the km² for a circle and a polygon (coast, cliffs and osm: areas are Polygons of the region)."""
    import area as ar
    from shapely.geometry import shape
    circle = ar.Circle(50.15, 19.75, 1000)
    outline = json.loads(ar.outline_geojson(circle))
    assert outline["type"] == "Polygon" and len(outline["coordinates"][0]) < 100
    assert ar.size_km2(shape(outline)) == pytest.approx(3.14159, rel=0.03)
    assert all(len(str(c).split(".")[-1]) <= 6 for ring in outline["coordinates"] for p in ring for c in p)
    polygon = ar.Polygon(shape(_square(19.80, 50.10, 0.01)))
    assert ar.size_km2(shape(json.loads(ar.outline_geojson(polygon)))) == pytest.approx(0.795, rel=0.01)

    class Plan:
        def __init__(self, area):
            self.area = area
    jobs = jb.Jobs(str(tmp_path))
    for area in (circle, polygon):
        job = jobs.add({"params": {}}, "a search")
        jb.note_area(jobs, job, Plan(area), str(tmp_path / "missing-cache"))
        row = jobs.get(job)
        assert row["area_km2"] > 0 and json.loads(row["area_outline"])["type"] == "Polygon"


def test_requests_per_route(tmp_path):
    """The guard counts every request by the template of its route (a mount's /{path}), "unmatched"
    without one, a refusal of the guard by the route it was meant for; the status as a class; the
    event stream left out of the time per route."""
    import web
    from fastapi.testclient import TestClient
    app = web.create_app(str(tmp_path), port=8799, start_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1:8799") as client:
        assert client.get("/api/jobs").status_code == 200
        assert client.get("/api/jobs/nope").status_code == 404
        assert client.get("/no/such/page").status_code == 404
        assert client.post("/api/jobs", json={}).status_code == 403  # no token: refused by the guard
        client.get("/app/viewer.js")
    found, seconds = app.state.route_counts.snapshot()
    assert found[("/api/jobs", "GET", "2xx")] == 1
    assert found[("/api/jobs/{job_id}", "GET", "4xx")] == 1
    assert found[("unmatched", "GET", "4xx")] == 1
    assert found[("/api/jobs", "POST", "4xx")] == 1
    assert [key for key in found if key[0] == "/app/{path}"]
    assert seconds["/api/jobs"][0] == 2 and "/api/events" not in seconds
    assert app.state.hub.listeners == {}  # findaline_event_streams: len() of these


def test_step_clock_and_ready_time(tmp_path, monkeypatch):
    """The computing phase's seconds per step (jobs.StepClock, F19) from the states of the progress bars,
    the orthophoto apart from step 5; a job's ready_at stamped when its download ends, not in the event."""
    now = iter([0.0, 1.0, 4.0, 5.0, 7.0, 8.0])
    monkeypatch.setattr(jb.time, "monotonic", lambda: next(now))
    clock = jb.StepClock()
    clock({"bar": "Compute", "stage": "x", "done": False, "step": "Step 1/5: downloading elevation data (A)"})
    clock({"bar": "Compute", "stage": "x", "done": False, "step": "Tile 1/2 · Step 3/5: evaluating anchor pairs"})
    clock({"bar": "Download", "stage": "orthophoto tiles", "done": False, "step": "Step 5/5: saving"})
    clock({"bar": "Download", "stage": "orthophoto tiles", "done": True, "step": "Step 5/5: saving"})
    seconds = clock.result()
    assert seconds == {"other": 1.0, "1": 3.0, "3": 1.0, "orthophoto": 2.0, "5": 1.0}
    assert set(seconds) <= set(jb.STEP_KEYS)
    monkeypatch.undo()
    jobs = jb.Jobs(str(tmp_path))
    job = jobs.add({"params": {}}, "a search", None)
    jobs.claim("queued", "downloading", "w")
    assert jobs.get(job)["ready_at"] is None
    jobs.set(job, "ready", when=("downloading",))
    assert jobs.get(job)["ready_at"] is not None
    assert jobs.job_events(job)["events"][-1]["data"] == {"status": "ready"}


def test_step_clock_cpu_and_stages(monkeypatch):
    """jobs.StepClock (F19, migration 16): the CPU seconds per step and the seconds and CPU seconds of
    the stages of the line search while their Compute bar runs, summed over the tiles; the time between
    the bars stays with the step only."""
    now = iter([0.0, 1.0, 3.0, 4.0, 8.0, 9.0, 10.0, 12.0, 20.0, 20.0, 20.0, 20.0])
    cpu = iter([0.0, 1.0, 9.0, 10.0, 40.0, 41.0, 45.0, 53.0, 60.0, 60.0, 60.0, 60.0])
    monkeypatch.setattr(jb.time, "monotonic", lambda: next(now))
    monkeypatch.setattr(jb.time, "process_time", lambda: next(cpu))
    clock = jb.StepClock()  # 0
    step3 = "Tile 1/2 · Step 3/5: evaluating anchor pairs"
    clock({"bar": "Compute", "stage": "anchor pairs", "done": False, "step": step3})  # 1: before it "other"
    clock({"bar": "Compute", "stage": "anchor pairs", "done": True, "step": step3})  # 3: 2 s, 8 CPU of the pairs
    clock({"bar": "Compute", "stage": "checking lines", "done": False, "step": step3})  # 4: between the bars
    clock({"bar": "Compute", "stage": "checking lines", "done": True, "step": step3})  # 8: 4 s, 30 CPU
    step3 = "Tile 2/2 · Step 3/5: evaluating anchor pairs"
    clock({"bar": "Compute", "stage": "anchor pairs", "done": False, "step": step3})  # 9
    clock({"bar": "Compute", "stage": "anchor pairs", "done": True, "step": step3})  # 10: 1 s, 4 CPU more
    clock({"bar": "Compute", "stage": "line profiles", "done": False, "step": "Step 4/5: profiles"})  # 12
    seconds, cpus = clock.result(), clock.cpu()  # 20: step 4 until now
    assert seconds == {"other": 1.0, "3": 11.0, "4": 8.0}
    assert cpus == {"other": 1.0, "3": 52.0, "4": 7.0}
    assert clock.stages() == {"anchor pairs": (3.0, 12.0), "checking lines": (4.0, 30.0)}
    assert set(clock.stages()) <= set(jb.STAGE_KEYS)


def test_stage_keys_are_compute_bars():
    """Every stage of STAGE_KEYS is the name of a Compute bar of the code (F19's stages)."""
    code = ""
    for name in ("helpers.py", "search.py", "sag.py", "linesearch.py"):
        with open(os.path.join(REPO, name), encoding="utf-8") as f:
            code += f.read()
    for stage in jb.STAGE_KEYS:
        assert f'progress.compute.start("{stage}"' in code, stage
    assert len(set(jb.STAGE_KEYS)) == len(jb.STAGE_KEYS) and len(set(jb.FUNNEL_STEPS)) == len(jb.FUNNEL_STEPS)


def test_migration_16_and_its_rows(tmp_path):
    """A jobs.sqlite of version 15 gets job_steps.cpu_seconds, job_stages and job_funnel (its jobs none
    of these); before the migration the metrics of these are absent and the others still there; the
    rows of set_steps, set_stages and set_funnel read back."""
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    cache.migrate(db, jb.MIGRATIONS[:15])
    db.execute("INSERT INTO jobs (id, created, status, request, title) VALUES ('old', '2026-10-01T10:00:00', "
               "'done', '{}', 'Old job')")
    db.execute("INSERT INTO job_steps (job_id, step, seconds) VALUES ('old', '3', 12.0)")
    db.commit()
    db.close()
    found = {name for name, _ in samples(scrape(tmp_path))}
    assert "findaline_compute_step_seconds_sum" in found and "findaline_jobs" in found
    assert not {n for n in found if n.startswith(("findaline_compute_step_cpu", "findaline_compute_stage",
                                                   "findaline_line_funnel"))}
    jobs = jb.Jobs(str(tmp_path))
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    assert db.execute("PRAGMA user_version").fetchone()[0] == len(jb.MIGRATIONS) >= 16
    assert db.execute("SELECT step, seconds, cpu_seconds FROM job_steps").fetchall() == [("3", 12.0, None)]
    assert db.execute("SELECT COUNT(*) FROM job_stages").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM job_funnel").fetchone()[0] == 0
    db.close()
    job = jobs.add({"params": {}}, "a search", None)
    jobs.set_steps(job, {"2": 1.5, "3": 4.0}, {"2": 1.0, "3": 30.0})
    jobs.set_stages(job, {"anchor pairs": (3.0, 25.0)})
    jobs.set_funnel(job, {"anchors": 10, "lines": 3})
    jobs.set_funnel(job, {"anchors": 11})  # replaced
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    assert db.execute("SELECT step, seconds, cpu_seconds FROM job_steps WHERE job_id = ? ORDER BY step",
                      (job,)).fetchall() == [("2", 1.5, 1.0), ("3", 4.0, 30.0)]
    assert db.execute("SELECT stage, seconds, cpu_seconds FROM job_stages").fetchall() == [("anchor pairs", 3.0, 25.0)]
    assert dict(db.execute("SELECT step, count FROM job_funnel").fetchall()) == {"anchors": 11, "lines": 3}
    db.close()
    found = samples(scrape(tmp_path))
    assert value(found, "findaline_compute_step_cpu_seconds_count", step="3") == 1  # the old job's CPU unknown
    assert value(found, "findaline_compute_step_seconds_count", step="3") == 2
    assert value(found, "findaline_line_funnel_total", level="anchors") == 11


def test_statistics_never_fail_a_search(tmp_path, capsys):
    """A write of the statistics that fails (here a database without migration 16's tables) prints a
    line to stderr, nothing to stdout (the job's events), and raises nothing."""
    jobs = jb.Jobs(str(tmp_path))
    db = sqlite3.connect(tmp_path / "jobs.sqlite")
    db.execute("DROP TABLE job_stages")
    db.commit()
    db.close()
    jb._write_statistics(jobs, "a-job", jb.StepClock(), {"anchors": 1})
    out, err = capsys.readouterr()
    assert out == "" and "statistics of job a-job not written" in err
