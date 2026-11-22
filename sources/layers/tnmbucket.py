"""The files of the USA's 1 m DEM that are in USGS's bucket but not in the TNM index: the list of them (make_unlisted)
and the list as the 1 m layer reads it (unlisted_in_tile, merged into the index's answers by tnm.UnlistedIndex).

The 1 m layer (tnm.Usgs1mBlocks) finds its files through the TNM Access API, but USGS's bucket holds more 1 m files
than the API lists (1,410 of 127,289 in the projects of the lower 48 on 2026-11-22; in Utah they covered every square
that looked like a hole). make_unlisted makes the list of those: (1) every `.tif` under
StagedProducts/Elevation/1m/Projects/<project>/TIFF/ of the bucket (ListObjectsV2, about 990 pages), (2) the names
the TNM index lists over the USA and its territories (REGIONS, a box split in four while it holds more than
SPLIT_ABOVE products, so no page is asked at a deep offset), (3) the bucket's files whose name the index does not
list, (4) the UTM zone of each (from the name, USGS_1M_<zone>_x..y..; for USGS_one_meter_x..y.. and USGS_1m_x..y..,
which carry none, from the project's listed files when they lie in one zone and the tile then lands in the
project's box, else from the file's own header: one small read), (5) written atomically to
<cache>/usa/sheet-index/bucket1m/unlisted.json with a row in usa/index.sqlite (its age), each file as the item a
TNM answer holds (tnm.tile_item: name, url, crs, extent, year; published = the upload time in the bucket). A file
whose zone cannot be found is left out and named. Any step that fails raises IndexUnavailable and leaves the list
there was. Every request carries the app's User-Agent, holds a slot of its host and is counted (servicecounts);
each listing has a budget of pages (PageBudget) and a repeated continuation token is an error.

Where no list is cached, the copy shipped with the code is read (SHIPPED, made by tools/usa_unlisted.py with this
function; FINDALINE_USA_UNLISTED_SHIPPED=off leaves it out: the tests). The renewal of the list (part A-2 of the
USA's wave A) calls make_unlisted. The web process never imports this module.
"""

import collections
import contextlib
import json
import os
import threading
import time
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
from .tnm import TILE_ZONE, TNM_API, tile_extent, tile_item, usgs_1m_item

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
BUCKET_PAGES = 3000  # 989 on 2026-11-22
TNM_PAGES = 3000     # about 450 (est.)
# More of the bucket's files looking unlisted than this share is an index that answered too little (a box empty for
# a moment): an error, not a list (1.1 % on 2026-11-22)
MAX_UNLISTED_SHARE = 0.05
PROJECT_MARGIN_DEG = 0.25  # a tile given its project's one zone lands within the project's listed box grown by this
# A file's bounds within this of its name's 10 km square: the standard tiles reach 6 m beyond it, older ones up to
# about 400 m (MS_Laurel_2014's x22y372: 297 m west; checked 2026-11-22), some cover only part of it (NM_NorthCentral)
HEADER_MARGIN_M = 1000
RECHECK_S = 300            # how often a process looks whether the cached list was renewed (by another process)


def unlisted_path(cache_dir: str, top: str = TOP) -> str:
    """The cached list of the unlisted files."""
    return os.path.join(cache_dir, top, "sheet-index", "bucket1m", "unlisted.json")


def project_of(url: str) -> str:
    """The project folder of a 1 m file's URL (or key)."""
    return url.split("/Projects/", 1)[-1].split("/", 1)[0] if "/Projects/" in url else ""


# The bucket

def bucket_files(cache_dir: Optional[str], bucket: str = BUCKET, budget: Optional[PageBudget] = None,
                 projects: Optional[Sequence[str]] = None) -> List[S3Object]:
    """Every .tif key under <project>/TIFF/ of the bucket's 1 m projects (all, or those named), in S3's order."""
    budget = budget or PageBudget("USGS's bucket (1 m DEM)", BUCKET_PAGES)
    found: List[S3Object] = []
    for folder in common_prefixes(bucket, PROJECTS, "/", cache_dir, budget):
        if projects is not None and folder[len(PROJECTS):].rstrip("/") not in projects:
            continue
        found += [obj for obj in list_objects(bucket, folder + "TIFF/", MAX_KEYS, cache_dir, budget)
                  if obj.key.lower().endswith(".tif")]
    return found


# The TNM index

