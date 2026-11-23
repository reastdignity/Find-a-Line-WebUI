"""The files of the USA's 1 m DEM that are in USGS's bucket but not in the TNM index: the list of them (make_unlisted)
and the list as the 1 m layer reads it (unlisted_in_tile, merged into the index's answers by tnm.UnlistedIndex).

The 1 m layer (tnm.Usgs1mBlocks) finds its files through the TNM Access API, but USGS's bucket holds more 1 m files
than the API lists (1,410 of 127,289 in the projects of the lower 48 on 2026-11-22; in Utah they covered every square
that looked like a hole). make_unlisted makes the list of those: (1) every `.tif` under
StagedProducts/Elevation/1m/Projects/<project>/TIFF/ of the bucket (ListObjectsV2, about 990 pages), (2) the names
the TNM index lists over the USA and its territories (REGIONS, a box split in four while it holds more than
SPLIT_ABOVE products, so no page is asked at a deep offset), (3) the bucket's files whose name the index does not
list, checked against two guards before anything else is asked (too many of them, or the index listing clearly
fewer files than the list before: an index that answered too little; a real shrink is taken when a listing at
least a day later agrees with the refused one, refused.json), (4) the UTM zone of each (from the name,
USGS_1M_<zone>_x..y..; for USGS_one_meter_x..y.. and USGS_1m_x..y.., which carry none, from the project's listed
files when they lie in one zone and the tile then lands in the project's box, else from the file's own header: one
small read, HEADER_READS at most), and its survey year (the project's folders, else the year its listed files
carry, else the upload year), (5) written atomically to <cache>/usa/sheet-index/bucket1m/unlisted.json with a row
in usa/index.sqlite (its age), each file as the item a TNM answer holds (tnm.tile_item: name, url, crs, extent,
year; published = the upload time in the bucket; in a block it ranks as any 1 m file: the user's decision of
2026-11-23). A file whose header answers definitely (the server's 404 or 403, a complete answer that is no TIFF, no
NAD83 / UTM CRS, bounds off its name) is left out and named; a header answer cut short is asked again. Any other
failing step raises IndexUnavailable and leaves the list there was. Each of the three parts asks REQUESTS_AT_ONCE
requests at a time (the bucket a project per task, the index a box per task, the headers a file per task); every
request carries the app's User-Agent, holds a slot of its host and takes its rate turn (a 429 or 503 of the index
backs off longer, another 4xx is not asked again); each part has a budget of requests (PageBudget), and the first
failure, or a Ctrl+C, stops the others.

Where no list is cached (or the cached one cannot be used), the copy shipped with the code is read (SHIPPED, made
by tools/usa_unlisted.py with this function; FINDALINE_USA_UNLISTED_SHIPPED=off leaves it out: the tests). The
renewal of the list (part A-2 of the USA's wave A) calls make_unlisted. The web process never imports this module.
"""

import collections
import contextlib
import json
import os
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import rasterio as rio
import requests
from rasterio.warp import transform_bounds

import cache
import osm
import servicecounts

from .. import net
from ..indexes.cached import INDEX_MARGIN_DEG, IndexUnavailable
from ..indexes.s3listing import MAX_KEYS, PageBudget, S3Object, common_prefixes, list_objects
from ..readers.windows import _forget, _same_crs
from .tnm import TILE_ZONE, TNM_API, _survey_year, folder_year, tile_extent, tile_item, usgs_1m_item

BUCKET = "https://prd-tnm.s3.amazonaws.com"
PROJECTS = "StagedProducts/Elevation/1m/Projects/"
DATASET = "Digital Elevation Model (DEM) 1 meter"
TOP = "usa"  # the top folder of the 1 m layer (usa/3dep-1m)
SHIPPED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "catalogue",
                       "usa_unlisted_1m.json")
