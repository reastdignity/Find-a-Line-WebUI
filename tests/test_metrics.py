"""The application's metrics (metrics.py; docs/monitoring.md, rows F1-F10 and F14-F16): the names
and labels of the contract with deploy/monitoring (Grafana's dashboard and alert rules, Telegraf),
their values on a scratch data folder, no personal data in any label, the port of `web --public`
and the cache sizes of the worker's housekeeping."""

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
}
SECRET = {"title": "Secret Title of Zakopane", "name": "Secret Name", "run": "run-secret-4242", "user": 4242}
ACCOUNTS = AccountSettings(session_secret="s" * 40, github_client_id="id", github_client_secret="secret",
                           admins="github:1")


def _job(jobs, user_id, status, error=None, area=None, country=None, title="a search", phases=()):
    job = jobs.add({"params": {}}, title, user_id)
    for waiting, working in phases:  # ("queued", "downloading"), ("ready", "computing")
        if waiting == "ready":
            jobs.set(job, "ready")
        assert jobs.claim(waiting, working, "w")["id"] == job
    if area is not None:
        jobs.set_area(job, area, country)
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
    _job(jobs, ids["a"], "done", area=10.5, country="pl", phases=both)
    _job(jobs, ids["a"], "done", area=4.5, country="pl", phases=both)
    _job(jobs, ids[SECRET["name"]], "done", area=2.0, country="sk", title=SECRET["title"], phases=both)
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
    jb.write_cache_sizes(str(tmp_path))
    return tmp_path, ids


def messages_error():
    import search
    return search.SearchError("Not enough steep terrain", "no_steep_terrain")


def scrape(data_dir, limits=None, accounts_dir=None, quick=None) -> str:
    return generate_latest(metrics.registry(str(data_dir), limits, accounts_dir, quick)).decode()


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
    text = scrape(data_dir, limits, str(data_dir), {"ok": 5, "no_worker": 1, "busy": 0, "gone": 2})
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


def test_no_personal_data_in_labels(data):
    """No label value is a user id, a name, a title, a run or a path: each label takes values of its
    own small set (statuses, phases, codes, actions, alpha-2 countries, cache folders)."""
    data_dir, ids = data
    text = scrape(data_dir, Limits.load(public=True), str(data_dir), dict.fromkeys(metrics.QUICK_RESULTS, 0))
    for secret in (SECRET["title"], SECRET["name"], SECRET["run"], "secret text", str(data_dir), "worker-1"):
        assert secret not in text, secret
    allowed = {
        "version": re.compile(r"[\w.+-]+"), "status": re.compile(r"queued|ready|downloading|computing|done|failed|"
                                                                   r"cancelled|pending|approved|blocked"),
        "phase": re.compile(r"waiting|download|compute"), "error": re.compile(r"[a-z0-9_]*"),
        "result": re.compile("|".join(metrics.QUICK_RESULTS)), "country": re.compile(r"[a-z]{2}|unknown"),
        "window": re.compile(r"15m|24h"), "action": re.compile("|".join(audit.ACTIONS)),
        "kind": re.compile(r"rate|quota|other"), "folder": re.compile(r"[\w.-]+"),
    }
    for (name, labels), _ in samples(text).items():
        for label, label_value in labels:
            assert allowed[label].fullmatch(label_value), (name, label, label_value)
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