def _tnm_page(cache_dir: Optional[str], api: str, dataset: str, box: Tuple[float, float, float, float],
              offset: int, budget: PageBudget) -> Dict:
    """One page of the TNM index's products over a box; slow or failed answers asked again (net.RETRIES)."""
    params = {"datasets": dataset, "max": TNM_PAGE, "offset": offset, "bbox": ",".join(f"{v:g}" for v in box)}
    for attempt in range(net.RETRIES):
        budget.take()
        try:
            net.rate_turn(api)
            slot = net.host_slot(cache_dir, api) if cache_dir else contextlib.nullcontext()
            with slot:
                response = servicecounts.get(api, timeout=120, headers=cache.http_headers(), params=params)
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, dict) or not isinstance(page.get("items") or [], list):
                raise ValueError("not an answer of products")
            return page
        except (requests.RequestException, ValueError) as e:
            if attempt == net.RETRIES - 1:
                raise IndexUnavailable(f"TNM API: {cache.clean_error(e)}") from e
            net._sleep(attempt)
    raise AssertionError("unreachable")


def tnm_listed(cache_dir: Optional[str], api: str = TNM_API, dataset: str = DATASET,
               regions: Sequence[Tuple[float, float, float, float]] = REGIONS,
               budget: Optional[PageBudget] = None) -> Dict[str, Dict]:
    """Every product of the TNM index's dataset over the boxes, by its download URL. A box whose first page says it
    holds more than SPLIT_ABOVE is asked again as its four quarters (the first page's products kept), so no page
    lies deep. The API counts some products twice in its `total` (a box of one page may say 4 and give 2 distinct):
    a page shorter than the total promises is asked once more and the two are joined; the next page starts after
    what came (offset += its length: pages overlap, never skip). Completeness is the distinct URLs, never `total`."""
    budget = budget or PageBudget("the TNM index (1 m DEM)", TNM_PAGES)
    found: Dict[str, Dict] = {}

    def keep(items):
        for product in items:
            url = product.get("downloadURL") if isinstance(product, dict) else None
            if url:
                found.setdefault(url, {"downloadURL": url, "boundingBox": product.get("boundingBox"),
                                       "publicationDate": product.get("publicationDate")})

    boxes = list(regions)
    while boxes:
        box = boxes.pop(0)
        page, offset = _tnm_page(cache_dir, api, dataset, box, 0, budget), 0
        west, south, east, north = box
        if (page.get("total") or 0) > SPLIT_ABOVE and east - west > MIN_SPLIT_DEG:
            keep(page.get("items") or [])
            mid_x, mid_y = (west + east) / 2, (south + north) / 2
            boxes[0:0] = [(west, south, mid_x, mid_y), (mid_x, south, east, mid_y),
                          (west, mid_y, mid_x, north), (mid_x, mid_y, east, north)]
            continue
        while True:
            items, total = page.get("items") or [], page.get("total") or 0
            if len(items) < min(TNM_PAGE, total - offset):
                again = _tnm_page(cache_dir, api, dataset, box, offset, budget).get("items") or []
                keep(again)
                items = again if len(again) > len(items) else items
            keep(page.get("items") or [])
            if not items:
                break
            offset += len(items)
            if offset >= total:
                break
            page = _tnm_page(cache_dir, api, dataset, box, offset, budget)
    return found


# The zone of a name without one

def header_zone(url: str, extent: Sequence[float], cache_dir: Optional[str]) -> Optional[int]:
    """The UTM zone of a remote 1 m file from its own header (one small read through GDAL's /vsicurl/, inside
    net._gdal_http, its errors seen through net.gdal_errors, holding a slot of the host): the zone z whose NAD83 /
    UTM (EPSG:269zz) the file's CRS is (windows._same_crs, as the reader will test it), the file's bounds meeting
    the name's 10 km square and within HEADER_MARGIN_M of it. None when the file is not there (404) or fits no zone; a failure
    to read it raises IndexUnavailable (the list is then not made)."""
    found = None
    slot = net.host_slot(cache_dir, url) if cache_dir else contextlib.nullcontext()
    with slot, net._gdal_http():
        for attempt in range(net.RETRIES):
            with servicecounts.request(url) as counted:
                try:
                    with net.gdal_errors() as errors:
                        src = rio.open(net._remote(url))
                    with src:
                        found = (src.crs, tuple(src.bounds))
                    if errors:
                        raise rio.errors.RasterioIOError("; ".join(dict.fromkeys(errors)))
                    break
                except rio.errors.RasterioIOError as e:
                    _forget(url)
                    if "404" in str(e) or "No such file" in str(e):
                        counted.outcome = "not_found"
                        return None
                    counted.outcome = "other"
                    if attempt == net.RETRIES - 1:
                        raise IndexUnavailable(f"the header of {url.rsplit('/', 1)[-1]}: "
                                               f"{cache.clean_error(e)}") from e
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


