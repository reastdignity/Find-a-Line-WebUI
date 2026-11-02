"""
The job queue of the web application and its worker.

- Jobs: the queue and the events of the jobs (jobs.sqlite in the data folder), and the
  leases of the workers.
- Scheduler: the worker. `findaline.py worker` runs it as its own process, `findaline.py
  web` in a thread of its own unless it gets --no-worker. It starts one process per job
  and phase (run_phase): Limits.download_slots downloading and Limits.compute_slots computing
  jobs at a time (1 and 1 unless set; each computing job of several gets its share of the
  memory, search.slot_memory), taking the waiting job of the user with the fewest running
  jobs first (Jobs.claim). It holds a
  lease in the table `workers` and renews it every HEARTBEAT seconds; the running jobs
  of a worker whose lease expired are failed by the next worker that looks (so a
  restart of the web server does not touch the jobs of a separate worker).
- Cancelling sets jobs.cancel_requested; the worker running the job kills its whole
  process tree (psutil) and marks it cancelled. A waiting job is cancelled at once.
- run_phase: a phase in its own process; its stdout becomes "info" events
  (_EventWriter), the progress goes as "progress" events.
- The public site (`worker --public`, Jobs(public=True)): events, errors and answers pass
  Redact, which removes the data folder and other absolute server paths; an unexpected
  exception shows "internal error, ref <id>" and its traceback goes to the log (stderr).
- The quick lane: estimates and profiles of the page (short, but they may call Nominatim
  or Overpass, read sheet indexes and build grids) are rows of the table `quick`, which
  one long-lived process of the worker (run_quick) serves one after another; the web
  server only adds a row and waits for its answer. A task that takes longer than the
  time limit gets its process killed and a new one started.
"""

import contextlib
import json
import math
import multiprocessing
import os
import re
import shutil
import signal
import socket
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

import cache
import messages
import params as pm
import servicecounts
from messages import UserError
from settings import Limits, PublicSettings, redact as redact_keys

TICK = 0.5                # seconds between looks at the queue
PROGRESS_INTERVAL = 0.3   # seconds between progress events of a job
HEARTBEAT = 5.0           # seconds between renewals of a worker's lease
HOUSEKEEPING = 6 * 3600   # seconds between clean-ups of the data folder (and at the start)
QUICK_POLL = 0.05         # seconds between looks of the quick lane at its table
KEEP_WORK_DAYS = 7        # days the work folder of a job that failed unexpectedly is kept (to look at)
KEEP_QUICK_SECONDS = 3600  # an answer of the quick lane nobody took (the page was closed) is deleted after it
# A waiting task of the quick lane is deleted by the web process that waits for it when it gives up
# (web.quick); one left by a web process that stopped is deleted after this (longer than any wait)
KEEP_WAITING_QUICK_SECONDS = 86400
EVENTS_LIMIT = 1000     # events one read of the event streams gets at most (the next read goes on from there)
JOB_EVENTS_MAX = 1000  # messages of a job its page gets at once (the newest; and the last progress)
LEASE = 30.0              # seconds a lease lasts without a renewal
# What a job is doing; "ready" means its data is downloaded and it waits to compute
ACTIVE = ("downloading", "computing")
WAITING = ("queued", "ready")
FINISHED = ("done", "failed", "cancelled")
PHASE_STATUS = {"download": "downloading", "compute": "computing"}  # the status each phase works in
VISIBILITIES = ("private", "demo")  # runs.visibility: the owner's (and administrators'), or everyone's
INTERRUPTED = ("interrupted: the app was closed (a tiled area resumes where it stopped when it is "
               "started again)")
# The schema of jobs.sqlite, one step per version (cache.migrate; never change a released step).
# Version 1 is the schema from before the versions: such a database (user_version 0)
# already has these tables, so the step only marks it, and its jobs stay.
MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS jobs (
           id TEXT PRIMARY KEY, created TEXT, status TEXT, request TEXT, title TEXT,
           run_id TEXT, error TEXT, finished TEXT);
       CREATE TABLE IF NOT EXISTS events (
           seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, kind TEXT, data TEXT);""",
    # 2: the events of one job (the log of the page) and the next job of a status (claim)
    """CREATE INDEX IF NOT EXISTS events_job ON events (job, seq);
       CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, created);""",
    # 3: the worker running a job, cancelling through the database, the leases of the workers
    """ALTER TABLE jobs ADD COLUMN worker_id TEXT;
       ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0;
       CREATE TABLE workers (id TEXT PRIMARY KEY, pid INTEGER, host TEXT, started TEXT, expires REAL);""",
    # 4: the tasks of the quick lane (estimates and profiles); `answer` is {"code": HTTP status, "body": ...}
    """CREATE TABLE quick (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, request TEXT, status TEXT,
                           answer TEXT, worker_id TEXT, created REAL, started REAL);
       CREATE INDEX quick_status ON quick (status, id);""",
    # 5: the owner of a job (accounts.sqlite users.id; NULL: the local app's, or from before the accounts)
    """ALTER TABLE jobs ADD COLUMN user_id INTEGER;
       CREATE INDEX jobs_user ON jobs (user_id, created);""",
    # 6: the owners of the runs (web.py serves a run's files to them only), who sees them (private;
    # later demo), the sha256 of a run's share link and its size on disk
    """CREATE TABLE runs (run_id TEXT PRIMARY KEY, user_id INTEGER, visibility TEXT NOT NULL DEFAULT 'private',
                          share_hash TEXT UNIQUE, bytes INTEGER NOT NULL DEFAULT 0, created TEXT);
       CREATE INDEX runs_user ON runs (user_id, created);""",
    # 7: quotas: whether a job or a quick task is a user's without limits (the worker applies its
    # Limits otherwise), the owner of a quick task, and what users used (km², Nominatim requests)
    """ALTER TABLE jobs ADD COLUMN unlimited INTEGER NOT NULL DEFAULT 0;
       ALTER TABLE quick ADD COLUMN user_id INTEGER;
       ALTER TABLE quick ADD COLUMN unlimited INTEGER NOT NULL DEFAULT 0;
       CREATE TABLE usage (user_id INTEGER NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL, amount REAL NOT NULL);
       CREATE INDEX usage_user ON usage (user_id, kind, at);""",
    # 8: a user's favourite lines (NULL: the local app's user): the run, the line ("lat1,lon1,lat2,lon2"
    # as the run's data.js holds it) and its values as the map sent them (JSON, for the list of all of them)
    """CREATE TABLE favourites (user_id INTEGER, run_id TEXT NOT NULL, line TEXT NOT NULL, data TEXT NOT NULL,
                                created TEXT);
       CREATE UNIQUE INDEX favourites_key ON favourites (IFNULL(user_id, 0), run_id, line);
       CREATE INDEX favourites_run ON favourites (run_id);""",
    # 9: folders of favourite lines (as a browser's bookmarks: nested, each favourite in one folder or at
    # the top level, NULL); the favourites of before stay at the top level
    """CREATE TABLE favourite_folders (id INTEGER PRIMARY KEY, user_id INTEGER, parent_id INTEGER,
                                       name TEXT NOT NULL, created TEXT);
       CREATE INDEX favourite_folders_user ON favourite_folders (IFNULL(user_id, 0));
       ALTER TABLE favourites ADD COLUMN folder_id INTEGER;""",
    # 10: problem reports of the users (the app's "Report a problem"): a category, the text and the page,
    # run, line, window and browser they were sent from (JSON); open or done, kept until an administrator
    # deletes them
    """CREATE TABLE reports (id INTEGER PRIMARY KEY, user_id INTEGER, created TEXT, category TEXT NOT NULL,
                             text TEXT NOT NULL, context TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open');""",
    # 11: the code of a job's error and its parameters (JSON {"code", "params"}: the page shows the text
    # of the message catalogue, "error.<code>"); NULL: no code (and every job of before), `error` is shown
    """ALTER TABLE jobs ADD COLUMN error_info TEXT;""",
    # 12: times in UTC with their offset ("...+00:00"; the page shows them in the viewer's time zone):
    # those of before had none and were the local time of the process (UTC in the container)
    lambda db: cache.utc_columns(db, {"jobs": ("created", "finished"), "runs": ("created",),
                                      "favourites": ("created",), "favourite_folders": ("created",),
                                      "reports": ("created",), "workers": ("started",)},
                                 json_columns={("events", "data"): ("created", "finished")}),
    # 13: the area of a search in km² and the country it lies in (sources.country_code, lower case), set
    # by the worker when it plans the search; when the job's phases started (UTC, as `created`). Jobs of
    # before get the area where their request gives it without any service (request_km2)
    lambda db: _area_columns(db),
    # 14: the requests of the worker's processes to outside services, running totals per host and outcome
    # (servicecounts; never deleted: a few hundred rows at most), and the outline of a search's area
    # (GeoJSON geometry in WGS84, simplified to about 50 m: area.outline_geojson), set with area_km2. Jobs of
    # before get it where their request gives it without any service (request_area)
    lambda db: _outline_column(db),
    # 15: when a job's data was downloaded (so the wait for a compute slot shows apart from the download),
    # the source and resolution of its search (set by the worker when it plans it), the seconds of the steps
    # of its computing phase (job_steps: STEP_KEYS), and the tiles of the elevation layers the worker's
    # processes downloaded or found cached, running totals per layer and role (servicecounts.tiles; a few
    # dozen rows). Jobs of before get none of these (their times cannot be told again)
    """ALTER TABLE jobs ADD COLUMN ready_at TEXT;
       ALTER TABLE jobs ADD COLUMN source TEXT;
       ALTER TABLE jobs ADD COLUMN resolution REAL;
       CREATE TABLE job_steps (job_id TEXT NOT NULL, step TEXT NOT NULL, seconds REAL NOT NULL,
                               PRIMARY KEY (job_id, step));
       CREATE TABLE layer_downloads (layer TEXT NOT NULL, role TEXT NOT NULL, tiles INTEGER NOT NULL,
                                     tiles_cached INTEGER NOT NULL, pixels INTEGER NOT NULL, km2 REAL NOT NULL,
                                     bytes INTEGER NOT NULL, seconds REAL NOT NULL, wait_seconds REAL NOT NULL,
                                     PRIMARY KEY (layer, role));""",
    # 16: where the CPU of a computing phase goes: the CPU seconds of its steps (job_steps.cpu_seconds, the
    # whole process with numba's threads), the seconds and CPU seconds of the stages of the line search
    # (job_stages: STAGE_KEYS, summed over the tiles) and its funnel (job_funnel: FUNNEL_STEPS, the counts of
    # search.Plan.funnel). Counts without users, like job_steps. Jobs of before get none of these
    # (tools/job_stats.py reads what it can of them from their events)
    """ALTER TABLE job_steps ADD COLUMN cpu_seconds REAL;
       CREATE TABLE job_stages (job_id TEXT NOT NULL, stage TEXT NOT NULL, seconds REAL NOT NULL,
                                cpu_seconds REAL NOT NULL, PRIMARY KEY (job_id, stage));
       CREATE TABLE job_funnel (job_id TEXT NOT NULL, step TEXT NOT NULL, count INTEGER NOT NULL,
                                PRIMARY KEY (job_id, step));""",
]
# The column of a status's start (claim), or of the end of the download ("ready", set by its process)
PHASE_TIME = {"downloading": "downloading_at", "ready": "ready_at", "computing": "computing_at"}
# What the time of a computing phase is counted as (job_steps.step): its steps (search.STEPS), the
# orthophoto tiles of step 5 (downloaded while the job holds its compute slot), and "other" (before the
# first step, between the tiles of an area)
STEP_KEYS = ("1", "2", "3", "4", "5", "orthophoto", "other")
# The stages of the line search (job_stages.stage): the names of the Compute bars of steps 2 and 3
# (helpers.find_significant_slopes, search._lines, sag.EnvelopeTable, linesearch.find_valid_lines)
STAGE_KEYS = ("finding anchors", "anchor prominence and drop", "sag estimator table", "free directions",
              "anchor pairs", "checking lines")
# The funnel of the line search (job_funnel.step, search.Plan.funnel): grids searched, anchors found
# and kept after the prominence and drop limits, anchors with an open direction and those pairs start
# from, candidate pairs, pairs checked pixel by pixel and found, valid lines, lines left out by the
# line limits, and the lines in the tiles' cores
FUNNEL_STEPS = ("grids", "anchors", "anchors_kept", "open", "todo", "candidates", "checked", "found", "valid",
                "left_out", "lines")