SHIPPED_ENV = "FINDALINE_USA_UNLISTED_SHIPPED"  # "off": no shipped copy (tests/conftest.py)
# The boxes (west, south, east, north) the TNM index is asked over: the lower 48, Alaska (no 1 m DEM in 2026-11:
# one small answer each), Hawaii, Puerto Rico and the Virgin Islands, Guam and the Northern Marianas, American Samoa.
# The bucket's projects of Hawaii and Puerto Rico must lie inside, or all their files would look unlisted
REGIONS: Tuple[Tuple[float, float, float, float], ...] = (
    (-125.0, 24.0, -66.0, 50.0),
    (-180.0, 51.0, -129.0, 72.0),
    (172.0, 51.0, 180.0, 54.0),
    (-161.0, 18.5, -154.5, 22.5),
    (-68.0, 17.5, -64.5, 18.6),
    (144.5, 13.0, 146.0, 20.6),
    (-171.2, -14.7, -168.0, -11.0),
)
TNM_PAGE = 500     # products a page (the API's most)
SPLIT_ABOVE = 2500  # a box holding more products is asked as its four quarters (at most 5 pages a box)
MIN_SPLIT_DEG = 0.25
# Requests at a time in each part: within the app's 8 connections a host (net.HOST_SLOTS), each still under a slot
# of its host and its rate turn (the planner's measurement at 4, 2026-11-23: the bucket in 193 s against 10 min one
# at a time, the 386 header reads in 43 s; gate 0b listed the index at 4 in 343 s)
REQUESTS_AT_ONCE = 4
BUCKET_PAGES = 3000  # 989 on 2026-11-22
TNM_PAGES = 3000     # 415 on 2026-11-22
# Times a page of the index is asked while it fails (backoff about 1, 2, 4, 8, 16 s): a renewal of 400 pages met one
# 500 asked three times in a row (2026-11-23, the same page answered at once a minute later)
TNM_RETRIES = 6
HEADER_READS = 1000  # 302 on 2026-11-22: room for the bucket to triple its names without a zone the index lacks
# More of the bucket's files looking unlisted than this share is an index that answered too little (a box empty for
# a moment): an error, checked before any header is read (1.1 % on 2026-11-22)
MAX_UNLISTED_SHARE = 0.05
# The index listing fewer files than the list before recorded (its counts.listed: the cached list, else the shipped
# copy) by more than this share is an index that answered too little, also when the unlisted files stay under
# MAX_UNLISTED_SHARE: 2 % is 2,535 of 126,767 files; the index is not known to shrink (it kept listing the 2013
# projects beside their successors). A real shrink heals by itself: a refused listing records its count (refused.json
# beside the list), and a listing at least REFUSED_RECORD_DAYS later whose count agrees with it within this share is
# accepted (two listings a day apart saw the same smaller index); allow_drop accepts it at once (tools/usa_unlisted.py
# --allow-drop, for the shipped copy or with --cached for a cache's own list)
MAX_LISTED_DROP = 0.02
REFUSED_RECORD_DAYS = 1.0
PROJECT_MARGIN_DEG = 0.25  # a tile given its project's one zone lands within the project's listed box grown by this
# A file's bounds within this of its name's 10 km square: the standard tiles reach 6 m beyond it, older ones up to
# about 400 m (MS_Laurel_2014's x22y372: 297 m west; checked 2026-11-22), some cover only part of it (NM_NorthCentral)
HEADER_MARGIN_M = 1000
# A header read GDAL fails is a definite answer (the file left out and named) only for the server's own 404 or 403,
# the HTTP status as GDAL reports it ("HTTP response code: 403"; never a "403 ms" or an x40y404 of curl's texts), or a
# complete answer that is no TIFF. GDAL says the same (TIFFReadDirectory, "not recognized as") for a file that is no
# TIFF and for a header whose answer was cut short, so that is decided from the file's first bytes, asked by a small
# range request of our own (_first_bytes). Anything else (a cut answer, a timeout, a broken connection, a 5xx after
# GDAL's own retries) may pass: asked again, then the list stops
REFUSED_STATUS = re.compile(r"(?<![\w.])HTTP response code: (40[34])(?!\d)")
WAIT_POLL_S = 0.5  # how often a part run several at a time looks up from its wait (a Ctrl+C is seen then)
RECHECK_S = 300            # how often a process looks whether the cached list was renewed (by another process)


def unlisted_path(cache_dir: str, top: str = TOP) -> str:
    """The cached list of the unlisted files."""
    return os.path.join(cache_dir, top, "sheet-index", "bucket1m", "unlisted.json")


def project_of(url: str) -> str:
    """The project folder of a 1 m file's URL (or key)."""
    return url.split("/Projects/", 1)[-1].split("/", 1)[0] if "/Projects/" in url else ""


def _all(task: Callable, args: Sequence, at_once: int, stop: Optional[threading.Event]) -> list:
    """task(arg) of every arg, at_once at a time, the results in the order of args. The first failure of a task, or
    any exception in the calling thread while it waits (a KeyboardInterrupt: Ctrl+C), sets stop (the budgets of the
    others then refuse their next request), drops the tasks not yet started and is raised once the requests in
    flight have ended."""
    if at_once <= 1 or len(args) <= 1:
        return [task(arg) for arg in args]
    pool = ThreadPoolExecutor(max_workers=at_once, thread_name_prefix="unlisted")
    finished = False
    try:
        futures = [pool.submit(task, arg) for arg in args]
        while True:
            _, pending = wait(futures, timeout=WAIT_POLL_S, return_when=FIRST_EXCEPTION)
            failed = next((f for f in futures if f.done() and not f.cancelled() and f.exception() is not None), None)
            if failed is not None:
                raise failed.exception()
            if not pending:
                break
        results = [f.result() for f in futures]
        finished = True
        return results
    finally:
        if not finished and stop is not None:
            stop.set()
        pool.shutdown(wait=True, cancel_futures=True)


# The bucket

