"""What the OPR layer (tnm.OprBlocks) knows of each lidar survey: USGS's table of surveys (WESM) as a cached listing,
and a record per survey with its year and its height unit, measured (the user's plan-v2: "undecided files are skipped
and named").

USGS's OPR DEMs are each survey's raster as it was delivered: its own CRS (State Plane in feet, UTM, Albers), pixels
of 0.25 to 3 m, heights in metres or in feet. The table's height unit is unreliable (gate 0: of the surveys it calls
"feet", the mosaics measured metres in 18 of 19), TNM dates every OPR product 1899-12-30, and a file's survey is
found only by WESM's `sourcedem_link` (a prefix of the file's URL; the work unit's folder fails for 13.5 % of files).

**WESM** (wesm_path: `<cache>/usa/sheet-index/wesm/WESM.csv`, about 2.3 MB, with its row in usa/index.sqlite) is
fetched through the app's HTTP path (servicecounts, a slot of its host, the User-Agent; a cached table is asked again
with its ETag, 304: nothing comes) and written atomically. A search fetches it only when none is cached
(ensure_wesm); a renewal over a layer that reads it (sources/renewal.py: a download pass or a country run once a row
holds the OPR layer, wave B-2; none does in B-1) and `cache update usa` (update.py) make it again when it is older
than WESM_MAX_AGE_DAYS (28, as the bucket's list of the 1 m files: renew_wesm), by the same rules as that list: one
process at a time (a lock file), a fetch that fails or is refused (no table, columns missing, fewer rows than the
cached table by more than WESM_MAX_DROP unless a fetch a day later agrees: wesm_refused.json) keeps the table there
was, writes wesm_failed.json and is not tried again within WESM_FAILED_RETRY_DAYS.

**A survey's record** (record_path: `<cache>/usa/sheet-index/opr-surveys/<work unit>.json`) is made when an index
answer naming the survey is first read and no record exists, made again when its WESM row's collect_end,
sourcedem_link, categories or method changed (fingerprint) or the unit rule's name changed (RULE). It holds the year
(collect_end's), the height unit and factor or "undecided", the pixel of the sampled files in metres (their pixel
in the CRS's unit times that unit in metres), their horizontal CRS and whether they lie on whole metres, when it was
made and from which files and windows. The unit's rule (make_record; gate B-1a's replay: docs/usa-data.md, "OPR
read by the app"): the headers of up to UNIT_WINDOWS of the answer's files of the survey spread by name, then up
to UNIT_WINDOWS windows of WINDOW_M on them, each file's windows at its highest ground by its own heights (its
smallest overview, when small) and at fixed points by turns (_windows_of), the first window that decides wins: the
file's heights read as metres, as feet and as US survey feet against the 1/3 arc-second DEM bilinearly on the
window's pixels (medians of the differences); decided when the wrong reading is off by more than DECIDE_M and more
than DECIDE_RATIO times the right one (plan-v2's rule), else the next window. A survey is read (readable) only
when its unit is decided, its sampled pixel is at most MAX_PIXEL_M, it is lidar (WESM's p_method; IfSAR never) and
its files have a projected CRS; else its record says why, its files give no item and a run names it once ("survey X
left out: ..."). Sampled files in two horizontal units (metres and feet; the foot and the US survey foot are one,
UNIT_REL_TOL) are not read. A record none of whose windows decided while a request failed is not written
(RuntimeError, or MeasurementNotReached when nothing answered): the failure is kept for a day in
`<work unit>.failed.json`, the survey's answers fail on the first and the second failed day, and the third failed
measurement in a row writes a "not read" record measured again RECORD_SKIP_DAYS later (survey_record: the rule as
built, the user's "Wait 3 days, then skip it" of 2026-11-27).

The web process never imports this module (tnm.OprIndex imports it when an answer is read)."""

import contextlib
import csv
import io
import json
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
import requests
from filelock import FileLock, Timeout
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window

import cache
import servicecounts

from .. import net
from ..indexes.cached import IndexUnavailable
from ..indexes.tilings import degree_tile_name
from ..layer import _clean
from ..readers.windows import OPR_FINER, OPR_MAX_PIXEL_M, UNIT_REL_TOL, _horizontal, _same_crs

OPR_TOP = "usa"
WESM_URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.csv"
# The columns the layer reads (the table has 28: docs/usa-data.md, "WESM")
WESM_COLUMNS = ("workunit", "project", "collect_end", "p_method", "dem_gsd_meters", "vert_crs", "sourcedem_link",
                "sourcedem_category", "onemeter_category")
WESM_MAX_AGE_DAYS = cache.TTL_DAYS["usgs-1m-index"]  # 28: renewed with the bucket's list of the 1 m files
WESM_FAILED_RETRY_DAYS = 1.0
WESM_MAX_DROP = 0.02      # a table with fewer rows than the cached one by more than this share is refused ...
WESM_REFUSED_DAYS = 1.0   # ... unless a fetch at least this many days later agrees with the refused count
WESM_LOCK_WAIT_S = 120

# The survey's record
# the unit rule's name: a record made by another rule is made again ("+units": a survey sampled in two horizontal
# units is not read, fix round 2; "units-1e-5": the foot and the US survey foot one unit, fix round 3)
RULE = "highest+fixed-5+units-1e-5"
UNIT_WINDOWS = 5    # windows at most
WINDOW_M = 200      # the side of a window
DECIDE_M = 3.0      # the wrong reading off by more than this ...
DECIDE_RATIO = 5.0  # ... and more than this many times the right one
MIN_VALID = 0.3     # a window with fewer valid pixels in both rasters gives no verdict
MAX_PIXEL_M = OPR_MAX_PIXEL_M  # the user's D4, "1 m or finer"; a pixel written as 3.2809 ft is 1.00002 m
FOOT, US_FOOT = 0.3048, 1200 / 3937
FINGERPRINT = ("collect_end", "sourcedem_link", "sourcedem_category", "onemeter_category", "p_method")


# WESM

def wesm_path(cache_dir: str, top: str = OPR_TOP) -> str:
    return os.path.join(cache_dir, top, "sheet-index", "wesm", "WESM.csv")