def request_area(request: Dict):
    """The area (area.Circle or area.Polygon) of a job's request when it gives it without any service
    (migrations 13 and 14 for the jobs of before): a circle or a drawn area (its buffered geometry,
    clipped to a box `within`); None for coast, cliffs, osm: areas, a drawn area within an osm: area,
    OSM extract jobs and requests that do not validate."""
    if not isinstance(request, dict) or not isinstance(request.get("params"), dict):
        return None
    try:
        p = search_params(request)
        import area as ar
        if p.geometry is not None:
            if p.within is not None and p.within.startswith("osm:"):
                return None
            return ar.from_geometry(p.geometry, p.buffer, p.within, "")
        if p.area is None:
            if p.lat is not None:
                lat, lon = p.lat, p.lon
            else:  # PL-1992, as mapping.pl1992_to_wgs84 (without importing the map's code)
                from pyproj import Transformer
                to_wgs84 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
                lon, lat = to_wgs84.transform(p.easting, p.northing)
            return ar.Circle(lat, lon, p.radius)
    except Exception:  # a request of an older version that no longer validates
        return None
    return None


def area_km2(area) -> float:
    """The km² of an area (area.Circle: pi r², as the km² quota counts it; area.Polygon: its geometry)."""
    from area import Polygon, size_km2
    return size_km2(area.geometry) if isinstance(area, Polygon) else math.pi * area.radius ** 2 / 1e6


def request_km2(request: Dict) -> Optional[float]:
    """The km² of a job's request when it gives them without any service (request_area), else None."""
    area = request_area(request)
    return None if area is None else area_km2(area)


def area_outline(area) -> Optional[str]:
    """The outline of an area kept with its job (area.outline_geojson); None when it cannot be made
    (the statistics never fail a search)."""
    try:
        import area as ar
        return ar.outline_geojson(area)
    except Exception:
        return None


def _area_columns(db: sqlite3.Connection):
    """Migration 13: the columns, and the area of the jobs of before (request_km2)."""
    for column in ("area_km2 REAL", "country TEXT", "downloading_at TEXT", "computing_at TEXT"):
        db.execute(f"ALTER TABLE jobs ADD COLUMN {column}")
    found = []
    for rowid, text in db.execute("SELECT rowid, request FROM jobs").fetchall():
        try:
            km2 = request_km2(json.loads(text))
        except (TypeError, ValueError):
            km2 = None
        if km2 is not None:
            found.append((km2, rowid))
    db.executemany("UPDATE jobs SET area_km2 = ? WHERE rowid = ?", found)


def _outline_column(db: sqlite3.Connection):
    """Migration 14: the table of the requests to outside services, the column of the outline and the
    outlines of the jobs of before (request_area)."""
    db.execute("CREATE TABLE service_requests (host TEXT NOT NULL, outcome TEXT NOT NULL, requests INTEGER NOT NULL, "
               "bytes INTEGER NOT NULL, seconds REAL NOT NULL, PRIMARY KEY (host, outcome))")
    db.execute("ALTER TABLE jobs ADD COLUMN area_outline TEXT")
    found = []
    for rowid, text in db.execute("SELECT rowid, request FROM jobs").fetchall():
        try:
            area = request_area(json.loads(text))
        except (TypeError, ValueError):
            area = None
        outline = area_outline(area) if area is not None else None
        if outline is not None:
            found.append((outline, rowid))
    db.executemany("UPDATE jobs SET area_outline = ? WHERE rowid = ?", found)


FAVOURITES_MAX = 10000  # favourite lines of a user (a safeguard of the database, the same for everyone)
FOLDERS_MAX = 1000      # folders of favourites of a user
FOLDER_DEPTH_MAX = 8    # folders inside one another (a top-level folder is at depth 1)
FOLDER_NAME_MAX = 100   # characters of a folder's name
REPORT_CATEGORIES = ("results", "water", "interface", "other")  # of a problem report
REPORT_TEXT_MAX = 4000  # characters of a problem report
REPORT_STATUSES = ("open", "done")


# An absolute path on the server: C:\... (or C:/...), or /dir/... not in a URL (http://host/...: the
# slash after "host" follows a letter, the first of "//" another slash); after a colon too (path:/x)
ABSOLUTE_PATH = re.compile(r"""(?:\b[A-Za-z]:[\\/]|(?<![\w/.~-])/(?=[\w.-]))[^\s"'<>|]*""")
APP_DIR = os.path.dirname(os.path.abspath(__file__))


class Redact:
    """Removes server paths from texts for the public site: the data folder becomes relative
    ("runs/<id>"), the folder of the app and other absolute paths "<path>"."""

    def __init__(self, data_dir: str):
        folders = {os.path.abspath(data_dir), os.path.realpath(data_dir)}
        flags = re.IGNORECASE if os.name == "nt" else 0
        # Only at a path boundary (a separator, a quote, whitespace or the end), so a sibling such as
        # "<data>-old" is not taken for the data folder (it is still an absolute path: ABSOLUTE_PATH).
        # Best effort: a path with spaces after the folder is cut at the first space.
        self.data = [re.compile(re.escape(f) + r"""(?:[\\/]|(?=[\s"']|$))""", flags)
                     for f in self._variants(folders)]
        self.app = [re.compile(re.escape(f) + r"""(?=[\\/\s"']|$)[^\s"'<>|]*""", flags)
                    for f in self._variants({APP_DIR})]

    @staticmethod
    def _variants(folders) -> List[str]:
        found = {v for f in folders for v in (f, f.replace("\\", "/"), f.replace("/", "\\"))}
        return sorted(found, key=len, reverse=True)  # the longest first

    def __call__(self, value: Any) -> Any:
        """The value (a text, or texts in lists and dicts) without server paths, and without the
        values of the service keys (settings.redact: a line a library printed may hold a request
        with a key that no clean_error saw)."""
        if isinstance(value, str):
            value = redact_keys(value)
            for pattern in self.data:
                value = pattern.sub(lambda m: "" if m.group(0)[-1] in "\\/" else "<data folder>", value)
            for pattern in self.app:
                value = pattern.sub("<path>", value)
            return ABSOLUTE_PATH.sub("<path>", value)
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        return value


class QuotaExceeded(UserError):
    """A quota or a safeguard refuses a job or a request (`status`: the HTTP status, 429 for a user's
    quota, 503 for the server's safeguards; `code`, `params`: its web text, messages.UserError). A
    ValueError, so code that goes on without an optional lookup (a run's place name, the country of
    --source auto) goes on without it."""

    def __init__(self, message: str, status: int = 429, code: Optional[str] = None, **params):
        super().__init__(message, code, **params)
        self.status = status


def _with_info(job: Dict) -> Dict:
    """A job (or a status event) for the page: its error_info read from its JSON."""
    if job.get("error_info"):
        job["error_info"] = json.loads(job["error_info"])
    return job


DAY = 86400.0  # seconds of the daily quotas (a moving 24 hours)
AREA_DAYS = 30  # days of a user's searched area by day (/api/usage `area`)
USAGE = {"km2": "km² of search areas", "mpx": "Mpx of search areas (km² / resolution²)", "nominatim": "uncached Nominatim requests (place names, osm: areas)",
         "download_mb": "MB of downloads (the estimates of your searches)"}


def _in(values: Iterable) -> str:
    """Placeholders for an SQL IN (...) of these values."""
    return "(" + ", ".join("?" * len(tuple(values))) + ")"