def bucket_files(cache_dir: Optional[str], bucket: str = BUCKET, budget: Optional[PageBudget] = None,
                 projects: Optional[Sequence[str]] = None, at_once: int = 1) -> List[S3Object]:
    """Every .tif key under <project>/TIFF/ of the bucket's 1 m projects (all, or those named), in S3's order of the
    projects and their keys; the projects listed at_once at a time."""
    budget = budget or PageBudget("USGS's bucket (1 m DEM)", BUCKET_PAGES)
    folders = [folder for folder in common_prefixes(bucket, PROJECTS, "/", cache_dir, budget)
               if projects is None or folder[len(PROJECTS):].rstrip("/") in projects]

    def one(folder):
        return [obj for obj in list_objects(bucket, folder + "TIFF/", MAX_KEYS, cache_dir, budget)
                if obj.key.lower().endswith(".tif")]
    return [obj for found in _all(one, folders, at_once, budget.stop) for obj in found]


# The TNM index

def _tnm_page(cache_dir: Optional[str], api: str, dataset: str, box: Tuple[float, float, float, float],
              offset: int, budget: PageBudget) -> Dict:
    """One page of the TNM index's products over a box; slow or failed answers asked again (TNM_RETRIES), a 429 or a
    503 (the server asks us to slow down) after a longer pause, as net._get does (net._sleep(attempt + 3)); another
    4xx is IndexUnavailable at once (asking again would not change it)."""
    params = {"datasets": dataset, "max": TNM_PAGE, "offset": offset, "bbox": ",".join(f"{v:g}" for v in box)}
    for attempt in range(TNM_RETRIES):
        budget.take()
        slow_down = False
        try:
            net.rate_turn(api)
            slot = net.host_slot(cache_dir, api) if cache_dir else contextlib.nullcontext()
            with slot:
                response = servicecounts.get(api, timeout=120, headers=cache.http_headers(), params=params)
            budget.add(len(response.content or b""))
            slow_down = response.status_code in (429, 503)
            if 400 <= response.status_code < 500 and not slow_down:
                raise IndexUnavailable(f"TNM API: HTTP {response.status_code} {response.text[:200]}".strip())
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, dict) or not isinstance(page.get("items") or [], list):
                raise ValueError("not an answer of products")
            return page
        except IndexUnavailable:
            raise
        except (requests.RequestException, ValueError) as e:
            if attempt == TNM_RETRIES - 1:
                raise IndexUnavailable(f"TNM API: {cache.clean_error(e)}") from e
            net._sleep(attempt + 3 if slow_down else attempt)
    raise AssertionError("unreachable")


def tnm_listed(cache_dir: Optional[str], api: str = TNM_API, dataset: str = DATASET,
               regions: Sequence[Tuple[float, float, float, float]] = REGIONS,
               budget: Optional[PageBudget] = None, at_once: int = 1) -> Dict[str, Dict]:
    """Every product of the TNM index's dataset over the boxes, by its download URL; the boxes asked at_once at a
    time. A box whose first page says it holds more than SPLIT_ABOVE is asked again as its four quarters (the first
    page's products kept), so no page lies deep. (The quarters' totals are not checked against the box's: on
    2026-11-23 one of 48 splits had its quarters say 104 fewer than the box, 4,171 of 4,275, the API's double
    counting not adding up across boxes; fix round 2, N3.)

    The API counts some products twice in its `total`, and pages over that count: on 2026-11-23 a box saying 572 gave
    500 items of 250 distinct URLs at offset 0 and 72 more at offset 500 (a file listed as two products), and two
    of 151 boxes gave a page short by one or ten; the pages always reached `total`. So the next page starts after
    what came (offset += the items' count, repeats included: pages overlap, never skip), a page shorter than the
    total promises is asked once more and the two are joined, and completeness is the distinct URLs, never `total`.
    A page that comes back empty, also when asked again, before `total` is reached is a dropped page:
    IndexUnavailable."""
    budget = budget or PageBudget("the TNM index (1 m DEM)", TNM_PAGES)
    found: Dict[str, Dict] = {}
    lock = threading.Lock()

    def keep(items):
        with lock:
            for product in items:
                url = product.get("downloadURL") if isinstance(product, dict) else None
                if url:
                    found.setdefault(url, {"downloadURL": url, "boundingBox": product.get("boundingBox"),
                                           "publicationDate": product.get("publicationDate")})

    def one(box) -> list:
        """The box's products kept; the quarters to ask instead, if any."""
        page, offset = _tnm_page(cache_dir, api, dataset, box, 0, budget), 0
        west, south, east, north = box
        if (page.get("total") or 0) > SPLIT_ABOVE and east - west > MIN_SPLIT_DEG:
            keep(page.get("items") or [])
            mid_x, mid_y = (west + east) / 2, (south + north) / 2
            return [(west, south, mid_x, mid_y), (mid_x, south, east, mid_y),
                    (west, mid_y, mid_x, north), (mid_x, mid_y, east, north)]
        while True:
            items, total = page.get("items") or [], page.get("total") or 0
            if len(items) < min(TNM_PAGE, total - offset):
                again = _tnm_page(cache_dir, api, dataset, box, offset, budget).get("items") or []
                keep(again)
                items = again if len(again) > len(items) else items
            keep(page.get("items") or [])
            if not items:
                if offset < total:
                    raise IndexUnavailable(f"TNM API: an empty page at offset {offset} of {total} in the box "
                                           f"{','.join(f'{v:g}' for v in box)} (a dropped page)")
                return []
            offset += len(items)
            if offset >= total:
                return []
            page = _tnm_page(cache_dir, api, dataset, box, offset, budget)

    if at_once <= 1:
        boxes = list(regions)
        while boxes:
            boxes[0:1] = one(boxes[0])
        return found
    pool = ThreadPoolExecutor(max_workers=at_once, thread_name_prefix="unlisted-tnm")
    finished = False
    try:  # as _all: a failure, or a Ctrl+C in this thread, stops the boxes not started
        pending = {pool.submit(one, box) for box in regions}
        while pending:
            done, pending = wait(pending, timeout=WAIT_POLL_S, return_when=FIRST_COMPLETED)
            for future in done:
                if future.exception() is not None:
                    raise future.exception()
                pending |= {pool.submit(one, box) for box in future.result()}
        finished = True
    finally:
        if not finished and budget.stop is not None:
            budget.stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
    return found