def _beside(cache_dir: str, name: str, top: str = OPR_TOP) -> str:
    return os.path.join(os.path.dirname(wesm_path(cache_dir, top)), name)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: str, data: Dict):
    tmp = net._part(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        print(f"{path} could not be written: {e}")


def _read_json(path: str) -> Optional[Dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse_wesm(text: str) -> List[Dict[str, str]]:
    """The table's rows; IndexUnavailable for a text that is no such table (columns missing, no rows)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in WESM_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise IndexUnavailable(f"WESM: not the table of surveys (no column {', '.join(missing)})")
    rows = [row for row in reader if row.get("workunit")]
    if not rows:
        raise IndexUnavailable("WESM: a table without rows")
    return rows


def _cached_rows(cache_dir: str, top: str = OPR_TOP) -> Optional[int]:
    try:
        return len(table(cache_dir, top).rows)
    except (OSError, IndexUnavailable):
        return None


def _wesm_refused_again(cache_dir: str, count: int, top: str = OPR_TOP) -> bool:
    """A table the row guard refuses: True when a refused fetch at least WESM_REFUSED_DAYS before counted as many rows
    (within WESM_MAX_DROP: the table did shrink), else False after recording this count (a record that agrees keeps
    its time)."""
    path = _beside(cache_dir, "wesm_refused.json", top)
    record = _read_json(path)
    try:
        at = datetime.fromisoformat(record["at"]) if record else None
        agrees = record is not None and abs(count - int(record["rows"])) <= WESM_MAX_DROP * int(record["rows"])
    except (KeyError, TypeError, ValueError):
        at, agrees = None, False
    if agrees and at is not None and at.tzinfo is not None:
        return (_now_utc() - at).total_seconds() >= WESM_REFUSED_DAYS * 86400
    _write_json(path, {"rows": count, "at": _now_utc().isoformat(timespec="seconds")})
    return False


def fetch_wesm(cache_dir: str, top: str = OPR_TOP, url: Optional[str] = None) -> str:
    """Fetch the table into the cache: "made" (written) or "same" (the server's 304 for the cached table's ETag: only
    its check time changes). Asked again net.RETRIES times while it fails (backoff); IndexUnavailable when it
    cannot be had or is refused (parse_wesm; fewer rows than the cached table by more than WESM_MAX_DROP: _wesm_refused_again),
    the cached table kept."""
    url = url or WESM_URL
    path = wesm_path(cache_dir, top)
    row = cache.info(cache_dir, path) if os.path.exists(path) else None
    headers = dict(cache.http_headers())
    if row and row.get("etag"):
        headers["If-None-Match"] = row["etag"]
    response, error = None, None
    for attempt in range(net.RETRIES):
        try:
            with net.host_slot(cache_dir, url):
                net.rate_turn(url)
                response = servicecounts.get(url, headers=headers, timeout=120)
            if response.status_code in (200, 304):
                break
            error = f"HTTP {response.status_code}"
        except requests.RequestException as e:
            error = cache.clean_error(e)
        response = None
        if attempt < net.RETRIES - 1:
            net._sleep(attempt)
    if response is None:
        raise IndexUnavailable(f"WESM could not be fetched ({error})")
    if response.status_code == 304:
        cache.record(cache_dir, path, url=url, etag=row.get("etag"), last_modified=row.get("last_modified"))
        return "same"
    rows = parse_wesm(response.content.decode("utf-8-sig", "replace"))
    before = _cached_rows(cache_dir, top)
    if before and len(rows) < (1 - WESM_MAX_DROP) * before and not _wesm_refused_again(cache_dir, len(rows), top):
        raise IndexUnavailable(f"WESM has {len(rows)} rows, the cached table {before}: refused (a fetch at least a day "
                               f"later that agrees is taken)")
    tmp = net._part(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(response.content)
        os.replace(tmp, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise IndexUnavailable(f"WESM could not be written ({path}): {e}") from e
    cache.record(cache_dir, path, url=url, etag=response.headers.get("ETag"),
                 last_modified=response.headers.get("Last-Modified"))
    with contextlib.suppress(OSError):
        os.remove(_beside(cache_dir, "wesm_refused.json", top))
    return "made"


def wesm_age_days(cache_dir: str, top: str = OPR_TOP) -> float:
    """Days since the cached table was fetched or checked (its row); infinite without one."""
    path = wesm_path(cache_dir, top)
    row = cache.info(cache_dir, path) if os.path.exists(path) else None
    return cache.age_days(row["checked_at"]) if row else float("inf")


def _failed_recently(cache_dir: str, top: str = OPR_TOP) -> Optional[Dict]:
    record = _read_json(_beside(cache_dir, "wesm_failed.json", top))
    try:
        at = datetime.fromisoformat(record["at"]) if record else None
    except (KeyError, TypeError, ValueError):
        return None
    if at is None or at.tzinfo is None:
        return None
    if 0 <= (_now_utc() - at).total_seconds() < WESM_FAILED_RETRY_DAYS * 86400:
        return {"at": at, "error": str(record.get("error", ""))}
    return None


def _lock(cache_dir: str, top: str = OPR_TOP) -> FileLock:
    return FileLock(f"{net._locks(cache_dir, 'renewal')}/{top}-wesm.lock")


def renew_wesm(cache_dir: str, say: Callable[[str], None] = print, force: bool = False, top: str = OPR_TOP) -> str:
    """The table made again when it is older than WESM_MAX_AGE_DAYS (force: whatever its age; a failure less than a
    day old still waits): "made", "same" (the server's 304), "kept" (fresh enough, made by another process, a recent
    failure) or "failed" (the line said why; the cached table stays). Never raises for a failed fetch."""
    age = wesm_age_days(cache_dir, top)
    if age <= WESM_MAX_AGE_DAYS and not force:
        return "kept"
    failed = _failed_recently(cache_dir, top)
    if failed is not None:
        say(f"USGS's table of surveys (WESM) is not fetched again before a day has passed since its last try failed "
            f"({failed['at']:%Y-%m-%d %H:%M} UTC: {failed['error'][:200]})")
        return "kept"
    try:
        with _lock(cache_dir, top).acquire(timeout=WESM_LOCK_WAIT_S):
            if wesm_age_days(cache_dir, top) < age and not force:
                return "kept"  # another process fetched it meanwhile
            try:
                done = fetch_wesm(cache_dir, top)
            except Exception as e:  # noqa: BLE001 (any failure: the table there was stays)
                _write_json(_beside(cache_dir, "wesm_failed.json", top),
                            {"at": _now_utc().isoformat(timespec="seconds"), "error": cache.clean_error(e)[:500]})
                say(f"USGS's table of surveys (WESM) could not be fetched ({cache.clean_error(e)[:300]}): the table "
                    f"there is is used; tried again after {WESM_FAILED_RETRY_DAYS:g} day")
                return "failed"
    except Timeout:
        say("Another process is fetching USGS's table of surveys (WESM): the table there is is used")
        return "kept"
    with contextlib.suppress(OSError):
        os.remove(_beside(cache_dir, "wesm_failed.json", top))
    say(f"USGS's table of surveys (WESM): {'fetched' if done == 'made' else 'unchanged (checked)'}")
    return done


def ensure_wesm(cache_dir: str, top: str = OPR_TOP):
    """A search's WESM: fetched only when none is cached (under the lock, so two searches fetch it once);
    IndexUnavailable when it cannot be."""
    path = wesm_path(cache_dir, top)
    if os.path.exists(path):
        return
    try:
        with _lock(cache_dir, top).acquire(timeout=WESM_LOCK_WAIT_S):
            if not os.path.exists(path):
                fetch_wesm(cache_dir, top)
    except Timeout:
        raise IndexUnavailable("another process is fetching USGS's table of surveys (WESM)")


class Wesm:
    """The table's rows by work unit, and a file's survey by its URL: the row whose sourcedem_link (a folder of the
    bucket) holds the file, the longest of them (rows found through the project's folder, so a URL is matched
    against a few links, not all 3,300)."""

    def __init__(self, rows: List[Dict[str, str]]):
        self.rows = {row["workunit"]: row for row in rows}
        self._links: Dict[str, List[Tuple[str, Dict]]] = {}
        for row in rows:
            key = link_key(row.get("sourcedem_link") or "")
            if key:
                self._links.setdefault(_project(key), []).append((key, row))
        for links in self._links.values():
            links.sort(key=lambda t: -len(t[0]))

    def survey_of(self, url: str) -> Optional[Dict[str, str]]:
        key = url_key(url)
        for link, row in self._links.get(_project(key), ()):
            if key.startswith(link + "/"):
                return row
        return None


def link_key(link: str) -> str:
    """A sourcedem_link as a folder of the bucket (StagedProducts/Elevation/OPR/Projects/<project>/<work unit>)."""
    link = link.split("prefix=", 1)[-1] if "prefix=" in link else re.sub(r"^https?://[^/]+/", "", link)
    return link.strip().strip("/")


def url_key(url: str) -> str:
    return re.sub(r"^https?://[^/]+/", "", url)


def _project(key: str) -> str:
    """The project's folder of a bucket path (the part after Projects/), else the path's first three parts."""
    parts = key.split("/")
    if "Projects" in parts:
        k = parts.index("Projects")
        return "/".join(parts[:k + 2])
    return "/".join(parts[:3])


_tables: Dict[str, Tuple[tuple, Wesm]] = {}
_tables_lock = threading.Lock()


def table(cache_dir: str, top: str = OPR_TOP) -> Wesm:
    """The cached table (read once per process while the file stays the same); OSError without one."""
    path = wesm_path(cache_dir, top)
    st = os.stat(path)
    stamp = (st.st_mtime_ns, st.st_size)
    with _tables_lock:
        known = _tables.get(path)
        if known and known[0] == stamp:
            return known[1]
    with open(path, encoding="utf-8-sig", newline="") as f:
        found = Wesm(parse_wesm(f.read()))
    with _tables_lock:
        _tables[path] = (stamp, found)
    return found


# The survey's record

def record_path(cache_dir: str, workunit: str, top: str = OPR_TOP) -> str:
    return os.path.join(cache_dir, top, "sheet-index", "opr-surveys", re.sub(r"[^\w.-]", "_", workunit) + ".json")


def fingerprint(row: Dict[str, str]) -> Dict[str, str]:
    return {k: (row.get(k) or "") for k in FINGERPRINT}


def collect_date(row: Dict[str, str]) -> str:
    """collect_end as YYYY-MM-DD ("2016/05/28" in the table); "" when it has none."""
    m = re.match(r"(\d{4})\D?(\d{1,2})?\D?(\d{1,2})?", (row.get("collect_end") or "").strip())
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2) or 1):02d}-{int(m.group(3) or 1):02d}"


def read_record(path: str) -> Optional[Dict]:
    return _read_json(path)


def survey_record(cache_dir: str, row: Dict[str, str], urls: Sequence[str], reference: Callable[[float, float], str],
                  top: str = OPR_TOP) -> Dict:
    """The record of a survey: the cached one while its WESM row's fingerprint and the rule are the same (and, for a
    survey skipped after failed measurements, until its retry date), else made now from these of its files
    (make_record) and written atomically (under the record's lock: two processes make it once).

    A measurement that fails is remembered in <work unit>.failed.json with the count of failed measurements in a row
    and not repeated for RECORD_FAILED_RETRY_DAYS; the first and the second failure raise (tnm.SurveyNotRead: its
    answers fail, nothing cached is touched). The RECORD_FAILED_TIMES-th failure in a row (each at least a day after
    the one before, no success between, none more than RECORD_SKIP_DAYS after the one before) writes a "not read"
    record at once (the user's decision of 2026-11-27, "Wait 3 days, then skip it"), so the survey's tiles are
    unavailable for about two days: its reason names the last error and the date from which it is measured again,
    RECORD_SKIP_DAYS later (the OPR answers' update_ttl_days, one constant); from then on its answers are read
    without it, as for any survey not read. The first read of an answer naming it after that date (a search's, a
    renewal's, `cache update`'s) measures once: a success writes its record (its items return), a failure the "not
    read" record for another RECORD_SKIP_DAYS at once, without raising. A measurement in which nothing answered and
    nothing could be connected to, while WESM's host cannot be connected to either (MeasurementNotReached and
    _wesm_host_reached: this machine's network), is remembered for the day but not counted; at a retry after the skip
    it keeps the skip and tries again a day later."""
    path = record_path(cache_dir, row["workunit"], top)

    def current(record):
        return (record is not None and record.get("wesm") == fingerprint(row) and record.get("rule") == RULE
                and "headers" in record  # records of before the headers were kept (fix round 1) are made again
                and not _retry_due(record))
    record = read_record(path)
    if current(record):
        return record
    with net.tile_lock(cache_dir, path):
        record = read_record(path)
        if current(record):
            return record
        old = record
        skipped = old is not None and old.get("retry_after") is not None  # a retry after the skip
        failed = None if skipped else _record_failed_recently(path)
        if failed is not None:  # the code review's F5: a measurement that failed is not repeated for a day
            raise RuntimeError(f"its measurement failed at {failed['at']:%Y-%m-%d %H:%M} UTC ({failed['error'][:150]});"
                               f" tried again after {RECORD_FAILED_RETRY_DAYS:g} day")
        try:
            record = make_record(cache_dir, row, urls, reference)
        except Exception as e:  # noqa: BLE001 (any failure: remembered, counted, the survey left out this time)
            error = cache.clean_error(e)[:500]
            # not counted only when nothing answered and WESM's host cannot be connected to either (the fourth code
            # review's finding 1: a survey's own unreachable file counts)
            not_counted = isinstance(e, MeasurementNotReached) and not _wesm_host_reached()
            if skipped:
                if not_counted:  # this machine offline at the retry: the skip stays, tried again a day later
                    record = _retry_later(old, row, timedelta(days=RECORD_FAILED_RETRY_DAYS))
                else:
                    record = _skipped_record(row, error, None)
                _write_json(path, record)
                return record
            count, counted_at = _failed_count(path)
            if not not_counted:
                count, counted_at = count + 1, _now_utc().isoformat(timespec="seconds")
            if count >= RECORD_FAILED_TIMES:
                record = _skipped_record(row, error, count)
                _write_json(path, record)
                with contextlib.suppress(OSError):
                    os.remove(_failed_path(path))
                return record
            # "at": the last try (the day's wait); "counted_at": the last counted failure (the count's gap)
            _write_json(_failed_path(path), {"at": _now_utc().isoformat(timespec="seconds"), "error": error,
                                             "count": count, "counted_at": counted_at})
            raise
        _write_json(path, record)
        with contextlib.suppress(OSError):
            os.remove(_failed_path(path))
    return record


RECORD_FAILED_RETRY_DAYS = 1.0  # a survey whose measurement failed is not measured again within this (as the list's)
RECORD_FAILED_TIMES = 3  # failed measurements in a row (a day apart) before the survey is skipped (the user's 3 days)
RECORD_SKIP_DAYS = cache.TTL_DAYS["usgs-1m-index"]  # 28: a skipped survey measured again after (tnm.OprBlocks' TTL)


class MeasurementNotReached(RuntimeError):
    """make_record could not decide, no request of the measurement got an answer, and every request that failed
    found no connection to its host (net.connect_failed). survey_record then probes WESM's host (_wesm_host_reached):
    only when that finds no connection either is the failure this machine's network and not counted towards
    RECORD_FAILED_TIMES; otherwise it counts (a survey's own file on a host this machine cannot reach while the network
    works). Left: USGS's bucket (the host of WESM, the reference DEM and every recorded OPR file) unreachable from
    this machine for weeks counts no failure, and nothing of OPR can be read then anyway."""


def _wesm_host_reached() -> bool:
    """One HEAD to WESM's URL through the app's counting (servicecounts): True when a connection was made, whatever
    the answer (a status, a TLS failure after connecting, a read timeout); False when none could be."""
    try:
        servicecounts.call(WESM_URL, lambda: net.session(WESM_URL).head(
            WESM_URL, timeout=2 * net.CONNECT_TIMEOUT_S, headers=cache.http_headers(), allow_redirects=False),
            read=False)
        return True
    except requests.RequestException as e:
        return not net.connect_failed(e)


def _failed_count(path: str) -> Tuple[int, Optional[str]]:
    """The failed measurements in a row before this one (failed.json's count; a file without it: 1) and the time of
    the last counted one ("counted_at"; a file without it: "at"); (0, None) when that failure lies more than
    RECORD_SKIP_DAYS back or cannot be read (three in a row are never made of failures months apart: the fourth code
    review; a not-counted try between does not move the time: its review 4b)."""
    before = _read_json(_failed_path(path))
    if not before:
        return 0, None
    try:
        count = int(before.get("count", 1))
        when = before.get("counted_at") or before["at"]
        if not count or not when:
            return 0, None
        at = datetime.fromisoformat(when)
        if at.tzinfo is None or (_now_utc() - at).total_seconds() > RECORD_SKIP_DAYS * 86400:
            return 0, None
        return count, when
    except (KeyError, TypeError, ValueError):
        return 0, None


def _retry_later(record: Dict, row: Dict[str, str], wait: timedelta) -> Dict:
    """A skipped survey's record kept, its retry date (and the reason's date) wait from now, and its WESM fingerprint
    and RULE those of now, so a retry set off by a changed row or rule waits too (review 4b: it was measured at every
    read)."""
    retry = (_now_utc() + wait).replace(microsecond=0)
    reason = re.sub(r"measured again from \d{4}-\d{2}-\d{2}$", f"measured again from {retry:%Y-%m-%d}",
                    record.get("reason") or "")
    return dict(record, retry_after=retry.isoformat(), reason=reason, wesm=fingerprint(row), rule=RULE)


def _retry_due(record: Dict) -> bool:
    """Whether a skipped survey's record (retry_after) has reached its retry date."""
    when = record.get("retry_after")
    if not when:
        return False
    try:
        return _now_utc() >= datetime.fromisoformat(when)
    except (TypeError, ValueError):
        return True


def _skipped_record(row: Dict[str, str], error: str, count: Optional[int]) -> Dict:
    """The "not read" record of a survey whose measurement kept failing (count failures in a row; None: a retry after
    the skip failed), measured again from RECORD_SKIP_DAYS on."""
    now = _now_utc()
    retry = (now + timedelta(days=RECORD_SKIP_DAYS)).replace(microsecond=0)
    record = _new_record(row)
    record["retry_after"] = retry.isoformat()
    done = f"on {count} days" if count is not None else "again after its skip"
    record["reason"] = (f"could not be measured {done}, last: {error[:200]}; measured again from "
                        f"{retry:%Y-%m-%d}")
    return record


def _failed_path(path: str) -> str:
    """A record's failure beside it (<work unit>.failed.json: {"at", "error", "count"}: the failed measurements in a
    row, as the bucket list's failed.json)."""
    return path[:-len(".json")] + ".failed.json"


def _record_failed_recently(path: str) -> Optional[Dict]:
    found = _read_json(_failed_path(path))
    try:
        at = datetime.fromisoformat(found["at"]) if found else None
    except (KeyError, TypeError, ValueError):
        return None
    if at is None or at.tzinfo is None:
        return None
    if 0 <= (_now_utc() - at).total_seconds() < RECORD_FAILED_RETRY_DAYS * 86400:
        return {"at": at, "error": str(found.get("error", ""))}
    return None


def readable(record: Optional[Dict]) -> bool:
    return bool(record) and record.get("read") is True


def method_of(pixel_m: float, same_crs: bool, on_metres: bool) -> Optional[str]:
    """The method a file's pixel takes onto 1 m blocks (the user's N4 and D4; windows.OPR_METHODS): copied on the
    block's pixels, averaged below 0.75 m, cubic from 0.75 to MAX_PIXEL_M, None above."""
    if pixel_m > MAX_PIXEL_M:
        return None
    if pixel_m < OPR_FINER:
        return "average"
    if same_crs and on_metres and abs(pixel_m - 1.0) <= 1e-6:
        return "copy"
    return "cubic"


def units_of(record: Dict) -> Tuple[float, ...]:
    """The linear units (metres per unit) of the horizontal CRSs of a survey's sampled files, each once
    (_distinct_units: the foot and the US survey foot one unit), ascending: the reader leaves out a file in another
    one (windows._opr_file), a heuristic guard of the survey's one height factor against a survey mixing metres and
    feet (a mosaic in metres with tiles in feet: gate 0 met one; the code review's S2). A survey mixing State Plane
    CRSs in "ft" and in "ftUS" is read as before fix round 2: its height factor is measured, and every file is placed
    by its own CRS. A survey in feet horizontally with heights in metres, or the reverse, is told by its windows, not
    by this."""
    return tuple(sorted(_distinct_units(h["unit"] for h in record.get("headers") or () if h.get("unit"))))


def _distinct_units(units) -> List[float]:
    """Linear units (metres per unit), each once, compared as the reader's guard compares them (windows._opr_file:
    relative UNIT_REL_TOL, so the foot and the US survey foot, 2e-6 apart, are one unit, and so is a header storing a
    rounded 0.3048006), the largest of each first (metres before feet)."""
    found: List[float] = []
    for u in sorted(units, reverse=True):
        if not any(math.isclose(u, f, rel_tol=UNIT_REL_TOL) for f in found):
            found.append(u)
    return found


def unit_class_texts(units) -> List[str]:
    """The sampled units as the key's token writes them (tnm.opr_items): one text per class of units the guard takes
    as one (UNIT_REL_TOL), whatever the sample and its history: "1" for metres, "0.3048" for the foot and the US survey
    foot alike (and a header's rounded 0.3048006), else the unit to 5 significant digits; sorted. A survey sampled in
    ft, in ftUS or in both gets the same units text. Its height factor, also in the token (x0.3048 or x0.3048006096),
    is the first deciding window's file's foot (make_record), so two caches whose records decided on files of the
    other foot may still name a mixed-feet survey's blocks differently (and differ by 2 ppm, 8 mm at 4,000 m)."""
    texts = set()
    for u in units:
        if math.isclose(u, 1.0, rel_tol=UNIT_REL_TOL):
            texts.add("1")
        elif math.isclose(u, FOOT, rel_tol=UNIT_REL_TOL) or math.isclose(u, US_FOOT, rel_tol=UNIT_REL_TOL):
            texts.add("0.3048")
        else:
            texts.add(f"{u:.5g}")
    return sorted(texts)


def _unit_name(unit: float) -> str:
    """A linear unit in words, plural (metres, feet, US survey feet)."""
    for value, name in ((1.0, "metres"), (FOOT, "feet"), (US_FOOT, "US survey feet")):
        if math.isclose(unit, value, rel_tol=1e-9):
            return name
    return f"units of {unit:.10g} m"


def methods_for(record: Dict, crs: str) -> Tuple[str, ...]:
    """The methods a readable survey's sampled headers take onto blocks in crs (a UTM zone), sorted: each sampled
    file's own (its pixel, its CRS compared with the zone's by _same_crs, never as text, whether it lies on whole
    metres). The reader still takes every file's method from its own header (windows.compose_opr); these go into
    the blocks' key (the token of tnm.opr_items)."""
    found = set()
    for h in record.get("headers") or ():
        same = bool(h.get("crs")) and _same_crs(rio.crs.CRS.from_wkt(h["crs"]), crs)
        method = method_of(h["pixel_m"], same, bool(h.get("on_metres")))
        if method:
            found.add(method)
    return tuple(sorted(found))


def _new_record(row: Dict[str, str]) -> Dict:
    """A survey's record before anything is measured: "not read", no reason yet."""
    return {"workunit": row["workunit"], "project": row.get("project", ""), "collect_end": collect_date(row),
            "year": int(collect_date(row)[:4]) if collect_date(row) else 0, "wesm": fingerprint(row), "rule": RULE,
            "made_at": cache.now_iso(), "read": False, "unit": None, "factor": None, "pixel_m": None, "crs": None,
            "on_metres": False, "files": [], "windows": [], "reason": "",
            # in every record, those left out early too (not lidar, cut at 4 GB, no readable file): survey_record
            # takes a record without it as one of before fix round 1 and makes it again (the second code review's N1)
            "headers": []}


def make_record(cache_dir: str, row: Dict[str, str], urls: Sequence[str],
                reference: Callable[[float, float], str]) -> Dict:
    """A survey's record, measured on its files (urls, sorted by name; the rule: the module's docstring). Requests
    that fail are left out of the verdict (a window that cannot be read gives none); a survey none of whose windows
    could be read is undecided this time, and its record is made again only when its WESM row changes or by hand
    (the record deleted). A failed request with nothing decided raises: MeasurementNotReached when none of the
    failed requests found a connection, else RuntimeError."""
    record = _new_record(row)
    method = (row.get("p_method") or "").lower()
    if "ifsar" in method or "lidar" not in method:
        record["reason"] = f"not lidar ({row.get('p_method') or 'no method'})"
        return record
    from ..readers import ranges
    urls = sorted(urls, key=lambda u: u.rsplit("/", 1)[-1])
    picks = _spread(len(urls), UNIT_WINDOWS)
    files: Dict[str, Dict] = {}
    import pyproj
    failures = (requests.RequestException, RuntimeError, rio.errors.RasterioError, net.Unreachable)
    # Errors that come back the same every time (a CRS PROJ cannot transform: rasterio's CRSError is a ValueError,
    # pyproj's a RuntimeError): a window or a file "not read" with the reason, never a failed request (the code
    # review's F5: such a survey was measured again at every answer read)
    deterministic = (rio.errors.CRSError, ValueError, pyproj.exceptions.ProjError)
    failed: List[str] = []  # requests that failed: a record made without them is not written (raised below)
    connected = []  # per failed request: whether a connection was made (net.connect_failed tells it apart)
    answered = 0  # requests (a header, a window with its reference) that got an answer, whatever it said
    with _Files(cache_dir) as opened:
        # the headers of every sampled file (the pixel and the CRS that count are those of all of them), then the
        # windows until one decides
        for url in dict.fromkeys(urls[i] for i in picks):
            try:
                files[url] = _file_facts(opened, url)
                answered += 1
            except ranges.Missing:
                answered += 1
                files[url] = {"error": "not there (404)"}
            except deterministic as e:
                answered += 1
                files[url] = {"error": f"its CRS cannot be used ({cache.clean_error(e)[:150]})"}
            except failures as e:
                files[url] = {"error": cache.clean_error(e)[:200]}
                failed.append(files[url]["error"])
                connected.append(not (isinstance(e, net.Unreachable) or net.connect_failed(e)))
        units = _distinct_units(f["unit"] for f in files.values() if not f.get("error") and f.get("unit"))
        windows: Dict[str, List] = {}
        for k, i in enumerate(picks):
            if len(units) > 1:
                break  # one height factor cannot serve both: not read, nothing measured (below)
            url = urls[i]
            if files[url].get("error"):
                continue
            try:
                if url not in windows:
                    windows[url] = _windows_of(opened, opened.get(url), files[url]["pixel_m"], picks.count(i))
                nth = picks[:k].count(i)
                if nth >= len(windows[url]):
                    continue
                verdict = _verdict(opened, url, windows[url][nth], reference)
                answered += 1
            except deterministic as e:
                verdict = {"file": url.rsplit("/", 1)[-1], "verdict": "not read",
                           "error": f"its CRS cannot be used ({cache.clean_error(e)[:150]})", "lasting": True}
            except failures as e:
                verdict = {"file": url.rsplit("/", 1)[-1], "verdict": "not read", "error": cache.clean_error(e)[:200]}
                failed.append(verdict["error"])
                connected.append(not (isinstance(e, net.Unreachable) or net.connect_failed(e)))
            record["windows"].append(verdict)
            if verdict.get("verdict") in ("metre", "foot"):
                break
    decided = next((w for w in record["windows"] if w.get("verdict") in ("metre", "foot")), None)
    record["files"] = [u.rsplit("/", 1)[-1] for u in files]
    # the verdicts no further request can change come before the raise for a failed one (the third code review's
    # finding 1): a sampled file cut at 4 GB, sampled files in two units (another header can only add a unit)
    cut = [u.rsplit("/", 1)[-1] for u, f in files.items() if f.get("cut")]
    if cut:
        record["reason"] = (f"its file {cut[0]} was cut at 4 GB (a classic TIFF at the format's limit: its last tiles "
                            f"are missing)")
        return record
    if failed and decided is None and len(units) <= 1:
        # never a survey left out for good because of a request that failed: no record, made again next time
        if not answered and not any(connected):  # nothing answered, no connection: survey_record probes WESM's host
            raise MeasurementNotReached(f"{len(failed)} requests failed, no connection ({failed[0]})")
        raise RuntimeError(f"{len(failed)} requests failed ({failed[0]})")
    good = [f for f in files.values() if not f.get("error")]
    if not good:
        errors = [f["error"] for f in files.values() if f.get("error")]
        record["reason"] = f"no file could be read ({errors[0] if errors else 'no file'})"
        return record
    record["pixel_m"] = max(f["pixel_m"] for f in good)
    record["crs"] = good[0]["crs"]
    # each sampled header's own facts: the methods its survey's files take onto a zone's blocks (methods_for) and
    # the linear unit of its horizontal CRS (units_of: the reader's guard of the survey's one factor)
    record["headers"] = [{"file": u.rsplit("/", 1)[-1], "pixel_m": f["pixel_m"], "crs": f["crs"],
                          "on_metres": f["on_metres"], "unit": f["unit"]} for u, f in files.items()
                         if not f.get("error")]
    record["on_metres"] = all(f["on_metres"] for f in good)
    if len(units) > 1:
        # a survey whose sampled files are in two horizontal units (a mosaic in metres beside tiles in feet): its one
        # measured height factor would read one of them 3.28 times off (fix round 2, the unit guard's limit)
        record["reason"] = (f"its files are in {' and in '.join(_unit_name(u) for u in units)}, one height factor "
                            f"cannot serve both")
        return record
    if decided is None:
        record["unit"] = "undecided"
        lasting = [w["error"] for w in record["windows"] if w.get("lasting")]
        record["reason"] = (f"its height unit could not be told ({lasting[0]})" if lasting
                            else "its height unit could not be told")
        return record
    if decided["verdict"] == "metre":
        record["unit"], record["factor"] = "metre", 1.0
    else:
        foot = files[next(u for u in files if u.rsplit("/", 1)[-1] == decided["file"])]["foot"]
        record["unit"], record["factor"] = ("US survey foot", US_FOOT) if foot == US_FOOT else ("foot", FOOT)
    if record["pixel_m"] > MAX_PIXEL_M:
        record["reason"] = f"its pixel is {record['pixel_m']:.3f} m (coarser than {MAX_PIXEL_M:g} m)"
        return record
    record["read"] = True
    return record


def _spread(n: int, k: int) -> List[int]:
    """k indices spread over n files by name, the middle first when k is 1; repeats (more windows on a file) when
    there are fewer files."""
    if n >= k:
        return [round(i * (n - 1) / (k - 1)) for i in range(k)] if k > 1 else [n // 2]
    return [i % n for i in range(k)]


class _Files:
    """The remote files of a record, each opened once (ranges.open_remote inside net._gdal_http, net.gdal_errors
    checked; every open and read under a slot of its host, held for that request only), closed in reverse order."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.stack = contextlib.ExitStack()
        self.open: Dict[str, Tuple] = {}

    def __enter__(self):
        self.stack.__enter__()
        self.stack.enter_context(net._gdal_http())
        return self

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)

    def get(self, url: str):
        """(dataset, RangeFile) of url; ranges.Missing for a 404 (the caller's error), RuntimeError for a failed
        open."""
        from ..readers import ranges
        if url not in self.open:
            with net.host_slot(self.cache_dir, url), net.gdal_errors() as errors:
                src, file = self.stack.enter_context(ranges.open_remote(url, tiff_only=True))
            if errors or file.error is not None:
                raise RuntimeError(f"could not open {url.rsplit('/', 1)[-1]}: "
                                   f"{cache.clean_error(file.error or '; '.join(errors))}")
            self.open[url] = (src, file, url)
        return self.open[url]


def _read_part(opened: _Files, entry, window: Window, out_shape=None) -> np.ndarray:
    """A window of an open file as float32, its nodata and values below VALID_MIN as NaN; RuntimeError when GDAL
    could not complete the read."""
    src, file, url = entry
    with net.host_slot(opened.cache_dir, url), net.gdal_errors() as errors:
        band = src.read(1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest)
    if errors or file.error is not None:
        raise RuntimeError(f"could not read: {cache.clean_error(file.error or '; '.join(errors))}")
    return _clean(band.astype(np.float32).filled(np.nan))


def pixel_of(crs, transform) -> Optional[float]:
    """A file's pixel in metres: its pixel in the CRS's unit times that unit in metres (US survey foot and foot both
    occur); None for a geographic or missing CRS and for a geotransform with rotation terms (its pixel is not
    abs(a): the code review's F8)."""
    if crs is None or not crs.is_projected or transform.b or transform.d:
        return None
    return abs(transform.a) * crs.linear_units_factor[1]


def _foot_of(crs) -> float:
    """The foot a file's heights in feet are taken in: its vertical CRS's when it names one, else its horizontal
    unit's when that is a foot, else the US survey foot (they differ by 2 ppm: 8 mm at 4,000 m)."""
    try:
        import pyproj
        parsed = pyproj.CRS.from_wkt(crs.to_wkt())
        parts = parsed.sub_crs_list or [parsed]
        for part in reversed(parts):
            for axis in part.axis_info:
                if math.isclose(axis.unit_conversion_factor, FOOT, rel_tol=1e-9):
                    return FOOT
                if math.isclose(axis.unit_conversion_factor, US_FOOT, rel_tol=1e-9):
                    return US_FOOT
    except Exception:  # noqa: BLE001 (a CRS pyproj cannot read: the default)
        pass
    return US_FOOT


CLASSIC_LIMIT = 2 ** 32  # the most bytes a classic TIFF (not BigTIFF) can hold
CUT_MARGIN = 64 * 1024   # a classic TIFF this close to CLASSIC_LIMIT may have been cut there


def cut_at_4gb(entry) -> bool:
    """Whether a file was cut at 4 GB: a classic TIFF of at least CLASSIC_LIMIT - CUT_MARGIN bytes whose last
    full-resolution tile has no offset (the writer stopped there; GDAL reads such tiles as nodata without an error,
    so the blocks there would be "missing" without a word). Gate B-1a: 15 of the 357 surveys have a file of
    4,294,96x,xxx bytes; MI_MuskegonCo_2013's tiles have offsets down to about the middle of the image, none after."""
    src, file, _ = entry
    first = file.chunks.get(0, b"")[:4]
    if first not in (b"II*\x00", b"MM\x00*") or file.size < CLASSIC_LIMIT - CUT_MARGIN:
        return False
    bh, bw = src.block_shapes[0]
    last = f"{(src.width - 1) // bw}_{(src.height - 1) // bh}"
    return int(src.get_tag_item(f"BLOCK_OFFSET_{last}", "TIFF", bidx=1) or 0) == 0


def _file_facts(opened: _Files, url: str) -> Dict:
    """A sampled file's header facts: its pixel in metres, its horizontal CRS, whether it lies on whole metres at
    1 m, the foot of its heights if they are in feet; an error for a file without a projected CRS; "cut" for a
    file cut at 4 GB (cut_at_4gb)."""
    entry = opened.get(url)
    src = entry[0]
    if src.transform.b or src.transform.d:
        return {"error": "its geotransform is rotated"}
    p = pixel_of(src.crs, src.transform)
    if p is None:
        return {"error": "no projected CRS"}
    if cut_at_4gb(entry):
        return {"error": "cut", "cut": True}
    t = src.transform
    on_metres = (abs(p - 1.0) <= 1e-6 and abs(t.c - round(t.c)) < 0.01 and abs(t.f - round(t.f)) < 0.01
                 and src.crs.linear_units_factor[1] == 1.0)
    return {"pixel_m": p, "crs": _horizontal(src.crs).to_wkt(), "on_metres": on_metres, "foot": _foot_of(src.crs),
            "unit": src.crs.linear_units_factor[1]}


OVERVIEW_MAX_PX = 1024  # the largest smallest overview read for the highest ground (a side); else fixed windows only
FIXED = ((0.5, 0.5), (0.25, 0.25), (0.75, 0.75), (0.25, 0.75), (0.75, 0.25))  # a file's fixed windows (centres)


def _windows_of(opened: _Files, entry, p: float, k: int) -> List[Tuple[int, int, int]]:
    """A file's windows of WINDOW_M in the order they are tried, at most k: its highest ground (_highest) and its
    fixed points (FIXED: the centre, then the quarters) by turns, as (col, row, side) in its pixels; a fixed window
    within 1 km of one taken already is left out. The fixed points catch a file whose overview has data where the
    file has none (a mosaic cut at 4 GB: MI_MuskegonCo_2013, gate B-1a) and a file with no small overview."""
    src = entry[0]
    side = min(max(8, math.ceil(WINDOW_M / p)), src.width, src.height)
    high = _highest(opened, entry, p, side, k)
    fixed = [(int((src.width - side) * fx), int((src.height - side) * fy), side) for fx, fy in FIXED]
    out: List[Tuple[int, int, int]] = []
    for pair in zip(high + [None] * len(fixed), fixed):
        for at in pair:
            if at is not None and not any(math.hypot((at[0] - c) * p, (at[1] - r) * p) < 1000 for c, r, _ in out):
                out.append(at)
    return out[:k]


def _highest(opened: _Files, entry, p: float, side: int, k: int) -> List[Tuple[int, int, int]]:
    """The k highest windows of side pixels of a file by its own heights, where it has data, at least 1 km apart: its
    smallest overview read whole when it is at most OVERVIEW_MAX_PX a side (none: a file without overviews, or a
    mosaic whose smallest is larger), scanned in cells of the window's size (the median of each cell, cells with
    90 % data), as (col, row, side) in the file's pixels. The highest raw value is the highest ground whatever the
    unit, and a window's verdict is the clearer the higher the ground (the wrong reading is off by 0.695 times the
    height)."""
    src = entry[0]
    overviews = src.overviews(1)
    if not overviews:
        return []
    f = overviews[-1]
    shape = (max(1, src.height // f), max(1, src.width // f))
    if max(shape) > OVERVIEW_MAX_PX:
        return []
    small = _read_part(opened, entry, Window(0, 0, src.width, src.height), shape)
    sy, sx = src.height / shape[0], src.width / shape[1]
    s = max(1, round(side / sx))
    ny, nx = max(1, shape[0] // s), max(1, shape[1] // s)
    cells = small[:ny * s, :nx * s].reshape(ny, min(s, shape[0]), nx, min(s, shape[1])).transpose(0, 2, 1, 3)
    cells = cells.reshape(ny, nx, -1)
    enough = np.isfinite(cells).mean(axis=2) >= 0.9
    if not enough.any():
        return []
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells: left out below
            medians = np.where(enough, np.nanmedian(cells, axis=2), -np.inf)
    out: List[Tuple[int, int, int]] = []
    for flat in np.argsort(medians, axis=None)[::-1]:
        y, x = divmod(int(flat), nx)
        if not enough[y, x]:
            break
        col, row = int(min(x * s * sx, src.width - side)), int(min(y * s * sy, src.height - side))
        if any(math.hypot((col - c) * p, (row - r) * p) < 1000 for c, r, _ in out):
            continue
        out.append((col, row, side))
        if len(out) >= k:
            break
    return out


def _verdict(opened: _Files, url: str, at: Tuple[int, int, int], reference: Callable[[float, float], str]) -> Dict:
    """One window's verdict: the file's heights against the 1/3 arc-second DEM on the window's pixels."""
    from ..readers import ranges
    entry = opened.get(url)
    src = entry[0]
    col, row, side = at
    window = Window(col, row, side, side)
    opr = _read_part(opened, entry, window)
    out = {"file": url.rsplit("/", 1)[-1], "at": [col, row, side]}
    if not np.isfinite(opr).any():
        return dict(out, verdict="no data")
    transform = src.window_transform(window)
    (lon,), (lat,) = rio.warp.transform(src.crs, "EPSG:4269", [transform.c + side * transform.a / 2],
                                        [transform.f + side * transform.e / 2])
    try:
        ref = _reference_on(opened, reference(lat, lon), src.crs, transform, (side, side))
    except ranges.Missing:
        return dict(out, verdict="no reference")
    both = np.isfinite(opr) & np.isfinite(ref)
    out["valid"] = round(float(both.mean()), 3)
    if both.mean() < MIN_VALID:
        return dict(out, verdict="no data")
    meds = {"metre": float(np.median(opr[both] - ref[both])), "foot": float(np.median(opr[both] * FOOT - ref[both])),
            "US survey foot": float(np.median(opr[both] * US_FOOT - ref[both]))}
    m, ft = abs(meds["metre"]), abs(meds["foot"])
    right, wrong = min(m, ft), max(m, ft)
    out["medians"] = {k: round(v, 3) for k, v in meds.items()}
    unit = "metre" if m < ft else "foot"
    out["verdict"] = unit if wrong > DECIDE_M and wrong > DECIDE_RATIO * right else "undecided"
    return out


def _reference_on(opened: _Files, url: str, crs, transform, shape) -> np.ndarray:
    """The 1/3 arc-second DEM bilinearly on a window's pixels (the file's window under them and 2 pixels more)."""
    entry = opened.get(url)
    src = entry[0]
    h, w = shape
    bounds = (transform.c, transform.f + h * transform.e, transform.c + w * transform.a, transform.f)
    left, bottom, right, top = transform_bounds(crs, src.crs, *bounds, densify_pts=21)
    t = src.transform
    cols = sorted(((left - t.c) / t.a, (right - t.c) / t.a))
    rows = sorted(((top - t.f) / t.e, (bottom - t.f) / t.e))
    c1, c2 = max(math.floor(cols[0]) - 2, 0), min(math.ceil(cols[1]) + 2, src.width)
    r1, r2 = max(math.floor(rows[0]) - 2, 0), min(math.ceil(rows[1]) + 2, src.height)
    out = np.full(shape, np.nan, dtype=np.float32)
    if r1 >= r2 or c1 >= c2:
        return out
    window = Window(c1, r1, c2 - c1, r2 - r1)
    band = _read_part(opened, entry, window)
    reproject(band, out, src_transform=src.window_transform(window), src_crs=src.crs, dst_transform=transform,
              dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear, num_threads=1)
    return out


def reference_url(layer) -> Callable[[float, float], str]:
    """The URL of the 1/3 arc-second DEM's file at a point, from its layer (DegreeBlocks: url(name of the 1° tile))."""
    return lambda lat, lon: layer.url(degree_tile_name(math.floor(lon * 10), math.floor(lat * 10)))


# Naming once per process

_named: set = set()
_named_lock = threading.Lock()


def name_once(key: str, text: str):
    """Print text the first time key is met in this process (a run names a survey or a file left out once)."""
    with _named_lock:
        if key in _named:
            return
        _named.add(key)
    print(text, flush=True)