class Jobs:
    """The queue and the events of the jobs (jobs.sqlite in the data folder)."""

    def __init__(self, data_dir: str, public: bool = False):
        self.data_dir = data_dir
        self.public = public
        # The public site: no server paths in events, errors and answers
        self.redact = Redact(data_dir) if public else (lambda value: value)
        self.path = os.path.join(data_dir, "jobs.sqlite")
        db = self._db()
        try:
            cache.migrate(db, MIGRATIONS)
        finally:
            db.close()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=60)
        db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = sqlite3.Row
        return db

    def folder(self, job_id: str) -> str:
        return os.path.join(self.data_dir, "work", "jobs", job_id)

    def add(self, request: Dict, title: str, user_id: Optional[int] = None,
            check: Optional[Callable[[sqlite3.Connection], None]] = None, unlimited: bool = False) -> str:
        """Queue a job of a user (None: the local app's); `check(db)` runs in the same write
        transaction before the job is added (a quota: it raises to refuse it); `unlimited`: a job
        of a user without limits (the worker's Limits do not apply to it, its time limits do)."""
        job_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        created = cache.now_iso()
        with self._write() as db:
            if check:
                check(db)
            db.execute("INSERT INTO jobs (id, created, status, request, title, user_id, unlimited) "
                       "VALUES (?, ?, 'queued', ?, ?, ?, ?)",
                       (job_id, created, json.dumps(request), title, user_id, int(unlimited)))
            self._insert_event(db, job_id, "status", {"status": "queued", "title": title, "created": created})
        return job_id

    def admission(self, user_id: Optional[int], limits: Optional[Limits], limited: bool) -> Callable:
        """The check of a new job (for add(check=...), so it runs in the insert's transaction and two
        requests at once cannot both pass): the safeguards of the server for everyone (free disk,
        queue length), the quotas of `limits` for a limited user (jobs at once and per day, size of
        their runs, Mpx and km² of the last 24 hours). Raises QuotaExceeded."""
        def check(db: sqlite3.Connection):
            if limits is None:
                return
            if limits.free_disk_gb_min is not None:
                free = shutil.disk_usage(self.data_dir).free / 1e9
                if free < limits.free_disk_gb_min:
                    raise QuotaExceeded("the server is short of disk space: no new searches for now", 503,
                                        "disk_full")
            active = WAITING + ACTIVE
            if limits.queue_max is not None:
                count = db.execute(f"SELECT COUNT(*) FROM jobs WHERE status IN {_in(active)}", active).fetchone()[0]
                if count >= limits.queue_max:
                    raise QuotaExceeded(f"the queue is full ({count} searches): try again later", 503, "queue_full",
                                        n=count)
            if not limited or user_id is None:
                return
            if limits.jobs_active_max is not None:
                count = db.execute(f"SELECT COUNT(*) FROM jobs WHERE user_id = ? AND status IN {_in(active)}",
                                   (user_id, *active)).fetchone()[0]
                if count >= limits.jobs_active_max:
                    raise QuotaExceeded(f"at most {limits.jobs_active_max} of your searches may wait or run at once",
                                        code="quota_active", max=limits.jobs_active_max)
            if limits.jobs_day_max is not None:
                since = cache.now_iso(ago=DAY)
                count = db.execute("SELECT COUNT(*) FROM jobs WHERE user_id = ? AND created >= ?",
                                   (user_id, since)).fetchone()[0]
                if count >= limits.jobs_day_max:
                    raise QuotaExceeded(f"at most {limits.jobs_day_max} searches in 24 hours: try again later",
                                        code="quota_jobs_day", max=limits.jobs_day_max)
            if limits.runs_gb_max is not None:
                size = db.execute("SELECT COALESCE(SUM(bytes), 0) FROM runs WHERE user_id = ?",
                                  (user_id,)).fetchone()[0]
                if size >= limits.runs_gb_max * 1e9:
                    raise QuotaExceeded(f"your runs take {size / 1e9:.1f} GB, at most {limits.runs_gb_max:g} GB: "
                                        f"delete some in Runs", code="quota_runs_gb", gb=round(size / 1e9, 1),
                                        max=limits.runs_gb_max)
            if limits.mpx_day_max is not None:
                used = self._used(db, user_id, "mpx")
                if used >= limits.mpx_day_max:
                    raise QuotaExceeded(f"your searches covered {used:.0f} Mpx (km² at 1 m) in 24 hours, at most "
                                        f"{limits.mpx_day_max:g}: try again later", code="quota_mpx",
                                        used=round(used), max=limits.mpx_day_max)
            if limits.km2_day_max is not None:
                used = self._used(db, user_id, "km2")
                if used >= limits.km2_day_max:
                    raise QuotaExceeded(f"your searches covered {used:.0f} km² in 24 hours, at most "
                                        f"{limits.km2_day_max:g} km²: try again later", code="quota_km2",
                                        used=round(used), max=limits.km2_day_max)
        return check

    def precheck(self, check: Callable[[sqlite3.Connection], None]):
        """Run an admission check (admission(...)) without adding a job: the web refuses a request
        over a quota before it validates it; add() checks again in its transaction."""
        db = self._db()
        try:
            check(db)
        finally:
            db.close()

    @staticmethod
    def _used(db: sqlite3.Connection, user_id: int, kind: str) -> float:
        return db.execute("SELECT COALESCE(SUM(amount), 0) FROM usage WHERE user_id = ? AND kind = ? AND at > ?",
                          (user_id, kind, time.time() - DAY)).fetchone()[0]

    def use(self, user_id: int, kind: str, amount: float, limit: Optional[float]):
        """Count what a user uses (USAGE: "km2", "mpx", "nominatim") against its quota of 24 hours; over it,
        QuotaExceeded and nothing is counted (checked and counted in one write transaction)."""
        with self._write() as db:
            used = self._used(db, user_id, kind)
            if limit is not None and used + amount > limit:
                refused = QuotaExceeded(f"{USAGE[kind]}: {used:.0f} of at most {limit:g} in 24 hours used, "
                                        f"{amount:.1f} more needed: try again later", code=f"quota_use_{kind}",
                                        used=round(used), max=limit, more=round(amount, 1))
            else:
                refused = None
                db.execute("INSERT INTO usage (user_id, kind, at, amount) VALUES (?, ?, ?, ?)",
                           (user_id, kind, time.time(), amount))
        if refused is not None:
            if self.public:  # the audit log of the public site (the worker's refusals)
                import audit
                audit.Audit(self.data_dir).log("refused", user_id, None, {"reason": str(refused), "status": 429})
            raise refused

    def usage(self, user_id: Optional[int], limits: Optional[Limits]) -> Dict:
        """A user's use of the quotas, as admission() and use() count it (the last 24 hours, the jobs
        waiting or running now, the size of the runs), each with its quota of `limits` (None: no
        quotas; the counts of USAGE, kept only against their quota, are None without it). user_id None:
        the local app's jobs and runs (those without an owner)."""
        owner = "user_id IS ?" if user_id is None else "user_id = ?"
        active = WAITING + ACTIVE
        since = cache.now_iso(ago=DAY)
        db = self._db()
        try:
            counted = limits is not None and user_id is not None
            used = {kind: self._used(db, user_id, kind) if counted and getattr(limits, f"{kind}_day_max") is not None
                    else None for kind in USAGE}
            jobs_active = db.execute(f"SELECT COUNT(*) FROM jobs WHERE {owner} AND status IN {_in(active)}",
                                     (user_id, *active)).fetchone()[0]
            jobs_day = db.execute(f"SELECT COUNT(*) FROM jobs WHERE {owner} AND created >= ?",
                                  (user_id, since)).fetchone()[0]
            runs_bytes = db.execute(f"SELECT COALESCE(SUM(bytes), 0) FROM runs WHERE {owner}",
                                    (user_id,)).fetchone()[0]
        finally:
            db.close()
        quota = (lambda name: getattr(limits, name)) if limits is not None else (lambda name: None)
        return {"limited": limits is not None, "hours": DAY / 3600, "usage": {
            "mpx": {"used": used["mpx"], "limit": quota("mpx_day_max")},
            "km2": {"used": used["km2"], "limit": quota("km2_day_max")},
            "download_mb": {"used": used["download_mb"], "limit": quota("download_mb_day_max")},
            "nominatim": {"used": used["nominatim"], "limit": quota("nominatim_day_max")},
            "jobs_day": {"used": jobs_day, "limit": quota("jobs_day_max")},
            "jobs_active": {"used": jobs_active, "limit": quota("jobs_active_max")},
            "runs_gb": {"used": runs_bytes / 1e9, "limit": quota("runs_gb_max")},
        }}

    def forget_usage(self) -> int:
        """Delete what users used before the last two days (the quotas look at 24 hours)."""
        with self._db() as db:
            return db.execute("DELETE FROM usage WHERE at < ?", (time.time() - 2 * DAY,)).rowcount

    def set_area(self, job_id: str, km2: Optional[float], country: Optional[str], outline: Optional[str] = None):
        """The area of a job's search in km², the country it lies in and its outline (GeoJSON text,
        area.outline_geojson), set by the worker when it plans it."""
        with self._db() as db:
            db.execute("UPDATE jobs SET area_km2 = ?, country = ?, area_outline = ? WHERE id = ?",
                       (km2, country, outline, job_id))

    def set_search(self, job_id: str, source: Optional[str], resolution: Optional[float]):
        """The source (sources.Source.id) and resolution of a job's search, set by the worker when it
        plans it (the compute side of the statistics: Mpx = km² / resolution²)."""
        with self._db() as db:
            db.execute("UPDATE jobs SET source = ?, resolution = ? WHERE id = ?", (source, resolution, job_id))

    def set_steps(self, job_id: str, seconds: Dict[str, float], cpu: Optional[Dict[str, float]] = None):
        """The seconds of the steps of a job's computing phase (STEP_KEYS -> seconds), and their CPU
        seconds (None: unknown)."""
        cpu = cpu or {}
        with self._db() as db:
            db.executemany("INSERT OR REPLACE INTO job_steps (job_id, step, seconds, cpu_seconds) VALUES (?, ?, ?, ?)",
                           [(job_id, step, s, cpu.get(step)) for step, s in seconds.items()])

    def set_stages(self, job_id: str, stages: Dict[str, Tuple[float, float]]):
        """The seconds and CPU seconds of the stages of a job's line search (STAGE_KEYS)."""
        with self._db() as db:
            db.executemany("INSERT OR REPLACE INTO job_stages (job_id, stage, seconds, cpu_seconds) "
                           "VALUES (?, ?, ?, ?)", [(job_id, stage, s, c) for stage, (s, c) in stages.items()])

    def set_funnel(self, job_id: str, counts: Dict[str, int]):
        """The counts of a job's line search (FUNNEL_STEPS, search.Plan.funnel)."""
        with self._db() as db:
            db.executemany("INSERT OR REPLACE INTO job_funnel (job_id, step, count) VALUES (?, ?, ?)",
                           [(job_id, step, int(n)) for step, n in counts.items()])

    def add_layer_downloads(self, rows: Iterable[Tuple[str, str, int, int, int, float, int, float, float]]):
        """Add counts of the tiles of the elevation layers (layer, role, tiles, tiles cached, pixels, km²,
        bytes, seconds, wait seconds) to their running totals, in one write transaction
        (servicecounts.flush of the worker's processes)."""
        with self._write() as db:
            db.executemany("INSERT INTO layer_downloads (layer, role, tiles, tiles_cached, pixels, km2, bytes, "
                           "seconds, wait_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (layer, role) "
                           "DO UPDATE SET tiles = tiles + excluded.tiles, tiles_cached = tiles_cached + "
                           "excluded.tiles_cached, pixels = pixels + excluded.pixels, km2 = km2 + excluded.km2, "
                           "bytes = bytes + excluded.bytes, seconds = seconds + excluded.seconds, "
                           "wait_seconds = wait_seconds + excluded.wait_seconds", list(rows))

    def add_service_requests(self, rows: Iterable[Tuple[str, str, int, int, float]]):
        """Add counts of requests to outside services (host, outcome, requests, bytes, seconds) to their
        running totals, in one write transaction (servicecounts.flush of the worker's processes)."""
        with self._write() as db:
            db.executemany("INSERT INTO service_requests (host, outcome, requests, bytes, seconds) "
                           "VALUES (?, ?, ?, ?, ?) ON CONFLICT (host, outcome) DO UPDATE SET "
                           "requests = requests + excluded.requests, bytes = bytes + excluded.bytes, "
                           "seconds = seconds + excluded.seconds", list(rows))

    def area(self, user_id: Optional[int], days: float = AREA_DAYS) -> Dict:
        """The area a user's finished searches (status done, with an area) covered: in total, their
        number, and [finished, km²] of those finished in the last `days`, oldest first. user_id None:
        the local app's jobs (those without an owner)."""
        db = self._db()
        try:
            total, count = db.execute("SELECT COALESCE(SUM(area_km2), 0), COUNT(*) FROM jobs WHERE user_id IS ? "
                                      "AND status = 'done' AND area_km2 IS NOT NULL", (user_id,)).fetchone()
            recent = db.execute("SELECT finished, area_km2 FROM jobs WHERE user_id IS ? AND status = 'done' AND "
                                "area_km2 IS NOT NULL AND finished >= ? ORDER BY finished",
                                (user_id, cache.now_iso(ago=days * DAY))).fetchall()
        finally:
            db.close()
        return {"total_km2": total, "searches": count, "recent": [[r[0], r[1]] for r in recent]}

    def area_of_everyone(self) -> Tuple[float, int]:
        """(km², searches) of every user's finished searches with an area (the sign-in page)."""
        db = self._db()
        try:
            total, count = db.execute("SELECT COALESCE(SUM(area_km2), 0), COUNT(*) FROM jobs WHERE status = 'done' "
                                      "AND area_km2 IS NOT NULL").fetchone()
        finally:
            db.close()
        return total, count

    def get(self, job_id: str) -> Optional[Dict]:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def statuses(self, job_ids: Iterable[str]) -> Dict[str, str]:
        """The status of each of these jobs, in one query (a job that is gone is left out)."""
        job_ids = tuple(job_ids)
        if not job_ids:
            return {}
        with self._db() as db:
            rows = db.execute(f"SELECT id, status FROM jobs WHERE id IN {_in(job_ids)}", job_ids).fetchall()
        return {r[0]: r[1] for r in rows}

    def all(self, user_id: Optional[int] = None) -> List[Dict]:
        """The newest jobs, of one user (None: of everyone)."""
        mine = "" if user_id is None else "WHERE user_id = ? "
        with self._db() as db:
            rows = db.execute(f"SELECT id, created, status, title, run_id, error, error_info, finished, user_id "
                              f"FROM jobs {mine}ORDER BY created DESC LIMIT 200",
                              () if user_id is None else (user_id,)).fetchall()
        return [_with_info(dict(r)) for r in rows]

    def waiting_or_running(self) -> List[Dict]:
        """The jobs not finished yet, with their requests."""
        with self._db() as db:
            rows = db.execute(f"SELECT * FROM jobs WHERE status IN {_in(WAITING + ACTIVE)}",
                              WAITING + ACTIVE).fetchall()
        return [dict(r) for r in rows]

    @contextlib.contextmanager
    def _write(self):
        """A connection in one BEGIN IMMEDIATE transaction: committed at the end, rolled back on an error."""
        db = self._db()
        db.isolation_level = None  # our own BEGIN / COMMIT
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        finally:
            db.close()

    def claim(self, waiting: str, status: str, worker_id: Optional[str] = None) -> Optional[Dict]:
        """Take a job of the status `waiting` and set it to `status` (None if there is none): the
        oldest job of the user with the fewest jobs running (downloading or computing, by any
        worker); jobs without a user (the local app's) count as one user's. So one user's queue
        never holds the others' jobs back.

        One statement in one write transaction, so two workers never take the same job.
        """
        started = f", {PHASE_TIME[status]} = ?" if status in PHASE_TIME else ""  # when the phase started
        with self._write() as db:
            rows = db.execute(
                f"UPDATE jobs SET status = ?, worker_id = ?{started} WHERE id = (SELECT j.id FROM jobs j "
                "WHERE j.status = ? AND j.cancel_requested = 0 ORDER BY (SELECT COUNT(*) FROM jobs r "
                f"WHERE r.status IN {_in(ACTIVE)} AND r.user_id IS j.user_id), j.created, j.rowid LIMIT 1) "
                "AND status = ? RETURNING *",
                (status, worker_id, *((cache.now_iso(),) if started else ()), waiting, *ACTIVE, waiting)).fetchall()
            if rows:
                self._insert_event(db, rows[0]["id"], "status", {"status": status})
        return dict(rows[0]) if rows else None

    def set(self, job_id: str, status: str, when: Optional[Iterable[str]] = None, **fields) -> bool:
        """Set the status (and other columns) of a job; with `when` only if its status is one of
        those (e.g. a phase that ends must not overwrite a job cancelled meanwhile). Whether it changed.
        An `error` is a text or an error: a coded one (messages.Coded) is stored as its web text with
        its code and parameters in `error_info`; an error clears the code of an earlier one."""
        if status in FINISHED:
            fields["finished"] = cache.now_iso()
        if "error" in fields:
            error = fields["error"]
            coded = messages.user_error(error) if isinstance(error, BaseException) else None
            info = coded.info() if coded is not None else None
            fields["error"] = None if error is None else self.redact(
                coded.web_text() if coded is not None else cache.clean_error(error))
            fields["error_info"] = self.redact(info)
        if fields.get("error_info") is not None:
            fields["error_info"] = json.dumps(fields["error_info"])
        stamp = {PHASE_TIME[status]: cache.now_iso()} if status == "ready" else {}  # not in the event
        names = "".join(f", {k} = ?" for k in {**fields, **stamp})
        condition, values = "", ()
        if when is not None:
            values = tuple(when)
            condition = f" AND status IN {_in(values)}"
        with self._write() as db:
            changed = db.execute(f"UPDATE jobs SET status = ?{names} WHERE id = ?{condition}",
                                 (status, *fields.values(), *stamp.values(), job_id, *values)).rowcount
            if changed:
                self._insert_event(db, job_id, "status", _with_info({"status": status, **fields}))
        return bool(changed)

    def event(self, job_id: str, kind: str, data):
        with self._db() as db:
            self._insert_event(db, job_id, kind, data)

    def _insert_event(self, db: sqlite3.Connection, job_id: str, kind: str, data):
        """An event in the transaction of db: a status change writes its event in its own
        transaction, so the events of a job come in the order of its changes (a download process
        setting "ready" while the worker claims the job for computing wrote "computing" first)."""
        db.execute("INSERT INTO events (job, kind, data) VALUES (?, ?, ?)",
                   (job_id, kind, json.dumps(self.redact(data))))

    def job_events(self, job_id: str, limit: int = JOB_EVENTS_MAX) -> Dict:
        """The history of one job for its page: its newest `limit` events other than progress, and
        its last progress event, oldest first; "omitted": how many older messages were left out."""
        with self._db() as db:
            rows = db.execute("SELECT * FROM (SELECT * FROM events WHERE job = ? AND kind != 'progress' ORDER BY "
                              "seq DESC LIMIT ?) UNION ALL SELECT * FROM (SELECT * FROM events WHERE job = ? AND "
                              "kind = 'progress' ORDER BY seq DESC LIMIT 1) ORDER BY seq",
                              (job_id, limit, job_id)).fetchall()
            count = db.execute("SELECT COUNT(*) FROM events WHERE job = ? AND kind != 'progress'",
                               (job_id,)).fetchone()[0]
        return {"events": [{"seq": r["seq"], "job": r["job"], "kind": r["kind"], "data": json.loads(r["data"])}
                           for r in rows], "omitted": max(0, count - limit)}

    def events(self, since: int, job_id: Optional[str] = None, user_id: Optional[int] = None,
               until: Optional[int] = None) -> List[Dict]:
        """The events after `since` (and up to `until`): of one job, or of all jobs (of one user's
        jobs with user_id; EVENTS_LIMIT of them at most)."""
        end = until if until is not None else 2 ** 63 - 1
        with self._db() as db:
            if job_id:
                rows = db.execute("SELECT * FROM events WHERE seq > ? AND seq <= ? AND job = ? ORDER BY seq",
                                  (since, end, job_id))
            elif user_id is not None:
                rows = db.execute("SELECT e.* FROM events e JOIN jobs j ON j.id = e.job WHERE e.seq > ? AND "
                                  "e.seq <= ? AND j.user_id = ? ORDER BY e.seq LIMIT ?",
                                  (since, end, user_id, EVENTS_LIMIT))
            else:
                rows = db.execute("SELECT * FROM events WHERE seq > ? AND seq <= ? ORDER BY seq LIMIT ?",
                                  (since, end, EVENTS_LIMIT))
            return [{"seq": r["seq"], "job": r["job"], "kind": r["kind"], "data": json.loads(r["data"])}
                    for r in rows.fetchall()]

    def owned_events(self, since: int) -> List[Tuple[Optional[int], Dict]]:
        """The events of all jobs after `since` (EVENTS_LIMIT at most), each with the owner of its
        job (None: the local app's, or a job gone): for the event poller of the web process
        (web.EventHub), which hands each stream the events its user may see."""
        with self._db() as db:
            rows = db.execute("SELECT e.*, j.user_id AS owner FROM events e LEFT JOIN jobs j ON j.id = e.job "
                              "WHERE e.seq > ? ORDER BY e.seq LIMIT ?", (since, EVENTS_LIMIT)).fetchall()
        return [(r["owner"], {"seq": r["seq"], "job": r["job"], "kind": r["kind"], "data": json.loads(r["data"])})
                for r in rows]

    def last_seq(self, user_id: Optional[int] = None) -> int:
        """The id of the last event (of one user's jobs with user_id)."""
        with self._db() as db:
            if user_id is not None:
                return db.execute("SELECT COALESCE(MAX(e.seq), 0) FROM events e JOIN jobs j ON j.id = e.job "
                                  "WHERE j.user_id = ?", (user_id,)).fetchone()[0]
            return db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]

    # --- The runs: their owners and share links (web.py serves their files by these) ---

    def add_run(self, run_id: str, user_id: Optional[int], size: int):
        """A run saved by a job of a user (None: the local app's); the job's owner wins over an owner
        given by adopt_runs meanwhile."""
        with self._db() as db:
            db.execute("INSERT INTO runs (run_id, user_id, bytes, created) VALUES (?, ?, ?, ?) ON CONFLICT (run_id) "
                       "DO UPDATE SET user_id = excluded.user_id, bytes = excluded.bytes",
                       (run_id, user_id, size, cache.now_iso()))

    def run(self, run_id: str) -> Optional[Dict]:
        with self._db() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def runs_of(self, user_id: int) -> Set[str]:
        """The ids of a user's runs."""
        with self._db() as db:
            return {r[0] for r in db.execute("SELECT run_id FROM runs WHERE user_id = ?", (user_id,))}

    def adopt_runs(self, runs_dir: str, user_id: Optional[int]) -> int:
        """Give the runs without an owner to `user_id` (the first administrator), as private runs:
        those of the folder without a row (saved before the public mode, or on the command line) and
        rows without a user (the local app's), with the local app's favourite lines. Runs in progress
        (no run.json yet) are left to their job. Nothing is deleted. Returns how many runs were given."""
        import runs as rn
        found = []
        if os.path.isdir(runs_dir):
            for entry in os.scandir(runs_dir):
                if entry.is_dir() and not entry.name.startswith((".", "_")) \
                        and os.path.isfile(os.path.join(entry.path, "run.json")):
                    found.append(entry.name)
        with self._write() as db:
            known = {r[0] for r in db.execute("SELECT run_id FROM runs")}
            now = cache.now_iso()
            new = [run_id for run_id in found if run_id not in known]
            for run_id in new:
                db.execute("INSERT INTO runs (run_id, user_id, bytes, created) VALUES (?, ?, ?, ?)",
                           (run_id, user_id, rn.folder_bytes(os.path.join(runs_dir, run_id)), now))
            given = db.execute("UPDATE runs SET user_id = ? WHERE user_id IS NULL", (user_id,)).rowcount \
                if user_id is not None else 0
            if user_id is not None:  # the local app's favourites and their folders go with its runs
                db.execute("UPDATE OR IGNORE favourites SET user_id = ? WHERE user_id IS NULL", (user_id,))
                db.execute("UPDATE favourite_folders SET user_id = ? WHERE user_id IS NULL", (user_id,))
        return len(new) + given

    def set_share(self, run_id: str, share_hash: Optional[str]):
        """The sha256 of a run's share link (None: not shared); a new one replaces the old link."""
        with self._db() as db:
            db.execute("UPDATE runs SET share_hash = ? WHERE run_id = ?", (share_hash, run_id))

    def shared_runs(self, user_id: int) -> Set[str]:
        """The ids of a user's runs that have a share link."""
        with self._db() as db:
            return {r[0] for r in db.execute("SELECT run_id FROM runs WHERE user_id = ? AND share_hash IS NOT NULL",
                                             (user_id,))}

    def set_visibility(self, run_id: str, visibility: str) -> bool:
        """Who sees a run: "private" (its owner, administrators) or "demo" (everyone, also without
        signing in); whether the run has a row."""
        if visibility not in VISIBILITIES:
            raise ValueError(visibility)
        with self._db() as db:
            return bool(db.execute("UPDATE runs SET visibility = ? WHERE run_id = ?", (visibility, run_id)).rowcount)

    def delete_run(self, run_id: str, runs_dir: str):
        """Delete a run: its folder, then its row (its share link and demo flag go with it) and the
        favourite lines of everyone in it. A folder that cannot be deleted raises OSError and keeps its
        row (or adopt_runs would give it away)."""
        folder = os.path.join(runs_dir, run_id)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        with self._db() as db:
            db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            db.execute("DELETE FROM favourites WHERE run_id = ?", (run_id,))

    # --- Favourite lines (the maps mark them, the app lists them) ---

    def favourites(self, user_id: Optional[int], run_id: Optional[str] = None) -> List[Dict]:
        """A user's favourite lines (of one run), newest first: run_id, line, data (a dict), created and
        folder_id (None: the top level)."""
        query, args = "SELECT run_id, line, data, created, folder_id FROM favourites WHERE user_id IS ?", [user_id]
        if run_id is not None:
            query += " AND run_id = ?"
            args.append(run_id)
        with self._db() as db:
            rows = db.execute(query + " ORDER BY created DESC, rowid DESC", args).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def set_favourite(self, user_id: Optional[int], run_id: str, line: str, data: Optional[Dict],
                      folder_id: Optional[int] = None):
        """Mark a line of a run as a favourite of a user (with its values `data`, in the user's folder
        `folder_id`, None: the top level), or unmark it (data None). Marking one more than FAVOURITES_MAX
        raises QuotaExceeded (409), a folder not the user's KeyError; marking a line again keeps the first
        values and its folder (move_favourite moves it)."""
        with self._write() as db:
            if data is None:
                db.execute("DELETE FROM favourites WHERE user_id IS ? AND run_id = ? AND line = ?",
                           (user_id, run_id, line))
                return
            self._own_folder(db, user_id, folder_id)
            count = db.execute("SELECT COUNT(*) FROM favourites WHERE user_id IS ?", (user_id,)).fetchone()[0]
            known = db.execute("SELECT 1 FROM favourites WHERE user_id IS ? AND run_id = ? AND line = ?",
                               (user_id, run_id, line)).fetchone()
            if not known and count >= FAVOURITES_MAX:
                raise QuotaExceeded(f"at most {FAVOURITES_MAX} favourite lines: remove some first", 409,
                                    "favourites_max", max=FAVOURITES_MAX)
            db.execute("INSERT INTO favourites (user_id, run_id, line, data, created, folder_id) "
                       "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                       (user_id, run_id, line, json.dumps(data), cache.now_iso(),
                        folder_id))

    def move_favourite(self, user_id: Optional[int], run_id: str, line: str, folder_id: Optional[int]):
        """Move a favourite of a user into the user's folder `folder_id` (None: the top level); KeyError
        when the favourite or the folder is not the user's."""
        with self._write() as db:
            self._own_folder(db, user_id, folder_id)
            if not db.execute("UPDATE favourites SET folder_id = ? WHERE user_id IS ? AND run_id = ? AND line = ?",
                              (folder_id, user_id, run_id, line)).rowcount:
                raise KeyError(line)

    # --- Folders of favourites (nested; deleting one deletes what is in it) ---

    def folders(self, user_id: Optional[int]) -> List[Dict]:
        """A user's folders of favourites: id, parent_id (None: the top level), name, created; by name."""
        with self._db() as db:
            rows = db.execute("SELECT id, parent_id, name, created FROM favourite_folders WHERE user_id IS ? "
                              "ORDER BY name COLLATE NOCASE, id", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _tree(db, user_id: Optional[int]) -> Dict[int, Optional[int]]:
        """The parent of each folder of a user."""
        return {r[0]: r[1] for r in db.execute("SELECT id, parent_id FROM favourite_folders WHERE user_id IS ?",
                                               (user_id,))}

    @classmethod
    def _own_folder(cls, db, user_id: Optional[int], folder_id: Optional[int]):
        """KeyError unless `folder_id` is None (the top level) or a folder of the user."""
        if folder_id is not None and not db.execute("SELECT 1 FROM favourite_folders WHERE id = ? AND user_id IS ?",
                                                    (folder_id, user_id)).fetchone():
            raise KeyError(folder_id)

    @staticmethod
    def _depth(parents: Dict[int, Optional[int]], folder_id: Optional[int]) -> int:
        """How deep a folder is (the top level 0, a folder in it 1)."""
        depth = 0
        while folder_id is not None:
            depth += 1
            folder_id = parents.get(folder_id)
        return depth

    @staticmethod
    def _subtree(parents: Dict[int, Optional[int]], folder_id: int) -> List[int]:
        """A folder and every folder inside it, at any depth."""
        found, todo = [], [folder_id]
        while todo:
            f = todo.pop()
            found.append(f)
            todo += [c for c, p in parents.items() if p == f]
        return found

    def add_folder(self, user_id: Optional[int], name: str, parent_id: Optional[int] = None) -> int:
        """A new folder of a user in `parent_id` (None: the top level); its id. KeyError for a parent not
        the user's, ValueError beyond FOLDER_DEPTH_MAX, QuotaExceeded (409) beyond FOLDERS_MAX."""
        with self._write() as db:
            self._own_folder(db, user_id, parent_id)
            parents = self._tree(db, user_id)
            if len(parents) >= FOLDERS_MAX:
                raise QuotaExceeded(f"at most {FOLDERS_MAX} folders: delete some first", 409, "folders_max",
                                    max=FOLDERS_MAX)
            if self._depth(parents, parent_id) + 1 > FOLDER_DEPTH_MAX:
                raise ValueError(f"folders go at most {FOLDER_DEPTH_MAX} deep")
            return db.execute("INSERT INTO favourite_folders (user_id, parent_id, name, created) VALUES (?, ?, ?, ?)",
                              (user_id, parent_id, name, cache.now_iso())).lastrowid

    def change_folder(self, user_id: Optional[int], folder_id: int, name: Optional[str] = None,
                      parent_id: Optional[int] = None, move: bool = False):
        """Rename a user's folder (`name`) and/or move it into `parent_id` (`move`; None: the top level).
        KeyError for a folder not the user's; ValueError for a move into itself or its own folders, or
        beyond FOLDER_DEPTH_MAX."""
        with self._write() as db:
            self._own_folder(db, user_id, folder_id)
            if move:
                self._own_folder(db, user_id, parent_id)
                parents = self._tree(db, user_id)
                inside = self._subtree(parents, folder_id)
                if parent_id in inside:
                    raise ValueError("a folder cannot go into itself or one of its folders")
                height = max(self._depth(parents, f) for f in inside) - self._depth(parents, folder_id) + 1
                if self._depth(parents, parent_id) + height > FOLDER_DEPTH_MAX:
                    raise ValueError(f"folders go at most {FOLDER_DEPTH_MAX} deep")
                db.execute("UPDATE favourite_folders SET parent_id = ? WHERE id = ?", (parent_id, folder_id))
            if name is not None:
                db.execute("UPDATE favourite_folders SET name = ? WHERE id = ?", (name, folder_id))

    def delete_folder(self, user_id: Optional[int], folder_id: int) -> Dict[str, int]:
        """Delete a user's folder with the folders and favourite lines in it (as a browser's bookmarks);
        how many of each went. KeyError for a folder not the user's."""
        with self._write() as db:
            self._own_folder(db, user_id, folder_id)
            inside = self._subtree(self._tree(db, user_id), folder_id)
            marks = ",".join("?" * len(inside))
            lines = db.execute(f"DELETE FROM favourites WHERE user_id IS ? AND folder_id IN ({marks})",
                               (user_id, *inside)).rowcount
            db.execute(f"DELETE FROM favourite_folders WHERE id IN ({marks})", inside)
        return {"folders": len(inside), "favourites": lines}

    # --- Problem reports (the users send them, administrators read them) ---

    def add_report(self, user_id: Optional[int], category: str, text: str, context: Dict) -> int:
        """A user's problem report (checked by web.checked_report); its id."""
        with self._db() as db:
            return db.execute("INSERT INTO reports (user_id, created, category, text, context) VALUES (?, ?, ?, ?, ?)",
                              (user_id, cache.now_iso(), category, text,
                               json.dumps(context))).lastrowid

    def reports(self, limit: int = 200) -> List[Dict]:
        """The latest problem reports, newest first: id, user_id, created, category, text, context (a
        dict), status."""
        with self._db() as db:
            rows = db.execute("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "context": json.loads(r["context"])} for r in rows]

    def set_report_status(self, report_id: int, status: str):
        """Mark a report open or done; KeyError when there is none, ValueError for another status."""
        if status not in REPORT_STATUSES:
            raise ValueError(status)
        with self._db() as db:
            if not db.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id)).rowcount:
                raise KeyError(report_id)

    def delete_report(self, report_id: int):
        """Delete a report; KeyError when there is none."""
        with self._db() as db:
            if not db.execute("DELETE FROM reports WHERE id = ?", (report_id,)).rowcount:
                raise KeyError(report_id)

    def all_runs(self) -> List[Dict]:
        """Every run's row (the admin tab), newest first."""
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT run_id, user_id, visibility, bytes, created, "
                                                "share_hash IS NOT NULL AS shared FROM runs ORDER BY created DESC")]

    def workers(self) -> List[Dict]:
        """The workers holding a lease (the admin tab)."""
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT id, pid, host, started FROM workers WHERE expires > ?",
                                                (time.time(),))]

    def demo_runs(self) -> Set[str]:
        """The ids of the demo runs."""
        with self._db() as db:
            return {r[0] for r in db.execute("SELECT run_id FROM runs WHERE visibility = 'demo'")}

    def shared_run(self, share_hash: str) -> Optional[str]:
        """The run of a share link's sha256 (None if no run has it)."""
        with self._db() as db:
            row = db.execute("SELECT run_id FROM runs WHERE share_hash = ?", (share_hash,)).fetchone()
        return row[0] if row else None

    # --- Workers and their leases ---

    def register(self, worker_id: str):
        """A worker starts: its lease."""
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO workers (id, pid, host, started, expires) VALUES (?, ?, ?, ?, ?)",
                       (worker_id, os.getpid(), socket.gethostname(), cache.now_iso(),
                        time.time() + LEASE))

    def heartbeat(self, worker_id: str) -> bool:
        """Renew a worker's lease; False if it had expired already (its jobs may have been failed)."""
        now = time.time()
        with self._db() as db:
            return bool(db.execute("UPDATE workers SET expires = ? WHERE id = ? AND expires > ?",
                                   (now + LEASE, worker_id, now)).rowcount)

    def unregister(self, worker_id: str):
        with self._db() as db:
            db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))

    def worker_alive(self) -> bool:
        """Whether any worker holds a lease (the page says so when none does)."""
        with self._db() as db:
            return db.execute("SELECT 1 FROM workers WHERE expires > ? LIMIT 1", (time.time(),)).fetchone() is not None

    def interrupted(self, worker_id: Optional[str] = None) -> List[str]:
        """Fail the running jobs of workers that are gone: whose lease expired (or of no worker,
        from before the leases), or those of `worker_id` when it stops. Returns their ids."""
        now = time.time()
        with self._write() as db:
            if worker_id:
                rows = db.execute(f"SELECT id FROM jobs WHERE status IN {_in(ACTIVE)} AND worker_id = ?",
                                  (*ACTIVE, worker_id))
            else:
                rows = db.execute(f"SELECT id FROM jobs WHERE status IN {_in(ACTIVE)} AND (worker_id IS NULL "
                                  "OR worker_id NOT IN (SELECT id FROM workers WHERE expires > ?))", (*ACTIVE, now))
            ids = [r[0] for r in rows.fetchall()]
            gone = json.dumps({"code": 503, "body": "the worker stopped"})
            if worker_id:
                db.execute("UPDATE quick SET status = 'done', answer = ? WHERE status = 'running' AND worker_id = ?",
                           (gone, worker_id))
            else:
                db.execute("UPDATE quick SET status = 'done', answer = ? WHERE status = 'running' AND worker_id NOT IN "
                           "(SELECT id FROM workers WHERE expires > ?)", (gone, now))
            db.execute("DELETE FROM workers WHERE expires <= ?", (now - LEASE,))  # long gone
        return [job_id for job_id in ids if self.set(job_id, "failed", when=ACTIVE, error=INTERRUPTED)]

    # --- The quick lane ---

    def quick_add(self, kind: str, request: Dict, user_id: Optional[int] = None, unlimited: bool = False,
                  one_waiting: bool = False) -> int:
        """A task for the quick lane (a kind of QUICK) of a user (`unlimited`: without the
        worker's Limits); its id. With `one_waiting` (the public site), QuotaExceeded while another
        task of the same user waits (checked in the insert's transaction)."""
        with self._write() as db:
            if one_waiting and user_id is not None and db.execute(
                    "SELECT 1 FROM quick WHERE user_id = ? AND status = 'waiting' LIMIT 1", (user_id,)).fetchone():
                raise QuotaExceeded("another estimate, profile or place lookup of yours is still waiting: try again when it "
                                    "is answered", code="quick_waiting")
            return db.execute("INSERT INTO quick (kind, request, status, created, user_id, unlimited) "
                              "VALUES (?, ?, 'waiting', ?, ?, ?)",
                              (kind, json.dumps(request), time.time(), user_id, int(unlimited))).lastrowid

    def quick_forget_user(self, user_id: int) -> int:
        """Delete the waiting tasks of a user (blocked); how many."""
        with self._db() as db:
            return db.execute("DELETE FROM quick WHERE user_id = ? AND status = 'waiting'", (user_id,)).rowcount

    def quick_ahead(self, task_id: int) -> int:
        """Tasks of the quick lane waiting or running before this one."""
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM quick WHERE id < ? AND status IN ('waiting', 'running')",
                              (task_id,)).fetchone()[0]

    def quick_take(self, task_id: int) -> Optional[Dict]:
        """The answer of a task once it is there ({"code", "body"}), removing the task; else None.
        A read first: no write transaction while the answer is not there."""
        with contextlib.closing(self._db()) as db:
            if db.execute("SELECT 1 FROM quick WHERE id = ? AND status = 'done'", (task_id,)).fetchone() is None:
                return None
        with self._write() as db:
            row = db.execute("SELECT answer FROM quick WHERE id = ? AND status = 'done'", (task_id,)).fetchone()
            if row:
                db.execute("DELETE FROM quick WHERE id = ?", (task_id,))
        return json.loads(row["answer"]) if row else None

    def quick_forget(self, task_id: int):
        """Delete a task nobody waits for any more; a running one stays until it is answered (the
        lane's time limit applies to it) and is deleted with the other answers nobody took."""
        with self._db() as db:
            db.execute("DELETE FROM quick WHERE id = ? AND status != 'running'", (task_id,))

    def quick_waiting(self, db: Optional[sqlite3.Connection] = None) -> bool:
        """Whether a task of the quick lane waits: a read (on `db`, the lane's own connection, if
        given), so the idle lane opens no write transaction."""
        if db is not None:
            return db.execute("SELECT 1 FROM quick WHERE status = 'waiting' LIMIT 1").fetchone() is not None
        with contextlib.closing(self._db()) as own:
            return self.quick_waiting(own)

    def quick_claim(self, worker_id: str) -> Optional[Dict]:
        """The oldest waiting task, now running on `worker_id`; None if none waits."""
        with self._write() as db:
            rows = db.execute("UPDATE quick SET status = 'running', worker_id = ?, started = ? WHERE id = "
                              "(SELECT id FROM quick WHERE status = 'waiting' ORDER BY id LIMIT 1) "
                              "AND status = 'waiting' RETURNING *", (worker_id, time.time())).fetchall()
        return dict(rows[0]) if rows else None

    def quick_running(self, worker_id: str) -> Optional[Dict]:
        with self._db() as db:
            row = db.execute("SELECT * FROM quick WHERE status = 'running' AND worker_id = ?", (worker_id,)).fetchone()
        return dict(row) if row else None

    def forget_quick(self, seconds: float = KEEP_QUICK_SECONDS) -> int:
        """Delete tasks of the quick lane nobody waits for any more: answers older than `seconds`
        nobody took, waiting tasks of a web process that stopped (KEEP_WAITING_QUICK_SECONDS; a web
        process deletes its own when it gives up). Waiting tasks someone awaits stay."""
        now = time.time()
        with self._db() as db:
            return db.execute("DELETE FROM quick WHERE (status = 'done' AND created < ?) OR (status = 'waiting' AND "
                              "created < ?)", (now - seconds, now - KEEP_WAITING_QUICK_SECONDS)).rowcount

    def forget_events(self, days: float) -> int:
        """Delete the events (messages, progress) of jobs finished more than `days` ago; the jobs stay."""
        cutoff = cache.now_iso(ago=days * 86400)
        with self._db() as db:
            return db.execute(f"DELETE FROM events WHERE job IN (SELECT id FROM jobs WHERE status IN {_in(FINISHED)} "
                              "AND finished < ?)", (*FINISHED, cutoff)).rowcount

    def quick_answer(self, task_id: int, code: int, body):
        """The answer of a running task."""
        with self._db() as db:
            db.execute("UPDATE quick SET status = 'done', answer = ? WHERE id = ? AND status = 'running'",
                       (json.dumps({"code": code, "body": self.redact(body)}), task_id))

    # --- Cancelling ---

    def request_cancel(self, job_id: str) -> bool:
        """Cancel a job: a waiting one (or one whose worker is gone) at once, a running one through
        its worker (cancel_requested). False if it is not waiting or running."""
        with self._write() as db:
            row = db.execute("SELECT status, worker_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or row["status"] not in WAITING + ACTIVE:
                return False
            alive = db.execute("SELECT 1 FROM workers WHERE id = ? AND expires > ?",
                               (row["worker_id"], time.time())).fetchone()
            now = row["status"] in WAITING or not alive
            finished = cache.now_iso()
            if now:
                db.execute("UPDATE jobs SET status = 'cancelled', finished = ? WHERE id = ?", (finished, job_id))
                self._insert_event(db, job_id, "status", {"status": "cancelled", "finished": finished})
            else:
                db.execute("UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))
        return True

    def cancel_requested(self, job_ids: Iterable[str]) -> Set[str]:
        """Which of these jobs are to be cancelled; jobs that wait with the request are cancelled
        here (a download that ended just after it)."""
        job_ids = tuple(job_ids)
        with self._db() as db:
            waiting = [r[0] for r in db.execute(f"SELECT id FROM jobs WHERE cancel_requested = 1 AND status IN "
                                                f"{_in(WAITING)}", WAITING)]
            found = {r[0] for r in db.execute(f"SELECT id FROM jobs WHERE cancel_requested = 1 AND id IN "
                                              f"{_in(job_ids)}", job_ids)} if job_ids else set()
        for job_id in waiting:
            self.set(job_id, "cancelled", when=WAITING)
        return found


# --- The worker: one process per job and phase ------------------------------------------

class _EventWriter:
    """stdout of a worker: every line becomes an "info" event of the job."""

    def __init__(self, jobs: Jobs, job_id: str):
        self.jobs, self.job_id, self.buffer = jobs, job_id, ""

    def write(self, text: str):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.jobs.event(self.job_id, "info", line)
        return len(text)

    def flush(self):
        pass


def search_params(request: Dict) -> pm.SearchParams:
    """The parameters of a request, a drawn or uploaded area as their geometry (validated, no file)."""
    values = dict(request["params"])
    if request.get("geometry") is not None:
        values["geometry"] = request["geometry"]
    return pm.SearchParams(**values)


def ortho_confirm(limits: Limits, on_event):
    """search.Confirm of the worker: yes, except to orthophoto over Limits.ortho_minutes (the map
    loads it online then); sets search.CONFIRM_MINUTES to that limit."""
    import search
    if limits.ortho_minutes is None:
        return lambda kind, text: True
    search.CONFIRM_MINUTES = limits.ortho_minutes

    def confirm(kind: str, text: str) -> bool:
        if kind != "ortho":
            return True
        on_event("info", f"The orthophoto would take more than {limits.ortho_minutes:g} min to download: the map "
                         f"loads it online")
        return False
    return confirm


def nominatim_quota(jobs: Jobs, user_id: Optional[int], limits: Optional[Limits]):
    """Count the uncached Nominatim requests of this process's work (a job's phase, a quick task) for
    its user, against Limits.nominatim_day_max: osm.BEFORE_REQUEST, which refuses a request over the
    quota before it is sent (QuotaExceeded). None (no limits, no user): nothing is counted."""
    import osm
    osm.BEFORE_REQUEST = None
    if limits is not None and limits.nominatim_day_max is not None and user_id is not None:
        osm.BEFORE_REQUEST = lambda: jobs.use(user_id, "nominatim", 1, limits.nominatim_day_max)


def check_disk(data_dir: str, limits: Optional[Limits], phase: str):
    """Fail a phase while the disk of the data folder has less free space than Limits.free_disk_gb_min
    (a safeguard for everyone: also for users without limits)."""
    if limits is None or limits.free_disk_gb_min is None:
        return
    free = shutil.disk_usage(data_dir).free / 1e9
    if free < limits.free_disk_gb_min:
        raise QuotaExceeded(f"the server is short of disk space ({free:.0f} GB free): the search stopped before "
                            f"its {phase}; try again later", 503, "disk_full_search")


def plan_km2(plan) -> float:
    """The km² of a planned search's area; known only here for osm:<name> and coast/cliffs areas. A
    circle counts as π r²."""
    return area_km2(plan.area)


def plan_mpx(plan) -> float:
    """The millions of pixels of a planned search's area at its resolution (km² / resolution²): what
    its computing costs follows (the compute quota, Limits.mpx_day_max)."""
    return plan_km2(plan) / plan.resolution ** 2


def charge_area(jobs: Jobs, user_id: Optional[int], plan, limits: Optional[Limits]):
    """Count the Mpx and km² of a search's area for its user against Limits.mpx_day_max and
    km2_day_max (QuotaExceeded over one; the Mpx first)."""
    if limits is None or user_id is None:
        return
    if limits.mpx_day_max is not None:
        jobs.use(user_id, "mpx", plan_mpx(plan), limits.mpx_day_max)
    if limits.km2_day_max is not None:
        jobs.use(user_id, "km2", plan_km2(plan), limits.km2_day_max)


def note_area(jobs: Jobs, job_id: str, plan, cache_dir: str):
    """Store the km² of a job's search, its outline (area_outline: for coast, cliffs and osm: areas the
    region the search covers) and the country of its centre (sources.country_code, usually cached
    already by --source auto) for every user: the users' totals and the site's statistics.
    The lookup does not count against the user's quota of Nominatim requests (the statistics are
    the site's); it never fails the search."""
    import osm
    from sources import choose
    before, osm.BEFORE_REQUEST = osm.BEFORE_REQUEST, None
    try:
        lat, lon = plan.area.center
        country = choose.country_code(lat, lon, cache_dir)
    except Exception:  # the statistics never fail a search
        country = None
    finally:
        osm.BEFORE_REQUEST = before
    jobs.set_area(job_id, plan_km2(plan), country, area_outline(plan.area))


class StepClock:
    """The seconds and CPU seconds of a computing phase per step (STEP_KEYS), from the states of the
    progress bars (progress.subscribe): the time until a state goes to what the previous state was in,
    the step of its text ("Tile 2/6 · Step 3/5: ...") or the orthophoto tiles while their bar runs.
    Also those of the stages of the line search (STAGE_KEYS) while their Compute bar runs (from a state
    of that stage, not done, to the next state), summed over the tiles. CPU: time.process_time, the
    whole process (numba's threads too)."""

    def __init__(self):
        self.seconds: Dict[str, float] = {}
        self.cpu_seconds: Dict[str, float] = {}
        self.stage_times: Dict[str, List[float]] = {}  # stage -> [seconds, CPU seconds]
        self.key, self.stage = "other", None
        self.since, self.cpu_since = time.monotonic(), time.process_time()

    def __call__(self, state: Dict):
        self._add()
        if state.get("bar") == "Download" and state.get("stage") == "orthophoto tiles" and not state.get("done"):
            self.key = "orthophoto"
        else:
            found = re.search(r"Step (\d)/", state.get("step") or "")
            self.key = found.group(1) if found and found.group(1) in STEP_KEYS else "other"
        running = state.get("bar") == "Compute" and not state.get("done")
        self.stage = state.get("stage") if running and state.get("stage") in STAGE_KEYS else None

    def _add(self):
        now, cpu = time.monotonic(), time.process_time()
        seconds, cpu_seconds = now - self.since, cpu - self.cpu_since
        self.seconds[self.key] = self.seconds.get(self.key, 0.0) + seconds
        self.cpu_seconds[self.key] = self.cpu_seconds.get(self.key, 0.0) + cpu_seconds
        if self.stage is not None:
            times = self.stage_times.setdefault(self.stage, [0.0, 0.0])
            times[0] += seconds
            times[1] += cpu_seconds
        self.since, self.cpu_since = now, cpu

    def result(self) -> Dict[str, float]:
        """The seconds per step until now."""
        self._add()
        return dict(self.seconds)

    def cpu(self) -> Dict[str, float]:
        """The CPU seconds per step until now."""
        self._add()
        return dict(self.cpu_seconds)

    def stages(self) -> Dict[str, Tuple[float, float]]:
        """The seconds and CPU seconds of the stages of the line search until now."""
        self._add()
        return {stage: (s, c) for stage, (s, c) in self.stage_times.items()}


def _write_statistics(jobs: Jobs, job_id: str, steps: StepClock, funnel: Dict[str, int]):
    """The statistics of a finished computing phase (F19): the seconds and CPU seconds per step, the
    stages and the funnel of the line search. They never fail the search: a line to stderr (stdout of
    a phase is the job's events)."""
    try:
        seconds, cpu, stages = steps.result(), steps.cpu(), steps.stages()
        jobs.set_steps(job_id, seconds, cpu)
        jobs.set_stages(job_id, stages)
        jobs.set_funnel(job_id, funnel)
    except Exception as e:  # statistics only
        print(f"statistics of job {job_id} not written: {type(e).__name__}: {e}", file=sys.stderr, flush=True)


def _orthophoto_after(jobs: Jobs, job_id: str, plan, spots: List[Dict], limits: Optional[Limits], on_event,
                      steps: StepClock):
    """The orthophoto step of a job done already (run_phase): search.download_orthophoto with the
    worker's answer to its question (ortho_confirm), its progress and messages as events of the job
    as before, then its seconds added to the job's steps (STEP_KEYS "orthophoto", as when it was part
    of the phase; only that row: "other" keeps the phase's own value, so the phase's seconds outside
    its steps still follow from its timestamps and its steps, tools/job_stats.py). An error leaves
    the job and its run as they are: a line to stderr and a warning event (the map loads the
    orthophoto online)."""
    import search
    try:
        search.download_orthophoto(plan, spots, ortho_confirm(limits or Limits(), on_event))
    except Exception as e:  # the job is done: never its status or its run
        print(f"orthophoto of job {job_id} not cached: {type(e).__name__}: {cache.clean_error(e)}",
              file=sys.stderr, flush=True)
        on_event("warning", "The orthophoto could not be cached for offline use: the map loads it online")
    try:
        seconds, cpu = steps.result(), steps.cpu()
        if "orthophoto" in seconds:
            jobs.set_steps(job_id, {"orthophoto": seconds["orthophoto"]}, {"orthophoto": cpu.get("orthophoto")})
    except Exception as e:  # statistics only
        print(f"statistics of job {job_id} not written: {type(e).__name__}: {e}", file=sys.stderr, flush=True)


def run_phase(data_dir: str, job_id: str, phase: str, limits: Optional[Limits] = None, public: bool = False,
              memory: Optional[int] = None):
    """A worker process: download the data of a job, or compute it. It ends the phase only if the
    job is still in it (not cancelled or failed by the worker meanwhile). With limits, a search
    over them fails before its costly work (search.plan_search, check_estimate); a job of a user
    without limits gets none, and the user's quotas (km², Nominatim) are counted here. `memory`:
    the budget of a compute slot (search.slot_memory; None with one slot), for every user: it sizes
    the tiles (in the download phase, which announces them) and refuses lines that would not fit."""
    import requests

    import progress as pg
    import search
    from progress import progress

    jobs = Jobs(data_dir, public)
    job = jobs.get(job_id)
    request = json.loads(job["request"])
    safeguards = limits  # of the server: for everyone
    if job["unlimited"]:
        limits = None  # a user without limits: the time limits of the phase (Scheduler) still apply
    nominatim_quota(jobs, job["user_id"], limits)
    servicecounts.enable(jobs.add_service_requests, tile_writer=jobs.add_layer_downloads)  # flushed every minute
    # and at the end of the phase
    sys.stdout = _EventWriter(jobs, job_id)
    pg.TEXT_INTERVAL = float("inf")  # the progress goes to the page as events, not as text
    last = [0.0]
    working = (PHASE_STATUS[phase],)

    def on_progress(state: Dict):
        if state["done"] or time.time() - last[0] >= PROGRESS_INTERVAL:
            last[0] = time.time()
            jobs.event(job_id, "progress", state)

    def on_event(kind: str, text: str):
        jobs.event(job_id, kind, text.web_text() if getattr(text, "code", None) else text)  # messages.Note

    progress.subscribe(on_progress)
    steps = StepClock()
    if phase == "compute":
        progress.subscribe(steps)
    paths = search.Paths(data_dir, os.path.join(jobs.folder(job_id), phase))  # removed with the job when killed
    os.makedirs(paths.work, exist_ok=True)
    failed = True
    try:
        check_disk(data_dir, safeguards, "download" if phase == "download" else "computing")
        if "osm" in request:  # an OpenStreetMap extract: one phase only
            import osmextract
            region = request["osm"]["region"]
            if request["osm"]["action"] == "download":
                osmextract.download(paths.cache, region)
            else:
                osmextract.update(paths.cache, region, dict(osmextract.extracts(paths.cache))[region])
            jobs.set(job_id, "done", when=working, error=None)
            failed = False
            return
        params = search_params(request)
        # Tiles are sized from the free memory: the computing phase uses the size the
        # download phase announced, not one from the memory free by then
        tile_file = os.path.join(jobs.folder(job_id), "tile_core.json")
        if phase == "compute":
            params = params.model_copy(update={"update": None})  # updated while downloading
            if params.tile_size is None and os.path.exists(tile_file):
                with open(tile_file, encoding="utf-8") as f:
                    params = params.model_copy(update={"tile_size": json.load(f)})
        plan = search.plan_search(params, paths, on_event, limits=limits, memory=memory)
        plan.owner = job["user_id"]  # a tiled search resumes only for the same user
        plan.index_runs = not public  # runs.js and index.html of the runs folder: read locally only
        if safeguards is not None:  # the server's switch, also for a user without limits (its memory budget)
            plan.early_stop = safeguards.lines_early_stop
        if phase == "download":
            note_area(jobs, job_id, plan, paths.cache)
            jobs.set_search(job_id, plan.source.id, plan.resolution)
            charge_area(jobs, job["user_id"], plan, limits)
            if limits and (limits.download_mb_max or limits.download_mb_day_max):  # the estimate asks the indexes
                estimate = search.estimate_search(plan)
                search.check_estimate(plan, estimate)
                if limits.download_mb_day_max and job["user_id"] is not None:  # the estimate, before the download
                    jobs.use(job["user_id"], "download_mb", estimate.download_mb, limits.download_mb_day_max)
            search.download_data(plan)
            if plan.tile_core:
                os.makedirs(jobs.folder(job_id), exist_ok=True)
                with open(tile_file, "w", encoding="utf-8") as f:
                    json.dump(plan.tile_core, f)
            jobs.set(job_id, "ready", when=working)
        else:
            lines, run = search.search_lines(plan)
            result = search.save_run(plan, lines, run)
            spots = search.orthophoto_lines(plan, lines)  # the orthophoto's strips, before the lines go
            import runs as rn
            jobs.add_run(result.run["id"], job["user_id"], rn.folder_bytes(result.run["path"]))  # its owner
            _write_statistics(jobs, job_id, steps, plan.funnel)
            done = jobs.set(job_id, "done", when=working, run_id=result.run["id"], error=None)
            if done:
                # The orthophoto for offline use comes after "done": the page has the result, and
                # the scheduler gives this compute slot to the next job meanwhile (Scheduler._occupied
                # counts no process of a job done). The lines are released first, so the process
                # holds its imports only: search.slot_memory reserves nothing for it
                del lines, result
                import gc
                gc.collect()
                _orthophoto_after(jobs, job_id, plan, spots, limits, on_event, steps)
        failed = False
    except (search.SearchError, ValueError, RuntimeError, requests.RequestException) as e:  # ValueError: parameters
        jobs.set(job_id, "failed", when=working, error=e)  # the web text of a coded error (Jobs.set)
        failed = False
    except Exception as e:  # anything else: keep the work folder to look at (not on the public site)
        if public:  # the traceback (raised below) goes to the log, the page gets a reference
            print(f"internal error, ref {job_id} (its working grids are removed):", file=sys.stderr)
            jobs.set(job_id, "failed", when=working, error=f"internal error, ref {job_id}")
            failed = False  # the public site keeps no work folders: its disk is shared
        else:
            jobs.set(job_id, "failed", when=working,
                     error=f"{type(e).__name__}: {cache.clean_error(e)} (working grids kept in {paths.work})")
        raise
    finally:
        servicecounts.flush()
        if not failed:
            import gc
            gc.collect()  # close the memory-mapped grids before deleting them (Windows)
            cache.remove_work(paths.work)
            if (jobs.get(job_id) or {}).get("status") in FINISHED:  # the job ended: tile_core.json is not needed
                shutil.rmtree(jobs.folder(job_id), ignore_errors=True)


def quick_estimate(data_dir: str, request: Dict, limits: Optional[Limits] = None) -> Dict:
    """The estimate of a search request (/api/estimate); a request over the limits is refused."""
    import search
    from area import Polygon, size_km2
    notes = []
    params = search_params(request)
    folder = os.path.join(data_dir, "work", "estimates", uuid.uuid4().hex)  # one per request
    try:
        paths = search.Paths(data_dir, folder)
        plan = search.plan_search(params, paths, lambda kind, text: notes.append(_message(kind, text)), limits=limits,
                                  memory=SLOT_MEMORY)  # the tiles of the job
        result = search.estimate_search(plan)
        search.check_estimate(plan, result)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return {"messages": notes, "reasons": result.reasons, "download_mb": round(result.download_mb),
            "work_gb": round(result.work_gb, 2), "source": plan.source.name,
            "tiles": len(plan.tiles) if plan.tiles else 1, "resolution": plan.resolution,
            "km2": size_km2(plan.area.geometry) if isinstance(plan.area, Polygon) else None,
            "area": plan.area.shape_wgs84().__geo_interface__}  # drawn on the map before the start


def _message(kind: str, text: str) -> list:
    """A message of an estimate: [kind, text], and {"code", "params"} of a coded one (messages.Note)
    with its web text."""
    info = getattr(text, "info", lambda: None)()
    return [kind, text.web_text(), info] if info else [kind, str(text)]


def quick_profile(data_dir: str, request: Dict, limits: Optional[Limits] = None) -> Dict:
    """The profile of a line of a saved run (/api/profile): {"run": id, "line": [lat1, lon1, lat2, lon2]}."""
    import search
    with open(os.path.join(data_dir, "runs", request["run"], "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    lat1, lon1, lat2, lon2 = request["line"]
    paths = search.Paths(data_dir, os.path.join(data_dir, "work", "profiles", uuid.uuid4().hex))
    os.makedirs(paths.work)
    try:
        return search.profile_of_line(meta, paths, (lat1, lon1), (lat2, lon2))
    finally:
        cache.remove_work(paths.work)


def quick_place(data_dir: str, request: Dict, limits: Optional[Limits] = None) -> Dict:
    """The places of a name (/api/place: {"q": name}) for the app's place box; Nominatim through
    osm.places (cached, counted by nominatim_quota)."""
    import osm
    return {"places": osm.places(request["q"], os.path.join(data_dir, "cache"))}


QUICK = {"estimate": quick_estimate, "profile": quick_profile, "place": quick_place}
SLOT_MEMORY: Optional[int] = None  # the budget of a compute slot, in the quick lane's process (run_quick)


def run_quick(data_dir: str, worker_id: str, parent: int, limits: Optional[Limits] = None, public: bool = False,
              memory: Optional[int] = None):
    """The process of the quick lane: serves the tasks of the table `quick` one after another, until
    its worker (`parent`) is gone. One process and one thread, so the state of search and sources
    (caches of sheet indexes, sag tables) is never shared between threads."""
    import traceback

    import psutil
    import requests

    import search
    global SLOT_MEMORY
    SLOT_MEMORY = memory  # an estimate's tiles as its job's (search.slot_memory)
    jobs = Jobs(data_dir, public)
    servicecounts.enable(jobs.add_service_requests, tile_writer=jobs.add_layer_downloads)  # flushed every
    # minute and after each task
    reader = jobs._db()  # one connection for the idle looks (reads, so no write lock 1/QUICK_POLL times a second)
    looked = time.time()
    while True:
        task = jobs.quick_claim(worker_id) if jobs.quick_waiting(reader) else None
        if task is None:
            if time.time() - looked > 2:
                looked = time.time()
                if not psutil.pid_exists(parent):
                    return
            time.sleep(QUICK_POLL)
            continue
        task_limits = None if task["unlimited"] else limits  # a user without limits: none
        nominatim_quota(jobs, task["user_id"], task_limits)
        try:
            jobs.quick_answer(task["id"], 200, QUICK[task["kind"]](data_dir, json.loads(task["request"]), task_limits))
        except QuotaExceeded as e:
            jobs.quick_answer(task["id"], e.status, e.detail())
        except (ValueError, search.SearchError, requests.RequestException) as e:  # ValueError: parameters
            coded = messages.user_error(e)  # {"message", "code", "params"} (web.error_detail)
            jobs.quick_answer(task["id"], 400, coded.detail() if coded is not None else cache.clean_error(e))
        except Exception as e:
            ref = f"quick-{task['id']}"
            print(f"internal error, ref {ref}:", file=sys.stderr)
            traceback.print_exc()
            jobs.quick_answer(task["id"], 500, f"internal error, ref {ref}" if public else
                              f"internal error: {type(e).__name__}: {cache.clean_error(e)}")
        finally:
            servicecounts.flush()


class Running(NamedTuple):
    """A phase of a job in its process."""
    job_id: str
    process: object
    started: float
    limit: Optional[float] = None  # seconds (Limits.phase_seconds), None: no limit
    what: str = "phase"            # for the error over the limit: "the download phase", "the OSM extract job"


def _remove_old(folder: str, days: float, keep: Iterable[str] = ()) -> int:
    """Delete the entries of a folder not changed for `days`, except those named in `keep`; their number."""
    limit, keep, removed = time.time() - days * 86400, set(keep), 0
    if not os.path.isdir(folder):
        return 0
    for entry in os.scandir(folder):
        with contextlib.suppress(OSError):
            if entry.name not in keep and entry.stat().st_mtime < limit:
                shutil.rmtree(entry.path) if entry.is_dir() else os.remove(entry.path)
                removed += 1
    return removed


CACHE_SIZES = "cache-sizes.json"  # in the work folder: the bytes of each top-level cache folder (metrics.py)


def cache_sizes(cache_dir: str) -> Dict[str, int]:
    """The bytes of the files in each top-level folder of the cache (symbolic links not followed)."""
    sizes = {}
    if not os.path.isdir(cache_dir):
        return sizes
    for top in os.scandir(cache_dir):
        if not top.is_dir(follow_symlinks=False):
            continue
        total = 0
        for folder, _, names in os.walk(top.path):
            for name in names:
                with contextlib.suppress(OSError):  # gone meanwhile
                    total += os.lstat(os.path.join(folder, name)).st_size
        sizes[top.name] = total
    return sizes


def write_cache_sizes(data_dir: str):
    """Housekeeping: <data>/work/cache-sizes.json, {"time": epoch seconds, "folders": {folder: bytes}},
    replaced at once (cache.replacing) so the metrics never read half a file."""
    sizes = cache_sizes(os.path.join(data_dir, "cache"))
    path = os.path.join(data_dir, "work", CACHE_SIZES)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump({"time": round(time.time()), "folders": sizes}, f)


HOUSEKEEPING_FILE = "housekeeping.json"  # in the work folder: the last round of the housekeeping (metrics.py)
COVERAGE_FILE = "coverage.json"          # in the work folder: the area searched at least once (metrics.py)
CELL_DEG = 0.25                          # the cells of the searches per area in coverage.json


def _write_json(data_dir: str, name: str, value: Dict):
    """A file of the work folder replaced at once (cache.replacing), so the metrics never read half of it."""
    path = os.path.join(data_dir, "work", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump(value, f)


def coverage(jobs: "Jobs") -> Dict:
    """The coverage of the site's searches (docs/monitoring.md F17): the km² of the union of the
    outlines of all finished searches (status done; on the WGS84 ellipsoid, pyproj.Geod), and per cell
    of CELL_DEG degrees the number of those searches whose outline touches it, as [lat, lon of its
    south-west corner, searches] (no users: a count per cell only)."""
    import shapely
    from pyproj import Geod
    from shapely.geometry import box
    from shapely.geometry.polygon import orient
    db = jobs._db()
    try:
        texts = [row[0] for row in db.execute("SELECT area_outline FROM jobs WHERE status = 'done' AND "
                                              "area_outline IS NOT NULL")]
    finally:
        db.close()
    shapes, cells = [], {}
    for text in texts:
        try:
            shape = shapely.from_geojson(text)
        except Exception:  # not GeoJSON: left out
            continue
        if not shape.is_valid:
            shape = shapely.make_valid(shape)
        shape = shapely.union_all([part for part in shapely.get_parts(shape)
                                   if part.geom_type in ("Polygon", "MultiPolygon")])
        if shape.is_empty:
            continue
        shapes.append(shape)
        shapely.prepare(shape)
        west, south, east, north = shape.bounds
        for i in range(math.floor(south / CELL_DEG), math.floor(north / CELL_DEG) + 1):
            for j in range(math.floor(west / CELL_DEG), math.floor(east / CELL_DEG) + 1):
                if shape.intersects(box(j * CELL_DEG, i * CELL_DEG, (j + 1) * CELL_DEG, (i + 1) * CELL_DEG)):
                    cells[(i, j)] = cells.get((i, j), 0) + 1
    union = shapely.union_all(shapes) if shapes else None
    geod = Geod(ellps="WGS84")
    km2 = sum(abs(geod.geometry_area_perimeter(orient(part, 1.0))[0])
              for part in shapely.get_parts(union) if part.geom_type == "Polygon") / 1e6 if union is not None else 0.0
    return {"time": round(time.time()), "km2": km2,
            "cells": [[i * CELL_DEG, j * CELL_DEG, n] for (i, j), n in sorted(cells.items())]}


def kill_tree(pid: int):
    """Kill a process and every process it started (download pools, numba, GDAL helpers)."""
    import psutil
    try:
        parent = psutil.Process(pid)
        processes = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    for process in processes:
        with contextlib.suppress(psutil.NoSuchProcess):
            process.kill()
    psutil.wait_procs(processes, timeout=30)


class Scheduler:
    """The worker: starts the processes of the jobs, Limits.download_slots downloading and
    Limits.compute_slots computing jobs at a time."""

    def __init__(self, jobs: Jobs, worker_id: Optional[str] = None, limits: Optional[Limits] = None,
                 public: bool = False, warm_up: bool = False):
        self.jobs = jobs
        self.public = public  # the worker of the public site
        # Compile numba's kernels in a process of their own at the start (warmup.py): `findaline.py
        # worker` and `web` (warm_up_wanted); the tests leave it off
        self.warm_up = warm_up
        self.warming = None  # that process
        self.limits = limits or Limits.load(public)  # FINDALINE_LIMIT_* (none locally), for its processes too
        self.quick = None  # the process of the quick lane
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.slots = {"download": self.limits.download_slots, "compute": self.limits.compute_slots}
        self.running: Dict[str, List[Running]] = {phase: [] for phase in self.slots}  # the jobs of each phase
        self._memory: Optional[int] = None
        self._measured = False
        self.lock = threading.Lock()
        self.context = multiprocessing.get_context("spawn")  # the same on every OS
        self.stopped = threading.Event()
        self.beat = 0.0  # time of the last heartbeat

    @property
    def memory(self) -> Optional[int]:
        """The budget of a compute slot (search.slot_memory), with several: the memory free before any
        search, shared by the slots. Measured at the first use (the worker's start, _begin), so a
        scheduler that never runs (the public site's web process, whose settings may name the worker's
        slots for its metrics) imports no search code."""
        if not self._measured:
            self._measured = True
            if self.slots["compute"] > 1:
                import search
                self._memory = search.slot_memory(self.limits)
        return self._memory

    def start(self):
        """Run the worker in a thread of this process (findaline.py web)."""
        self._begin()
        threading.Thread(target=self._loop, daemon=True).start()

    def run(self):
        """Run the worker in this thread until stop() (findaline.py worker)."""
        self._begin()
        try:
            self._loop()
        finally:
            self.stop()

    def _begin(self):
        self.memory  # measured now, before any search
        self.jobs.register(self.worker_id)
        self.beat = time.time()
        self.jobs.interrupted()  # jobs of workers that are gone
        self._start_warm_up()

    def _start_warm_up(self):
        """The numba warm-up (warmup.warm_up) in a daemonic process, while jobs are claimed: the
        first search after a start (the public worker's numba cache is in a tmpfs) or after a
        change of the code finds the kernels compiled, or compiles fewer of them itself."""
        if self.warm_up and self.warming is None:
            import warmup
            self.warming = self.context.Process(target=warmup.warm_up, args=(self.jobs.data_dir,), daemon=True)
            self.warming.start()

    def housekeeping(self):
        """Clean the data folder up: temporary files of downloads killed while writing; events of
        jobs finished more than Limits.keep_events_days ago; answers of the quick lane nobody took;
        work folders of ended jobs (kept after an unexpected error) after KEEP_WORK_DAYS, and those
        of estimates and profiles (left by a killed quick lane) and of the warm-up after a day. Measures the cache by
        top-level folder (write_cache_sizes) and the coverage of the searches (COVERAGE_FILE), and
        writes what this round removed, when it ended and how long it took (HOUSEKEEPING_FILE), for
        the metrics."""
        started = time.monotonic()
        data = self.jobs.data_dir
        removed = dict.fromkeys(("parts", "events", "quick", "usage", "audit", "work"), 0)
        removed["parts"] = cache.remove_stale_parts(os.path.join(data, "cache"))
        write_cache_sizes(data)
        import audit
        removed["audit"] = audit.purge(data)  # events of the audit log older than audit.KEEP_DAYS
        if self.limits.keep_events_days:
            removed["events"] = self.jobs.forget_events(self.limits.keep_events_days)
        removed["quick"] = self.jobs.forget_quick()
        removed["usage"] = self.jobs.forget_usage()
        unfinished = {job["id"] for job in self.jobs.waiting_or_running()}
        removed["work"] = _remove_old(os.path.join(data, "work", "jobs"), KEEP_WORK_DAYS, keep=unfinished)
        for name in ("estimates", "profiles", "warmup"):  # warmup: warmup.FOLDER
            removed["work"] += _remove_old(os.path.join(data, "work", name), 1)
        try:
            _write_json(data, COVERAGE_FILE, coverage(self.jobs))
        except Exception:  # the statistics never stop the housekeeping
            import traceback
            print("coverage:", traceback.format_exc(), file=sys.stderr)
        _write_json(data, HOUSEKEEPING_FILE, {"time": round(time.time()), "seconds": time.monotonic() - started,
                                              "removed": removed})

    def _remove_folder(self, job_id: str):
        """The work folder of a job whose processes were killed (their memory-mapped grids are closed)."""
        shutil.rmtree(self.jobs.folder(job_id), ignore_errors=True)

    def stop(self):
        """Stop gracefully: kill the running phases, mark their jobs interrupted, give up the lease."""
        self.stopped.set()
        with self.lock:
            self._kill_all()
            self.jobs.unregister(self.worker_id)
            if self.warming is not None and self.warming.is_alive():
                kill_tree(self.warming.pid)  # its temporary folder: removed by the housekeeping after a day
                self.warming.join()

    def _kill_all(self):
        for phase in self.running:
            for running in list(self.running[phase]):
                self._kill(phase, running)
        if self.quick is not None:
            kill_tree(self.quick.pid)
            self.quick.join()
            self.quick = None
        self.jobs.interrupted(self.worker_id)

    def _loop(self):
        cleaned = 0.0
        while not self.stopped.wait(TICK):
            if time.time() - cleaned >= HOUSEKEEPING:  # in a thread: it walks the whole cache
                cleaned = time.time()
                threading.Thread(target=self.housekeeping, daemon=True).start()
            with self.lock:
                if self.stopped.is_set():
                    break
                self._heartbeat()
                self._check_quick()
                self._check()

    def _heartbeat(self):
        if time.time() - self.beat < HEARTBEAT:
            return
        if not self.jobs.heartbeat(self.worker_id):
            # The lease expired (the computer slept, the database was locked): another worker may
            # have failed our jobs already; stop them and start over
            self._kill_all()
            self.jobs.register(self.worker_id)
        self.beat = time.time()
        self.jobs.interrupted()  # jobs of other workers that are gone

    def _check_quick(self):
        """Keep the quick lane running: a new process after a crash or a task over the time limit."""
        if self.quick is not None:
            task = self.jobs.quick_running(self.worker_id)
            if not self.quick.is_alive():
                self.quick.join()
                self.quick = None
                if task:
                    self.jobs.quick_answer(task["id"], 500, "the worker of estimates and profiles stopped")
            elif task and self.limits.quick_seconds and time.time() - task["started"] > self.limits.quick_seconds:
                kill_tree(self.quick.pid)
                self.quick.join()
                self.quick = None
                self.jobs.quick_answer(task["id"], 504, f"time limit: stopped after {self.limits.quick_seconds:g} s")
        if self.quick is None:
            quick = self.context.Process(target=run_quick, daemon=True,
                                         args=(self.jobs.data_dir, self.worker_id, os.getpid(), self.limits,
                                               self.public, self.memory))
            quick.start()
            self.quick = quick  # only a started process: one read without the lock has its pid

    def _kill(self, phase: str, running: "Running"):
        """Kill the process tree of one running phase of a job and remove the job's work folder."""
        self.running[phase].remove(running)
        kill_tree(running.process.pid)
        running.process.join()
        self._remove_folder(running.job_id)

    def _check(self):
        every = [(phase, running) for phase, slots in self.running.items() for running in slots]
        for job_id in self.jobs.cancel_requested(running.job_id for _, running in every):
            for phase, running in every:
                if running.job_id == job_id:
                    self._kill(phase, running)
            self._remove_folder(job_id)
            self.jobs.set(job_id, "cancelled", when=ACTIVE + WAITING)
        for phase in self.running:
            for running in list(self.running[phase]):
                job_id, process, started, limit, what = running
                if limit and process.is_alive() and time.time() - started > limit:
                    self._kill(phase, running)
                    self.jobs.set(job_id, "failed", when=(PHASE_STATUS[phase],),
                                  error=f"time limit: {what} was stopped after {limit:g} s")
                    continue
                if process.is_alive():
                    continue
                process.join()
                self.running[phase].remove(running)
                # Ended without a word. Only the job's status of this phase tells that: a download
                # process sets "ready" and may take a moment to exit, while the job already computes;
                # a compute process downloads the orthophoto after "done" (the time limit may end it)
                self.jobs.set(job_id, "failed", when=(PHASE_STATUS[phase],),
                              error=f"the worker stopped (exit code {process.exitcode})")
        for phase, waiting, status in (("download", "queued", "downloading"), ("compute", "ready", "computing")):
            free = self.slots[phase] - self._occupied(phase)
            while free > 0:
                job = self.jobs.claim(waiting, status, self.worker_id)
                if not job:
                    break
                process = self.context.Process(target=run_phase, daemon=True,
                                               args=(self.jobs.data_dir, job["id"], phase, self.limits,
                                                     self.public, self.memory))
                process.start()
                osm = "osm" in json.loads(job["request"])  # an OSM extract: its own limit
                self.running[phase].append(Running(job["id"], process, time.time(),
                                                   self.limits.phase_seconds(phase, osm),
                                                   "the OSM extract job" if osm else f"the {phase} phase"))
                free -= 1

    def _occupied(self, phase: str) -> int:
        """The slots of a phase in use: its running processes, of the compute phase those whose job
        still computes (one query, Jobs.statuses). A compute process of a job done already downloads
        the orthophoto (run_phase, after "done") and holds no slot: the next job starts beside it.
        It keeps its time limit (the kill ends the download only: the job's status is guarded by
        `when`), is joined when it ends, and stop() kills it like the others; it holds its imports
        only (the lines are released before the orthophoto), nothing search.slot_memory has to
        reserve."""
        running = self.running[phase]
        if phase != "compute" or not running:
            return len(running)
        statuses = self.jobs.statuses(r.job_id for r in running)
        return sum(1 for r in running if statuses.get(r.job_id) == PHASE_STATUS[phase])


def warm_up_wanted() -> bool:
    """Whether the worker of `findaline.py worker` and `web` warms numba up at its start
    (Scheduler.warm_up): yes, unless FINDALINE_WARM_UP=0."""
    return os.environ.get("FINDALINE_WARM_UP", "").strip() != "0"


def warn_without_cgroup(root: Optional[str] = None) -> bool:
    """The public worker sizes tiles and threads from the limits of its container (search.cgroup_limits,
    cgroup v2 only): a warning on stderr when it finds none (cgroup v1, or no mem_limit / cpus).
    Whether it warned."""
    import search
    found = search.cgroup_limits(root)
    if found.memory is not None and found.cpus is not None:
        return False
    v2 = os.path.exists(os.path.join(root or search.CGROUP_ROOT, "cgroup.controllers"))
    print("WARNING: " + ("no memory or CPU limit of the container found (cgroup v2: memory.max, cpu.max)" if v2 else
                         "no cgroup v2 found (cgroup v1 is not read)") + ": tiles and threads are sized from the "
          "whole machine; run the worker in a container with mem_limit and cpus on a host with cgroup v2",
          file=sys.stderr, flush=True)
    return True


def main(argv: List[str]) -> int:
    """findaline.py worker: the worker of the web app as its own process."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="findaline.py worker",
        description="The worker of the web app: runs the queued searches (start the server with "
                    "`findaline.py web --no-worker`).")
    parser.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    parser.add_argument("--public", action="store_true",
                        help="the worker of the public site (`findaline.py web --public`): needs the same settings "
                             "(FINDALINE_PUBLIC_URL, FINDALINE_TRUSTED_PROXY, FINDALINE_CONTACT)")
    args = parser.parse_args(argv)
    if args.public:
        # The site's address and FINDALINE_CONTACT go into the User-Agent of the worker's requests
        # (cache.http_headers reads the environment, which the worker's processes inherit; a
        # Docker secret is put there too)
        public = PublicSettings.load()
        os.environ["FINDALINE_PUBLIC_URL"], os.environ["FINDALINE_CONTACT"] = public.public_url, public.contact
    data = cache.data_dir(args.data_dir)
    cache.check_layout(os.path.join(data, "cache"))
    scheduler = Scheduler(Jobs(data, public=args.public), public=args.public, warm_up=warm_up_wanted())
    if args.public:
        warn_without_cgroup()
        import search
        # The largest search must fit into one compute slot (with one slot: into the memory free now)
        warning = search.memory_warning(scheduler.limits, scheduler.memory)
        if warning:
            print(warning, file=sys.stderr, flush=True)
    # SIGTERM (docker stop, systemd) stops it like Ctrl+C: the running phases are killed and
    # their jobs marked interrupted (a tiled area resumes when it is started again)
    for name in ("SIGTERM", "SIGBREAK"):  # SIGBREAK: Ctrl+Break, or a service stopped on Windows
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: scheduler.stopped.set())
    print(f"Find-a-Line worker {scheduler.worker_id} is running on {data} (Ctrl+C to stop it)", flush=True)
    try:
        scheduler.run()
    except KeyboardInterrupt:
        pass
    return 0