# The zone of a name without one

def header_zone(url: str, extent: Sequence[float], cache_dir: Optional[str]) -> Optional[int]:
    """The UTM zone of a remote 1 m file from its own header (one small read through GDAL's /vsicurl/, inside
    net._gdal_http, its errors seen through net.gdal_errors, holding a slot of the host): the zone z whose NAD83 /
    UTM (EPSG:269zz) the file's CRS is (windows._same_crs, as the reader will test it), the file's bounds meeting
    the name's 10 km square and within HEADER_MARGIN_M of it. None for a definite answer: the server's own 404 or 403
    (REFUSED_STATUS), a complete answer that is no TIFF (_first_bytes), no CRS, no NAD83 / UTM zone, bounds off the
    square. A failure that may pass (an answer cut short, a timeout, a broken connection, a 5xx) is forgotten by
    GDAL's cache of ranges and asked again (net.RETRIES), then raises IndexUnavailable (the list is then not made).
    Each attempt takes its rate turn (net.rate_turn)."""
    found = None
    slot = net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    with slot, net._gdal_http():
        for attempt in range(net.RETRIES):
            problem = None
            with servicecounts.request(url) as counted:
                try:
                    net.rate_turn(url)
                    with net.gdal_errors() as errors:
                        src = rio.open(net._remote(url))
                    with src:
                        found = (src.crs, tuple(src.bounds))
                    if errors:
                        raise rio.errors.RasterioIOError("; ".join(dict.fromkeys(errors)))
                except rio.errors.RasterioIOError as e:
                    _forget(url)
                    status = REFUSED_STATUS.search(str(e))
                    if status:
                        counted.outcome = "not_found" if status.group(1) == "404" else "other"
                        return None
                    counted.outcome = "other"
                    problem = e
            if problem is None:
                break
            if _first_bytes(url) in ("gone", "not a TIFF"):
                return None
            if attempt == net.RETRIES - 1:
                raise IndexUnavailable(f"the header of {url.rsplit('/', 1)[-1]}: "
                                       f"{cache.clean_error(problem)}") from problem
            net._sleep(attempt)
    crs, (left, bottom, right, top) = found
    if crs is None:
        return None
    for zone in range(1, 24):
        if _same_crs(crs, f"EPSG:{26900 + zone}"):
            m = HEADER_MARGIN_M
            inside = (left >= extent[0] - m and bottom >= extent[1] - m and right <= extent[2] + m
                      and top <= extent[3] + m)
            meets = left < extent[2] and right > extent[0] and bottom < extent[3] and top > extent[1]
            return zone if inside and meets else None
    return None


def _first_bytes(url: str) -> Optional[str]:
    """What a remote file's first 8 bytes say, asked by one small range request of our own through net
    (readers.ranges.get_range: our User-Agent, a rate turn, counted, asked again while it fails): "TIFF", "not a TIFF"
    (a complete answer whose bytes are no TIFF's magic), "gone" (404 or 403), or None (no complete answer: it may
    pass). Decided from what came, not from GDAL's message, which is the same for a file that is no TIFF and for a
    header whose answer was cut short."""
    from ..readers import TIFF_MAGIC, ranges
    if not re.match(r"https?://", url):
        return None
    try:
        body, _ = ranges.get_range(url, 0, 7)
    except ranges.Missing:
        return "gone"
    except RuntimeError as e:
        return "gone" if re.match(r"HTTP 403 ", str(e)) else None
    return "TIFF" if body[:4] in TIFF_MAGIC else "not a TIFF"