def _in_box(zone: int, extent: Sequence[float], box: Sequence[float]) -> bool:
    """Whether the centre of a tile, taken in a zone, lies in a WGS84 box grown by PROJECT_MARGIN_DEG."""
    x, y = rio.warp.transform(f"EPSG:{26900 + zone}", "EPSG:4326", [(extent[0] + extent[2]) / 2],
                              [(extent[1] + extent[3]) / 2])
    m = PROJECT_MARGIN_DEG
    return box[0] - m <= x[0] <= box[2] + m and box[1] - m <= y[0] <= box[3] + m


def unlisted_from(objects: Sequence[S3Object], listed: Dict[str, Dict], header: Callable[[str, list], Optional[int]],
                  bucket: str = BUCKET) -> Tuple[List[Dict], List[str], Dict[str, int]]:
    """The bucket's files (objects) whose name the index (listed: its products by URL) does not list, each as an item
    (tnm.tile_item, published = its upload time), sorted by URL; the names left out (no x..y.. in the name, or no
    zone found); counts (by how the zone was found, and bytes). header(url, extent) gives a zone from the file."""
    names = {url.rsplit("/", 1)[-1] for url in listed}
    unlisted = [obj for obj in objects if obj.key.rsplit("/", 1)[-1] not in names]
    # The zones and the box of the listed files of the projects that need them (names without a zone)
    wanted = {project_of(obj.key) for obj in unlisted if not TILE_ZONE.match(obj.key.rsplit("/", 1)[-1])}
    zones: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    boxes: Dict[str, List[float]] = {}
    for url, product in listed.items():
        project = project_of(url)
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
    items, left_out = [], []
    counts = collections.Counter()
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
                zone, how = header(url, extent), "zone_from_header"
        if zone is None:
            left_out.append(name)
            continue
        counts[how] += 1
        counts["bytes"] += obj.size
        items.append(tile_item(url, zone, obj.last_modified))
    items.sort(key=lambda item: item["url"])
    return items, sorted(left_out), dict(counts)


# Making the list

def make_unlisted(cache_dir: str, out: Optional[str] = None, bucket: str = BUCKET, api: str = TNM_API,
                  dataset: str = DATASET, regions: Sequence[Tuple[float, float, float, float]] = REGIONS,
                  projects: Optional[Sequence[str]] = None, log: Callable[[str], None] = print) -> Dict:
    """Make the list of the bucket's 1 m files the TNM index does not list and write it to out, by default the cached
    list (unlisted_path, with a row in the index of its top folder); cache_dir also holds the host slots. projects:
    only these of the bucket (a recorded test; then the share of unlisted files is not checked). Returns what it did:
    files, bytes, how their zones were found, the names left out, the bucket's files and the index's, the requests.
    IndexUnavailable when a step fails; the list there was stays."""
    started = time.monotonic()
    bucket_budget = PageBudget("USGS's bucket (1 m DEM)", BUCKET_PAGES)
    tnm_budget = PageBudget("the TNM index (1 m DEM)", TNM_PAGES)
    headers = [0]

    def header(url, extent):
        headers[0] += 1
        return header_zone(url, extent, cache_dir)
    try:
        log("Listing USGS's bucket (1 m DEM projects)...")
        objects = bucket_files(cache_dir, bucket, bucket_budget, projects)
        log(f"  {len(objects)} files in {bucket_budget.used} requests; listing the TNM index...")
        listed = tnm_listed(cache_dir, api, dataset, regions, tnm_budget)
        log(f"  {len(listed)} listed in {tnm_budget.used} requests; finding the zones of the unlisted files...")
        if objects and not listed:
            raise IndexUnavailable("the TNM index listed no 1 m file")
        items, left_out, counts = unlisted_from(objects, listed, header, bucket)
    except IndexUnavailable:
        raise
    except (requests.RequestException, rio.errors.RasterioError, RuntimeError, OSError) as e:
        raise IndexUnavailable(f"the list of the unlisted 1 m files: {cache.clean_error(e)}") from e
    if projects is None and objects and (len(items) + len(left_out)) > MAX_UNLISTED_SHARE * len(objects):
        raise IndexUnavailable(f"{len(items) + len(left_out)} of the bucket's {len(objects)} 1 m files look "
                               f"unlisted: the TNM index answered too little; the list was not made")
    summary = {"made_at": cache.now_iso(), "files": len(items), "bytes": counts.get("bytes", 0),
               "zone_in_name": counts.get("zone_in_name", 0), "zone_from_project": counts.get("zone_from_project", 0),
               "zone_from_header": counts.get("zone_from_header", 0), "left_out": left_out,
               "bucket_files": len(objects), "listed": len(listed),
               "requests": {"bucket": bucket_budget.used, "index": tnm_budget.used, "headers": headers[0]},
               "seconds": round(time.monotonic() - started, 1)}
    path = out or unlisted_path(cache_dir)
    write_list(path, summary, items, bucket, api, dataset)
    if out is None:
        cache.record(cache_dir, path, url=bucket)
    forget_unlisted()
    summary["path"] = path
    log(f"  {len(items)} unlisted files ({summary['bytes'] / 1e9:.1f} GB), {len(left_out)} left out without a zone; "
        f"written to {path}")
    return summary