def _in_box(zone: int, extent: Sequence[float], box: Sequence[float]) -> bool:
    """Whether the centre of a tile, taken in a zone, lies in a WGS84 box grown by PROJECT_MARGIN_DEG."""
    x, y = rio.warp.transform(f"EPSG:{26900 + zone}", "EPSG:4326", [(extent[0] + extent[2]) / 2],
                              [(extent[1] + extent[3]) / 2])
    m = PROJECT_MARGIN_DEG
    return box[0] - m <= x[0] <= box[2] + m and box[1] - m <= y[0] <= box[3] + m


def unlisted_objects(objects: Sequence[S3Object], listed: Dict[str, Dict]) -> List[S3Object]:
    """The bucket's files whose name the index (its products by URL) does not list, in their order."""
    names = {url.rsplit("/", 1)[-1] for url in listed}
    return [obj for obj in objects if obj.key.rsplit("/", 1)[-1] not in names]


def _sibling_year(years: collections.Counter) -> int:
    """The year a project's listed files carry: the most frequent, of two as frequent the newer."""
    return max(years.items(), key=lambda kv: (kv[1], kv[0]))[0]


def unlisted_from(objects: Sequence[S3Object], listed: Dict[str, Dict], header: Callable[[str, list], Optional[int]],
                  bucket: str = BUCKET, at_once: int = 1,
                  stop: Optional[threading.Event] = None) -> Tuple[List[Dict], List[str], Dict[str, int], List[str]]:
    """The bucket's files (objects) whose name the index (listed: its products by URL) does not list, each as an item
    (tnm.tile_item, published = its upload time), sorted by URL; the names left out (no x..y.. in the name, or no
    zone found); counts (by how the zone and the year were found, and bytes); the projects whose files took their
    upload year. header(url, extent) gives a zone from the file; those reads go at_once at a time (stop: as _all).

    The year: the one the project's folders name (tnm.folder_year); else the one the project's listed files carry
    (the most frequent: ND_Lidar_Phase10's listed files 2024, its unlisted ones uploaded in 2026); only a project
    without a listed file keeps the upload year."""
    unlisted = unlisted_objects(objects, listed)
    # The zones and the box of the listed files of the projects that need them (names without a zone), and the years
    # of the listed files of the projects whose folders name no year
    wanted = {project_of(obj.key) for obj in unlisted if not TILE_ZONE.match(obj.key.rsplit("/", 1)[-1])}
    yearless = {project_of(obj.key) for obj in unlisted if folder_year(obj.key) is None}
    zones: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    years: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    boxes: Dict[str, List[float]] = {}
    for url, product in listed.items():
        project = project_of(url)
        if project in yearless:
            years[project][_survey_year(url, product.get("publicationDate") or "")] += 1
        if project not in wanted:
            continue
        item = usgs_1m_item(product)
        box = product.get("boundingBox") or {}
        if item is None or not all(k in box for k in ("minX", "minY", "maxX", "maxY")):
            continue
        zones[project][int(item["crs"].split(":")[1]) - 26900] += 1
        b = boxes.setdefault(project, [box["minX"], box["minY"], box["maxX"], box["maxY"]])
        boxes[project] = [min(b[0], box["minX"]), min(b[1], box["minY"]), max(b[2], box["maxX"]),
                          max(b[3], box["maxY"])]
    # The zone of each file: from its name or its project here, the header reads then at once
    zoned, reads = [], []
    for obj in unlisted:
        name = obj.key.rsplit("/", 1)[-1]
        url = f"{bucket.rstrip('/')}/{obj.key}"
        extent = tile_extent(name)
        zone, how = None, None
        if extent is not None:
            named = TILE_ZONE.match(name)
            project = project_of(obj.key)
            if named:
                zone, how = int(named.group(1)), "zone_in_name"
            elif len(zones.get(project, ())) == 1 and _in_box(next(iter(zones[project])), extent, boxes[project]):
                zone, how = next(iter(zones[project])), "zone_from_project"
            else:
                how = "zone_from_header"
                zone = len(reads)  # the position of its read, until the reads are done
                reads.append((url, extent))
        zoned.append((obj, name, url, zone, how))
    read = _all(lambda r: header(*r), reads, at_once, stop)
    items, left_out, upload_projects = [], [], set()
    counts = collections.Counter()
    for obj, name, url, zone, how in zoned:
        if how == "zone_from_header":
            zone = read[zone]
        if zone is None:
            left_out.append(name)
            continue
        counts[how] += 1
        counts["bytes"] += obj.size
        year = None
        if folder_year(obj.key) is None:
            project = project_of(obj.key)
            if years.get(project):
                year = _sibling_year(years[project])
                counts["year_from_siblings"] += 1
            else:
                counts["year_from_upload"] += 1
                upload_projects.add(project)
        items.append(tile_item(url, zone, obj.last_modified, year))
    items.sort(key=lambda item: item["url"])
    return items, sorted(left_out), dict(counts), sorted(upload_projects)


# Making the list

def refused_path(cache_dir: str, top: str = TOP) -> str:
    """The record of a listing the count guard refused (beside the cached list): {"listed": count, "at": ISO time}."""
    return os.path.join(cache_dir, top, "sheet-index", "bucket1m", "refused.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_refused(cache_dir: str) -> Optional[Dict]:
    """The record of a refused listing; None without one, or for one that cannot be read (ignored)."""
    try:
        with open(refused_path(cache_dir), encoding="utf-8") as f:
            record = json.load(f)
        listed, at = record["listed"], datetime.fromisoformat(record["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(listed, int) or listed <= 0 or at.tzinfo is None:
        return None
    return {"listed": listed, "at": at}


def _agrees(count: int, record: Dict) -> bool:
    return abs(count - record["listed"]) <= MAX_LISTED_DROP * record["listed"]


def _refused_again(cache_dir: str, count: int) -> Optional[Dict]:
    """A listing the count guard refuses: the record that confirms it when it is at least REFUSED_RECORD_DAYS old
    and agrees with count within MAX_LISTED_DROP (then the shrink is taken as real), else None after recording this
    listing (a record that agrees keeps its time; another, or none, is written now, atomically)."""
    record = _read_refused(cache_dir)
    if record is not None and _agrees(count, record):
        if (_utc_now() - record["at"]).total_seconds() >= REFUSED_RECORD_DAYS * 86400:
            return record
        return None
    path = refused_path(cache_dir)
    tmp = net._part(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"listed": count, "at": _utc_now().isoformat(timespec="seconds")}, f)
        os.replace(tmp, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        print(f"The record of the refused listing could not be written ({path}): {e}")
    return None


def previous_listed(cache_dir: str, top: str = TOP) -> Optional[int]:
    """The index's count of files the list before recorded (counts.listed): the cached list's, else the shipped
    copy's (unless SHIPPED_ENV is off); None without a usable one."""
    paths = [unlisted_path(cache_dir, top)] + ([] if _shipped_off() else [SHIPPED])
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                listed = json.load(f)["counts"]["listed"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(listed, int) and listed > 0:
            return listed
    return None


def make_unlisted(cache_dir: str, out: Optional[str] = None, bucket: str = BUCKET, api: str = TNM_API,
                  dataset: str = DATASET, regions: Sequence[Tuple[float, float, float, float]] = REGIONS,
                  projects: Optional[Sequence[str]] = None, log: Callable[[str], None] = print,
                  at_once: Optional[int] = None, allow_drop: bool = False) -> Dict:
    """Make the list of the bucket's 1 m files the TNM index does not list and write it to out, by default the cached
    list (unlisted_path, with a row in the index of its top folder); cache_dir also holds the host slots. projects:
    only these of the bucket (a recorded test; then neither guard applies). at_once: requests at a time in each
    part (REQUESTS_AT_ONCE). allow_drop: the index may list fewer files than the list before by more than
    MAX_LISTED_DROP (checked by hand). Returns what it did: files, bytes, how their zones and years were found, the
    names left out, the projects dated by their upload, the bucket's files and the index's, the requests, bytes and
    seconds of each part. IndexUnavailable when a step fails; the list there was stays."""
    at_once = REQUESTS_AT_ONCE if at_once is None else at_once
    started = time.monotonic()
    stop = threading.Event()
    bucket_budget = PageBudget("USGS's bucket (1 m DEM)", BUCKET_PAGES, stop)
    tnm_budget = PageBudget("the TNM index (1 m DEM)", TNM_PAGES, stop)
    header_budget = PageBudget("the headers of the unlisted 1 m files", HEADER_READS, stop)
    seconds = {}

    def header(url, extent):
        header_budget.take()
        return header_zone(url, extent, cache_dir)
    try:
        log("Listing USGS's bucket (1 m DEM projects)...")
        objects = bucket_files(cache_dir, bucket, bucket_budget, projects, at_once)
        seconds["bucket"] = round(time.monotonic() - started, 1)
        log(f"  {len(objects)} files in {bucket_budget.used} requests; listing the TNM index...")
        listed = tnm_listed(cache_dir, api, dataset, regions, tnm_budget, at_once)
        seconds["index"] = round(time.monotonic() - started - seconds["bucket"], 1)
        log(f"  {len(listed)} listed in {tnm_budget.used} requests; finding the zones of the unlisted files...")
        if objects and not listed:
            raise IndexUnavailable("the TNM index listed no 1 m file")
        if projects is None:  # the guards, before any header is read
            unlisted = len(unlisted_objects(objects, listed))
            if unlisted > MAX_UNLISTED_SHARE * len(objects):
                raise IndexUnavailable(f"{unlisted} of the bucket's {len(objects)} 1 m files look unlisted: the TNM "
                                       f"index answered too little; the list was not made")
            before = previous_listed(cache_dir)
            if before and len(listed) < (1 - MAX_LISTED_DROP) * before:
                confirmed = None if allow_drop else _refused_again(cache_dir, len(listed))
                if allow_drop:
                    log(f"  the index lists {len(listed)} files, the list before {before}: accepted (allow_drop)")
                elif confirmed is not None:
                    log(f"  the index lists {len(listed)} files, the list before {before}, as a listing of "
                        f"{confirmed['at']:%Y-%m-%d %H:%M} UTC did: the index did shrink, the list is made")
                else:
                    raise IndexUnavailable(f"the TNM index listed {len(listed)} 1 m files, the list before {before}: "
                                           f"it answered too little; the list was not made (a listing at least a "
                                           f"day later that agrees is accepted; tools/usa_unlisted.py --allow-drop "
                                           f"after checking)")
        mark = time.monotonic()
        items, left_out, counts, upload_projects = unlisted_from(objects, listed, header, bucket, at_once, stop)
        seconds["headers"] = round(time.monotonic() - mark, 1)
    except IndexUnavailable:
        raise
    except (requests.RequestException, rio.errors.RasterioError, RuntimeError, OSError) as e:
        raise IndexUnavailable(f"the list of the unlisted 1 m files: {cache.clean_error(e)}") from e
    summary = {"made_at": cache.now_iso(), "files": len(items), "bytes": counts.get("bytes", 0),
               "zone_in_name": counts.get("zone_in_name", 0), "zone_from_project": counts.get("zone_from_project", 0),
               "zone_from_header": counts.get("zone_from_header", 0),
               "year_from_siblings": counts.get("year_from_siblings", 0),
               "year_from_upload": counts.get("year_from_upload", 0), "upload_year_projects": upload_projects,
               "left_out": left_out, "bucket_files": len(objects), "listed": len(listed),
               "requests": {"bucket": bucket_budget.used, "index": tnm_budget.used, "headers": header_budget.used},
               "answer_bytes": {"bucket": bucket_budget.bytes, "index": tnm_budget.bytes},
               "seconds_by_part": seconds, "at_once": at_once, "seconds": round(time.monotonic() - started, 1)}
    path = out or unlisted_path(cache_dir)
    write_list(path, summary, items, bucket, api, dataset)
    if out is None:
        cache.record(cache_dir, path, url=bucket)
        with contextlib.suppress(OSError):
            os.remove(refused_path(cache_dir))
    forget_unlisted()
    summary["path"] = path
    log(f"  {len(items)} unlisted files ({summary['bytes'] / 1e9:.1f} GB), {len(left_out)} left out without a zone; "
        f"written to {path}")
    return summary


COUNT_KEYS = ("files", "bytes", "zone_in_name", "zone_from_project", "zone_from_header", "year_from_siblings",
              "year_from_upload", "bucket_files", "listed")


def write_list(path: str, summary: Dict, items: List[Dict], bucket: str, api: str, dataset: str):
    """The list as JSON, one item a line (the shipped copy's changes read as lines), written to a temporary file next
    to it and put in its place (os.replace). A failure (a full disk, the file held open by another process on
    Windows) is IndexUnavailable, the temporary file removed and the list there was kept."""
    head = {"made_at": summary["made_at"], "bucket": bucket, "index": api, "dataset": dataset,
            "counts": {k: summary.get(k, 0) for k in COUNT_KEYS},
            "upload_year_projects": summary.get("upload_year_projects", []), "left_out": summary["left_out"]}
    text = json.dumps(head)[:-1] + ', "items": [\n' + ",\n".join(json.dumps(item) for item in items) + "\n]}\n"
    tmp = net._part(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise IndexUnavailable(f"the list of the unlisted 1 m files could not be written ({path}): {e}") from e


def unlisted_age_days(cache_dir: str, top: str = TOP) -> float:
    """Days since the cached list was made (its row's check time); infinite without one (the shipped copy does
    not count: a renewal makes the cached list). The user's rule of 2026-11-23 for A-2: a download row or a country
    run starts on a list at most 28 days old."""
    path = unlisted_path(cache_dir, top)
    row = cache.info(cache_dir, path) if os.path.exists(path) else None
    return cache.age_days(row["checked_at"]) if row else float("inf")


# Reading the list

READS = 0  # lists parsed by this process (tests: once per process and data folder)
ITEM_KEYS = ("name", "url", "crs", "extent", "year", "published")
_memo: Dict[Tuple[str, str], Tuple[float, tuple, Dict]] = {}
_memo_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _shipped_off() -> bool:
    return os.environ.get(SHIPPED_ENV, "").strip().lower() == "off"


def forget_unlisted():
    """Read the list again at its next use (after it was written)."""
    with _memo_lock:
        _memo.clear()


def _stamp(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return path, st.st_mtime_ns, st.st_size


def _good_item(item) -> bool:
    """Whether a list's item is a 1 m file as tile_item makes it (the right fields and kinds, a NAD83 / UTM zone, a
    square extent)."""
    if not isinstance(item, dict) or not all(k in item for k in ITEM_KEYS):
        return False
    zone = re.fullmatch(r"EPSG:269(\d\d)", item["crs"]) if isinstance(item["crs"], str) else None
    extent = item["extent"]
    return (isinstance(item["name"], str) and isinstance(item["url"], str) and bool(item["url"])
            and zone is not None and 1 <= int(zone.group(1)) <= 23 and isinstance(item["year"], int)
            and isinstance(item["published"], str) and isinstance(extent, list) and len(extent) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in extent)
            and extent[0] < extent[2] and extent[1] < extent[3])


def read_list(path: str) -> Tuple[List[Dict], int]:
    """The items of a list file that are 1 m files (_good_item), and how many others it held. ValueError for a file
    that is no list (not JSON, cut short, not an object with a list of items)."""
    global READS
    with open(path, encoding="utf-8") as f:
        document = json.load(f)
    READS += 1
    if not isinstance(document, dict) or not isinstance(document.get("items"), list):
        raise ValueError("not a list of files (an object with \"items\")")
    items = [item for item in document["items"] if _good_item(item)]
    return items, len(document["items"]) - len(items)


def _by_tile(items: List[Dict]) -> Dict[Tuple[int, int], List[Dict]]:
    """The items by the 0.25° index tiles their 10 km square reaches (its WGS84 box grown by INDEX_MARGIN_DEG: an
    extra tile costs nothing, the blocks take a file by its extent; a missed one would lose it)."""
    found: Dict[Tuple[int, int], List[Dict]] = {}
    m = INDEX_MARGIN_DEG
    for item in items:
        west, south, east, north = transform_bounds(item["crs"], "EPSG:4326", *item["extent"], densify_pts=21)
        for lat, lon in osm.tiles(west - m, south - m, east + m, north + m):
            found.setdefault((round(lat / osm.TILE_DEG), round(lon / osm.TILE_DEG)), []).append(item)
    return found


def _load(cache_dir: str, top: str) -> Tuple[tuple, Dict[Tuple[int, int], List[Dict]]]:
    """The stamps of the lists that could be read and the first usable one by index tile: the cached list, else the
    shipped copy (unless SHIPPED_ENV is off). Whatever a file holds, reading it never fails the 1 m layer: a file that
    cannot be used is one printed line and the next one is read; its wrong items are left out and counted."""
    cached = unlisted_path(cache_dir, top)
    paths = [cached] + ([] if _shipped_off() else [SHIPPED])
    stamps = list(_stamp(path) for path in paths)
    for k, (path, stamp) in enumerate(zip(paths, stamps)):
        if stamp is None:
            continue
        try:
            for attempt in range(3):  # a list being replaced by a renewal (Windows: a moment of no access)
                try:
                    items, wrong = read_list(path)
                    break
                except OSError:
                    if attempt == 2:
                        stamps[k] = (path, "unreadable", time.monotonic())  # looked at again at the next check
                        raise
                    time.sleep(0.05)
            tiles = _by_tile(items)
        except Exception as e:  # noqa: BLE001 (any content of a file: never a failure of a search)
            then = "the shipped copy is read instead" if path == cached and len(paths) > 1 else "no list is used"
            print(f"The list of the 1 m files the TNM index does not list cannot be used ({path}: "
                  f"{type(e).__name__}: {str(e)[:200]}); {then}")
            continue
        if wrong:
            print(f"The list of the 1 m files the TNM index does not list ({path}): {wrong} of its items are no 1 m "
                  f"file and are left out")
        return tuple(stamps), tiles
    return tuple(stamps), {}


def _tiles(cache_dir: str, top: str) -> Dict[Tuple[int, int], List[Dict]]:
    """The list by index tile, read once per process and data folder: looked at again (a stat) at most every
    RECHECK_S and read again only when it changed (a renewal by another process); a list that could not be used
    is remembered the same way (no read per tile)."""
    key, now = (os.path.abspath(cache_dir), top), _now()
    with _memo_lock:
        memo = _memo.get(key)
        if memo is not None and now - memo[0] < RECHECK_S:
            return memo[2]
        paths = [unlisted_path(cache_dir, top)] + ([] if _shipped_off() else [SHIPPED])
        stamps = tuple(_stamp(path) for path in paths)
        if memo is not None and memo[1] == stamps:
            _memo[key] = (now, stamps, memo[2])
            return memo[2]
        stamps, tiles = _load(cache_dir, top)
        _memo[key] = (now, stamps, tiles)
        return tiles


def unlisted_in_tile(cache_dir: str, top: str, lat: float, lon: float) -> List[Dict]:
    """The unlisted files whose 10 km square reaches the 0.25° index tile with this south-west corner."""
    return _tiles(cache_dir, top).get((round(lat / osm.TILE_DEG), round(lon / osm.TILE_DEG)), [])