def write_list(path: str, summary: Dict, items: List[Dict], bucket: str, api: str, dataset: str):
    """The list as JSON, one item a line (the shipped copy's changes read as lines), written atomically."""
    head = {"made_at": summary["made_at"], "bucket": bucket, "index": api, "dataset": dataset,
            "counts": {k: summary[k] for k in ("files", "bytes", "zone_in_name", "zone_from_project",
                                               "zone_from_header", "bucket_files", "listed")},
            "left_out": summary["left_out"]}
    text = json.dumps(head)[:-1] + ', "items": [\n' + ",\n".join(json.dumps(item) for item in items) + "\n]}\n"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = net._part(path)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def unlisted_age_days(cache_dir: str, top: str = TOP) -> float:
    """Days since the cached list was made (its row's check time); infinite without one (the shipped copy does
    not count: a renewal makes the cached list)."""
    path = unlisted_path(cache_dir, top)
    row = cache.info(cache_dir, path) if os.path.exists(path) else None
    return cache.age_days(row["checked_at"]) if row else float("inf")


# Reading the list

READS = 0  # lists parsed by this process (tests: once per process and data folder)
ITEM_KEYS = ("name", "url", "crs", "extent", "year", "published")
_memo: Dict[Tuple[str, str], Tuple[float, Optional[tuple], Dict]] = {}
_memo_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


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


def _source(cache_dir: str, top: str) -> Tuple[Optional[str], Optional[tuple]]:
    """The list to read: the cached one, else the shipped copy (unless SHIPPED_ENV is off), else none."""
    path = unlisted_path(cache_dir, top)
    stamp = _stamp(path)
    if stamp is not None:
        return path, stamp
    if os.environ.get(SHIPPED_ENV, "").strip().lower() == "off":
        return None, None
    stamp = _stamp(SHIPPED)
    return (SHIPPED, stamp) if stamp is not None else (None, None)


def read_list(path: str) -> List[Dict]:
    """The items of a list file (those with every key of an item)."""
    global READS
    with open(path, encoding="utf-8") as f:
        document = json.load(f)
    READS += 1
    return [item for item in document.get("items") or [] if isinstance(item, dict) and all(k in item for k in ITEM_KEYS)]


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


def _tiles(cache_dir: str, top: str) -> Dict[Tuple[int, int], List[Dict]]:
    """The list by index tile, read once per process and data folder: looked at again (a stat) at most every
    RECHECK_S and read again only when it changed (a renewal by another process)."""
    key, now = (os.path.abspath(cache_dir), top), _now()
    with _memo_lock:
        memo = _memo.get(key)
        if memo is not None and now - memo[0] < RECHECK_S:
            return memo[2]
        path, stamp = _source(cache_dir, top)
        if memo is not None and memo[1] == stamp:
            _memo[key] = (now, stamp, memo[2])
            return memo[2]
        tiles: Dict[Tuple[int, int], List[Dict]] = {}
        if path is not None:
            try:
                tiles = _by_tile(read_list(path))
            except (OSError, ValueError) as e:
                print(f"The list of the 1 m files the TNM index does not list could not be read ({path}): {e}")
        _memo[key] = (now, stamp, tiles)
        return tiles


def unlisted_in_tile(cache_dir: str, top: str, lat: float, lon: float) -> List[Dict]:
    """The unlisted files whose 10 km square reaches the 0.25° index tile with this south-west corner."""
    return _tiles(cache_dir, top).get((round(lat / osm.TILE_DEG), round(lon / osm.TILE_DEG)), [])
