"""
Bulk fetch of elevation models into a folder, for the mirror: Portugal's lidar terrain and surface models from
DGT's data centre (CDD: https://cdd.dgterritorio.gov.pt, CC BY 4.0, a free account's login) and plain file lists
(`fetch-list wallonia`: Wallonia's ten province ZIPs, CC BY 4.0, no login). It runs for days on another machine (a
home server) in a stock Python container: standard library only, Python 3.11 or newer, no import of this project.
Cutting the files into mirror tiles is a later step, not this tool's.

    python cdd_fetch.py plan [--collections MDT-50cm MDS-50cm ...] [--bbox S N W E]
    python cdd_fetch.py fetch [--pause 3] [--retries 2] [--min-free-gb 50] [--limit N]
    python cdd_fetch.py fetch-list wallonia
    python cdd_fetch.py status

Everything lives in `--out`, by default `downloads/` beside the script: `downloads/portugal/` (manifest.jsonl,
plan.json, done.jsonl, failed.jsonl, status.json, fetch.log and `<collection>/<folder>/<item id>.tif`: the folder is
a mainland sheet's first three digits or an Azores island's code) and `downloads/wallonia/` (the ZIPs under their
own names and the same state files). The tool never deletes a fetched file, only its own `.part` files.

`plan` asks the public search (POST /dgt-be/v1/search, CQL2-JSON `s_intersects` for `--bbox`, no login) for every
item of the collections, page after page (1000 items, the `next` link's body token, 1.5 s apart), keeps the newest
version of each sheet and writes one line per file (collection, item id, sheet, folder, version, size). A download
address is minted anew by every search (two searches for one item gave two addresses, 2026-11-15), so none is
stored: `fetch` resolves them from the signed-in search just before use, 20 ids per search.

`fetch` signs in through the site's Keycloak form (credentials only from the environment: CDD_USER, CDD_PASSWORD),
then fetches every file of the manifest not yet done: one request at a time, a pause between files, into
`<file>.part`, renamed when it checks (TIFF magic, the item's stated size); its sha256 goes into done.jsonl. A
download answered by the login page, a 401/403 or an HTML page means: sign in again and retry the file once with a
fresh address; three sign-ins without a file between them stop the run; a refused sign-in stops it at once (no
loop against the login form). 429/503: a growing wait honouring Retry-After. A failed file is tried again at the end
of the run (at most `--retries` times) and at the next run; five failed files in a row stop the run. Free space under
`--min-free-gb` (plus the next file) stops it. SIGTERM or Ctrl-C drops the current `.part` and exits 0 with the
state saved; a second `fetch` continues where it stopped. `status.json` is rewritten every few files. done.jsonl
decides what is done: a file deleted by hand after it was recorded (cut into tiles) is not fetched again.

`fetch-list wallonia` fetches the embedded list (addresses and sizes read 2026-11-15) the same way without a login;
that server ignores Range, so a broken file starts again from zero; the size must equal the list's (a different
Content-Length stops that file before its body is read). `status` prints both areas: files and bytes done and left,
the last error, the time left at the measured rate.

Secrets never appear in any output: the username, the password, cookies and download addresses (their tokens and
queries) are masked in every printed or written text (`Scrub`); the item id names a file in the log.

Exit codes: 0 done or stopped by a signal; 1 an error; 2 credentials missing or refused; 3 three sign-ins without a
file; 4 five failed files in a row; 5 the disk is full (under --min-free-gb).

On a home server, the script in its own folder with an env file `cdd.env` beside it (two lines,
`CDD_USER=...` and `CDD_PASSWORD=...`, readable by its owner only):

    docker run -d --name cdd-fetch --env-file /path/to/folder/cdd.env -v /path/to/folder:/work -w /work \\
        python:3.12-slim python cdd_fetch.py fetch

    services:                      # compose.yaml in the same folder
      cdd-fetch:
        image: python:3.12-slim
        working_dir: /work
        volumes: ["./:/work"]
        env_file: [cdd.env]
        command: python cdd_fetch.py fetch
        restart: "no"
        stop_grace_period: 60s
        # user: "<uid>:<gid>"        # the folder's owner, if the files should not belong to root

`plan` runs once before (`docker run --rm -v ...:/work -w /work python:3.12-slim python cdd_fetch.py plan`),
`status` any time; `fetch-list wallonia` is the same service with that command.
"""

import argparse
import datetime
import email.utils
import hashlib
import html
import http.client
import http.cookiejar
import itertools
import json
import os
import re
import shutil
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

SITE = "https://cdd.dgterritorio.gov.pt"
SEARCH = "/dgt-be/v1/search"
# The realm's own address of the login, asked when the site's /auth/login does not lead to the form
AUTH_URL = ("https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect/auth?"
            + urllib.parse.urlencode({"client_id": "aai-oidc-dgt", "response_type": "code",
                                      "redirect_uri": SITE + "/auth/callback", "scope": "openid profile email"}))
AGENT = "Find-a-Line/0.1 (highline finder; mirror fetch)"
COLLECTIONS = ("MDT-50cm", "MDS-50cm", "ACORES-MDE-1", "ACORES-MDS-1")
FIELDS = {"include": ["id", "collection", "properties.version", "properties.file:size", "properties.datetime",
                      "assets"],
          "exclude": ["properties.proj:wkt2", "properties.eo:bands", "geometry", "links"]}
PAGE = 1000            # items per search page while planning
RESOLVE_BATCH = 20     # ids per search resolving download addresses
ADDRESS_SECONDS = 900  # a resolved address is used within this time, else resolved again
SEARCH_PAUSE = 1.5     # seconds between searches
TIMEOUT = 120          # seconds a socket may wait
CHUNK = 1 << 20
STATUS_EVERY = 5       # files between rewrites of status.json
DISK_EVERY = 1 << 30   # bytes between free-space checks within one file
MAX_SIGNINS = 3        # sign-ins in a row without a fetched file
MAX_FAILED_IN_ROW = 5
THROTTLE_TRIES = 6     # 429/503 answers to one file before it counts as failed
WAIT_BASE = 60.0       # the first wait after a 429/503 (doubled each time)
WAIT_MAX = 1800.0
RATE = 16e6 / 2.1      # bytes per second of one CDD download, measured by the coordinator on 2026-11-15
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
ZIP_MAGIC = (b"PK\x03\x04",)

EXIT_OK, EXIT_ERROR, EXIT_CREDENTIALS, EXIT_SIGNINS, EXIT_FAILURES, EXIT_DISK = 0, 1, 2, 3, 4, 5

_WALLONIA = "https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/"
_MNT = _WALLONIA + "a004e570-99d6-4fe5-b83d-49b774409278/RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_"
_MNS = _WALLONIA + "5a4c28fe-d30c-493e-861e-a80ebc703b64/RELIEF_WALLONIE_MNS_50CM_2021_2022_GEOTIFF_3812_PROV_"
# Plain file lists: name -> the folder below --out, the files' magic, (group, address, bytes) in the order fetched.
# Wallonia: SPW's MNT and MNS 2021-2022 at 0.5 m in EPSG:3812, per province (catalogue pages a004e570... and
# 5a4c28fe..., tab "Téléchargement"; addresses and sizes read 2026-11-15); Namur first (the user's order)
LISTS = {
    "wallonia": {"folder": "wallonia", "read": "2026-11-15", "magic": ZIP_MAGIC, "files": [
        ("MNT", _MNT + "NAMUR.zip", 46_315_489_746),
        ("MNS", _MNS + "NAMUR.zip", 55_838_449_055),
        ("MNT", _MNT + "LIEGE.zip", 48_579_593_210),
        ("MNS", _MNS + "LIEGE.zip", 58_215_171_576),
        ("MNT", _MNT + "LUXEMBOURG.zip", 55_936_435_422),
        ("MNS", _MNS + "LUXEMBOURG.zip", 67_265_946_378),
        ("MNT", _MNT + "HAINAUT.zip", 47_398_087_781),
        ("MNS", _MNS + "HAINAUT.zip", 59_195_352_259),
        ("MNT", _MNT + "BRABANT_WALLON.zip", 13_919_501_421),
        ("MNS", _MNS + "BRABANT_WALLON.zip", 16_928_007_009),
    ]},
}

STOP = threading.Event()  # set by SIGTERM / SIGINT: the current file is dropped, the state saved
HTTPException = http.client.HTTPException


def _wait(seconds):
    """A pause that a stop ends early (tests replace it)."""
    STOP.wait(max(seconds, 0))


def default_out():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Secrets and output

class Scrub:
    """Masks what must never be printed or written: the credentials, cookie values, tokens of 64 hex digits and
    every address's path and query (an address is cut to its host)."""

    URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>]+")
    TOKEN = re.compile(r"[0-9A-Fa-f]{32,}")

    def __init__(self):
        self.secrets = set()

    def add(self, value):
        if value and len(value) >= 3:
            self.secrets.add(value)
            quoted = urllib.parse.quote(value, safe="")
            if quoted != value:
                self.secrets.add(quoted)
            plus = urllib.parse.quote_plus(value)
            if plus != value:
                self.secrets.add(plus)

    def text(self, text):
        text = str(text)
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "***")
        text = self.URL.sub(lambda m: "%s://%s/..." % (urllib.parse.urlsplit(m.group(0)).scheme,
                                                       urllib.parse.urlsplit(m.group(0)).hostname or "?"), text)
        return self.TOKEN.sub("<token>", text)


class Log:
    """Lines to stdout and to <area>/<name>.log, each scrubbed and dated."""

    def __init__(self, scrub, path=None):
        self.scrub, self.path = scrub, path

    def __call__(self, *parts, error=False):
        line = "%s %s" % (now(), self.scrub.text(" ".join(str(p) for p in parts)))
        print(line, file=sys.stderr if error else sys.stdout, flush=True)
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


def _write_json(path, data):
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(path + ".part", path)


def _read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass  # a line cut by a kill
    return rows


def _append_jsonl(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


# HTTP

class SessionLost(Exception):
    """The download was answered by the login (a redirect to it, 401/403, an HTML page)."""


class Throttled(Exception):
    def __init__(self, status, retry_after):
        super().__init__("HTTP %d" % status)
        self.retry_after = retry_after


class Stale(Exception):
    """404/410 of a download address: resolved again once."""


class BadFile(Exception):
    """The file failed (an HTTP error, a wrong magic or size, a broken connection): tried again later."""


class DiskLow(Exception):
    pass


class Stopped(Exception):
    pass


class CredentialsRefused(Exception):
    pass


def _retry_after(headers):
    value = (headers or {}).get("Retry-After")
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
            return max((when - datetime.datetime.now(datetime.timezone.utc)).total_seconds(), 0.0)
        except (TypeError, ValueError):
            return None


class Http:
    """One opener with a cookie jar kept in memory only; one request at a time; every cookie value is masked."""

    def __init__(self, scrub):
        self.scrub = scrub
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", AGENT)]
        self.searched = -1e9

    def open(self, url, data=None, headers=None):
        """The answer (an HTTPError is an answer too; a network error raises BadFile); the caller closes it."""
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            answer = self.opener.open(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as error:
            answer = error
        except (urllib.error.URLError, OSError, HTTPException, ValueError) as error:
            raise BadFile("network: %s %s" % (type(error).__name__, getattr(error, "reason", ""))) from None
        finally:
            for cookie in self.jar:
                self.scrub.add(cookie.value)
        return answer

    def json(self, url, body):
        """A search: at least SEARCH_PAUSE after the previous one."""
        pause = SEARCH_PAUSE - (time.monotonic() - self.searched)
        if pause > 0:
            _wait(pause)
        self.searched = time.monotonic()
        answer = self.open(url, json.dumps(body).encode(), {"Content-Type": "application/json",
                                                            "Accept": "application/json"})
        with answer:
            status = answer.getcode()
            if status in (429, 503):
                raise Throttled(status, _retry_after(answer.headers))
            try:
                raw = answer.read(100_000_000)
            except (OSError, HTTPException, ValueError) as error:
                raise BadFile("network: %s while reading the search" % type(error).__name__) from None
        if status != 200:
            raise BadFile("the search answered HTTP %d" % status)
        try:
            return json.loads(raw)
        except ValueError:
            raise BadFile("the search answered something not JSON") from None


# Planning

MAINLAND = re.compile(r"(?P<product>MD[TS])-50cm-(?P<sheet>\d{6})-(?P<block>\d{2})-(?P<year>\d{4})")
AZORES = re.compile(r"(?P<year>\d{4})_(?P<island>[A-Z]{3})_(?P<places>(?:[A-Z]{3}_){1,6})(?P<sheet>[0-9A-Z][0-9A-Z_-]*?)"
                    r"_(?P<version>\d{2})_(?P<product>MDE|MDS)")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,200}")


def sheet_of(collection, item_id, version):
    """(sheet key, folder, version as a number, year) of an item; of the items of one key only the newest (year,
    then version) is fetched. Mainland ids are MD?-50cm-<sheet>-<block>-<year> with the version in the item's
    properties ("01".."03"); the key holds the block: on 2026-11-15 nine sheets had two items, of two blocks and
    years (213437-213442: block 07 of 2025 and block 09 of 2024, of different sizes), both kept (the older may
    cover what the newer lacks). Azores ids are <year>_<island>_<places>_<sheet>_<version>_<product>, with one to
    four municipalities (a sheet over a border names each) and sheets like 31-2-3-4, 22A-4-5-3 or 21A-4_1-4; the key
    is the island and the sheet (all 2024, version 01 on 2026-11-15)."""
    match = MAINLAND.fullmatch(item_id)
    if match:
        return ((collection, match["sheet"], match["block"]), match["sheet"][:3],
                int(version) if (version or "").isdigit() else 0, int(match["year"]))
    match = AZORES.fullmatch(item_id)
    if match:
        return ((collection, match["island"], match["sheet"]), match["island"],
                int(match["version"]), int(match["year"]))
    return (collection, item_id), "other", int(version) if (version or "").isdigit() else 0, 0


def _bbox_filter(bbox):
    south, north, west, east = bbox
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"filter-lang": "cql2-json",
            "filter": {"op": "s_intersects", "args": [{"property": "geometry"},
                                                      {"type": "Polygon", "coordinates": [ring]}]}}


def walk(http, collection, bbox, log):
    """Every item of a collection (over bbox), as (items by id, the search's own count)."""
    body = {"collections": [collection], "limit": PAGE, "fields": FIELDS}
    if bbox:
        body.update(_bbox_filter(bbox))
    items, matched, pages = {}, None, 0
    while body is not None:
        if STOP.is_set():
            raise Stopped()
        answer = http.json(SITE + SEARCH, body)
        pages += 1
        matched = (answer.get("context") or {}).get("matched", matched)
        features = answer.get("features") or []
        for feature in features:
            items[feature.get("id")] = feature
        following = [link for link in answer.get("links") or [] if link.get("rel") == "next"]
        # the link's href is ".../search?undefined": its body (with the paging token) goes to the search itself
        body = following[0].get("body") if following and features and isinstance(following[0].get("body"), dict) \
            else None
        if pages % 20 == 0:
            log(collection, ": page", pages, ",", len(items), "items of", matched)
    return items, matched


def plan(args, scrub, log):
    area = os.path.join(args.out, "portugal")
    os.makedirs(area, exist_ok=True)
    log.path = os.path.join(area, "plan.log")
    http = Http(scrub)
    rows, summary = [], {"made": now(), "bbox": args.bbox, "collections": {}}
    for collection in args.collections:
        items, matched = walk(http, collection, args.bbox, log)
        newest, skipped = {}, 0
        for item_id, feature in items.items():
            if not isinstance(item_id, str) or not SAFE_ID.fullmatch(item_id):
                skipped += 1
                log("an item id that cannot name a file, left out:", repr(item_id)[:80])
                continue
            props = feature.get("properties") or {}
            key, folder, version, year = sheet_of(collection, item_id, props.get("version"))
            asset = next((name for name, a in (feature.get("assets") or {}).items()
                          if isinstance(a, dict) and "/download/" in str(a.get("href", ""))), None)
            if asset is None:
                skipped += 1
                log(item_id, ": no download asset, left out")
                continue
            size = props.get("file:size")
            row = {"collection": collection, "id": item_id, "sheet": "_".join(key[1:]), "folder": folder,
                   "version": version, "year": year, "datetime": props.get("datetime"),
                   "size": size if isinstance(size, int) and size > 0 else None, "asset": asset}
            order = (year, version, row["datetime"] or "", item_id)
            if key not in newest or order > newest[key][0]:
                newest[key] = (order, row)
        kept = sorted((row for _, row in newest.values()), key=lambda r: (r["folder"], r["id"]))
        rows += kept
        size = sum(r["size"] or 0 for r in kept)
        summary["collections"][collection] = {
            "matched": matched, "found": len(items), "files": len(kept), "older_versions": len(items) - len(kept) -
            skipped, "left_out": skipped, "bytes": size, "without_size": sum(1 for r in kept if r["size"] is None)}
        log("%s: %d items (the search counts %s), %d files after keeping the newest version of each sheet, "
            "%.1f GB" % (collection, len(items), matched, len(kept), size / 1e9))
        if matched is not None and matched != len(items):
            log("WARNING: %s: the walk found %d items, the search counts %s: run plan again" % (
                collection, len(items), matched), error=True)
    files = len(rows)
    total = sum(r["size"] or 0 for r in rows)
    seconds = total / RATE + files * args.pause
    summary.update(files=files, bytes=total, pause=args.pause, rate=RATE,
                   days_at_measured_rate=round(seconds / 86400, 1))
    path = os.path.join(area, "manifest.jsonl")
    with open(path + ".part", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    os.replace(path + ".part", path)
    _write_json(os.path.join(area, "plan.json"), summary)
    log("manifest: %d files, %.2f TB; about %.1f days at %.1f MB/s with a pause of %g s" % (
        files, total / 1e12, seconds / 86400, RATE / 1e6, args.pause))
    return EXIT_OK


# Fetching

def _is_login(url, body_start, headers):
    path = urllib.parse.urlsplit(url or "").path
    kind = (headers.get("Content-Type") or "").lower() if headers else ""
    return ("/realms/" in path or "openid-connect" in path or path.startswith("/auth/login")
            or "text/html" in kind or body_start.lstrip()[:1] == b"<")


class Job:
    """What a fetch run needs of its source: items (id, path, size, group), how an item's address is found, how to
    sign in. The base is a plain list."""

    signin_needed = False

    def __init__(self, area, items, magic):
        self.area, self.items, self.magic = area, items, magic

    def signin(self, http, log):
        pass

    def address(self, http, item, pending):
        return item["url"]

    def forget(self, item):
        pass


class CddJob(Job):
    signin_needed = True

    def __init__(self, area, items, user, password):
        super().__init__(area, items, TIFF_MAGIC)
        self.user, self.password = user, password
        self.addresses = {}  # id -> (address, when resolved): in memory only

    def signin(self, http, log):
        """The Keycloak form as the site leads to it; raises CredentialsRefused when the form comes back."""
        http.jar.clear()
        self.addresses.clear()
        with http.open(SITE + "/") as answer:
            answer.read(2_000_000)
        with http.open(SITE + "/auth/login") as answer:
            page_url, body = answer.geturl(), answer.read(2_000_000)
        form = _login_form(body)
        if form is None:
            with http.open(AUTH_URL) as answer:
                page_url, body = answer.geturl(), answer.read(2_000_000)
            form = _login_form(body)
        if form is None:
            raise BadFile("no login form found")
        action, hidden = form
        fields = dict(hidden)
        fields.update(username=self.user, password=self.password)
        fields.setdefault("credentialId", "")
        with http.open(urllib.parse.urljoin(page_url, action), urllib.parse.urlencode(fields).encode(),
                       {"Content-Type": "application/x-www-form-urlencoded"}) as answer:
            status = answer.getcode()
            body = answer.read(2_000_000)
        if b"kc-form-login" in body:
            raise CredentialsRefused()
        if status >= 400:
            raise BadFile("the sign-in answered HTTP %d" % status)
        log("signed in")

    def address(self, http, item, pending):
        found = self.addresses.get(item["id"])
        if found is None or time.monotonic() - found[1] > ADDRESS_SECONDS:
            batch = [item] + list(itertools.islice(
                (other for other in pending if other["collection"] == item["collection"] and other["id"] != item["id"]
                 and other["id"] not in self.addresses), RESOLVE_BATCH - 1))
            ids = [other["id"] for other in batch]
            answer = http.json(SITE + SEARCH, {"collections": [item["collection"]], "ids": ids, "limit": len(ids),
                                               "fields": {"include": ["id", "assets"], "exclude": ["geometry",
                                                                                                    "links"]}})
            when = time.monotonic()
            for feature in answer.get("features") or []:
                other = next((o for o in batch if o["id"] == feature.get("id")), None)
                asset = (feature.get("assets") or {}).get(other["asset"] if other else "data")
                if other and isinstance(asset, dict) and asset.get("href"):
                    href = urllib.parse.urljoin(SITE, asset["href"])
                    self.addresses[other["id"]] = (href, when)
            found = self.addresses.get(item["id"])
        if found is None:
            raise BadFile("the search does not give this item any more")
        del self.addresses[item["id"]]  # used once: a retry asks for a fresh address
        return found[0]

    def forget(self, item):
        self.addresses.pop(item["id"], None)


def _login_form(body):
    """(action, hidden fields) of Keycloak's form `kc-form-login` (its attributes in any order), or None."""
    match = next((m for m in re.finditer(rb"<form\b[^>]*>", body) if b'id="kc-form-login"' in m.group(0)), None)
    if match is None:
        return None
    action = re.search(rb"\baction=\"([^\"]+)\"", match.group(0))
    if action is None:
        return None
    rest = body[match.end():]
    rest = rest[:rest.find(b"</form>")] if b"</form>" in rest else rest
    hidden = []
    for field in re.finditer(rb"<input\b[^>]*>", rest):
        attrs = dict((k.decode(), html.unescape(v.decode())) for k, v in
                     re.findall(rb"\b(type|name|value)=\"([^\"]*)\"", field.group(0)))
        if attrs.get("type") == "hidden" and attrs.get("name"):
            hidden.append((attrs["name"], attrs.get("value", "")))
    return html.unescape(action.group(1).decode()), hidden


def download(http, url, part, size, magic, min_free, sign_aware):
    """One GET of url into part, checked: (bytes, sha256). Raises SessionLost, Throttled, Stale, BadFile,
    DiskLow, Stopped; the .part is removed on any failure."""
    answer = http.open(url)
    with answer:
        status = answer.getcode()
        headers = answer.headers
        if status in (429, 503):
            raise Throttled(status, _retry_after(headers))
        if sign_aware and status in (401, 403):
            raise SessionLost()
        if status in (404, 410):
            raise Stale("HTTP %d" % status)
        if status != 200:
            raise BadFile("HTTP %d" % status)
        try:
            first = answer.read(8)
        except (OSError, ValueError, HTTPException) as error:
            raise BadFile("%s while reading" % type(error).__name__) from None
        if sign_aware and _is_login(answer.geturl(), first, headers):
            raise SessionLost()
        if not any(first.startswith(m) for m in magic):
            raise BadFile("not the expected file (it starts %r)" % first[:4])
        length = headers.get("Content-Length")
        if size is not None and length is not None and length.isdigit() and int(length) != size:
            raise BadFile("the server's file has %s bytes, %d expected (the data has changed?)" % (length, size))
        digest, done, checked = hashlib.sha256(first), len(first), len(first)
        try:
            with open(part, "wb") as f:
                f.write(first)
                while True:
                    if STOP.is_set():
                        raise Stopped()
                    cap = CHUNK if size is None else min(CHUNK, size - done + 1)
                    chunk = answer.read(cap)
                    if not chunk:
                        break
                    done += len(chunk)
                    if size is not None and done > size:
                        raise BadFile("more than the %d bytes expected (the data has changed?)" % size)
                    digest.update(chunk)
                    f.write(chunk)
                    if done - checked >= DISK_EVERY:
                        checked = done
                        if shutil.disk_usage(os.path.dirname(part)).free < min_free:
                            raise DiskLow()
            expected = size if size is not None else int(length) if length and length.isdigit() else None
            if expected is not None and done != expected:
                raise BadFile("cut short: %d of %d bytes" % (done, expected))
        except (OSError, ValueError, HTTPException) as error:
            _remove(part)
            raise BadFile("%s while reading" % type(error).__name__) from None
        except BaseException:
            _remove(part)
            raise
    return done, digest.hexdigest()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _magic_ok(path, magic):
    try:
        with open(path, "rb") as f:
            start = f.read(8)
    except OSError:
        return False
    return any(start.startswith(m) for m in magic)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Run:
    """The state of one fetch run: done items, counters, status.json."""

    def __init__(self, job, log, pause):
        self.job, self.log, self.pause = job, log, pause
        self.done = {row["id"]: row for row in _read_jsonl(os.path.join(job.area, "done.jsonl"))}
        self.failed = {}
        self.last_error = None
        self.started, self.files, self.bytes = time.monotonic(), 0, 0
        self.state = "running"
        old = os.path.join(job.area, "status.json")
        if os.path.exists(old):
            try:
                with open(old, encoding="utf-8") as f:
                    self.last_error = json.load(f).get("last_error")
            except (OSError, ValueError):
                pass

    def record_done(self, item, size, sha):
        row = {"id": item["id"], "group": item["group"], "path": item["path"], "size": size, "sha256": sha,
               "time": now()}
        _append_jsonl(os.path.join(self.job.area, "done.jsonl"), row)
        self.done[item["id"]] = row

    def record_failed(self, item, reason):
        text = self.log.scrub.text(reason)
        self.failed[item["id"]] = text
        self.last_error = {"time": now(), "id": item["id"], "error": text}
        _append_jsonl(os.path.join(self.job.area, "failed.jsonl"), dict(self.last_error))

    def status(self):
        groups = {}
        for item in self.job.items:
            g = groups.setdefault(item["group"], {"files": 0, "done": 0, "bytes_done": 0, "bytes_left": 0,
                                                  "failed_this_run": 0})
            g["files"] += 1
            if item["id"] in self.done:
                g["done"] += 1
                g["bytes_done"] += self.done[item["id"]].get("size") or 0
            else:
                g["bytes_left"] += item["size"] or 0
                g["failed_this_run"] += item["id"] in self.failed
        elapsed = time.monotonic() - self.started
        rate = self.bytes / elapsed if self.bytes and elapsed > 0 else None
        left = sum(g["bytes_left"] for g in groups.values())
        return {"updated": now(), "state": self.state, "groups": groups, "last_error": self.last_error,
                "this_run": {"files": self.files, "bytes": self.bytes, "seconds": round(elapsed),
                             "bytes_per_second": round(rate) if rate else None},
                "seconds_left": round(left / rate) if rate else None}

    def save(self):
        _write_json(os.path.join(self.job.area, "status.json"), self.status())


def _check_disk(area, need):
    return shutil.disk_usage(area).free >= need


def fetch_run(job, args, http, log):
    """Fetch every item of job not yet done (see the module's docstring); the exit code."""
    run = Run(job, log, args.pause)
    skipped, present, paths = set(), set(), {item["path"] for item in job.items}
    for root, _, files in os.walk(job.area):  # one walk, not a look per item (a network share is slow)
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), job.area).replace(os.sep, "/")
            if rel.endswith(".part") and rel[:-5] in paths:
                _remove(os.path.join(root, name))  # left by a kill: fetched again
            elif rel in paths:
                present.add(rel)
    for item in job.items:  # a file renamed but not recorded (a kill between): hashed and recorded
        path = os.path.join(job.area, item["path"])
        if item["id"] not in run.done and item["path"] in present:
            size = os.path.getsize(path)
            if _magic_ok(path, job.magic) and (item["size"] is None or size == item["size"]):
                run.record_done(item, size, _sha256(path))
                log(item["id"], ": on disk, recorded")
            else:
                skipped.add(item["id"])
                log(item["id"], ": a file on disk that does not check, left as it is (move it away to fetch it again)",
                    error=True)
    pending = deque(item for item in job.items if item["id"] not in run.done and item["id"] not in skipped)
    if args.limit is not None:
        pending = deque(list(pending)[:args.limit])
    log("%d files to fetch, %d done before" % (len(pending), len(run.done)))
    attempts, failed_in_row, signins, code = {}, 0, 0, EXIT_OK
    min_free = args.min_free_gb * 1e9
    try:
        if pending and job.signin_needed:
            signins += 1
            job.signin(http, log)
        first = True
        while pending and not STOP.is_set():
            item = pending.popleft()
            if not first:
                _wait(args.pause)
                if STOP.is_set():
                    pending.appendleft(item)
                    break
            first = False
            if not _check_disk(job.area, min_free + (item["size"] or 0)):
                raise DiskLow()
            attempts[item["id"]] = attempts.get(item["id"], 0) + 1
            path = os.path.join(job.area, item["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            renewed, throttled, error = False, 0, None
            started = time.monotonic()
            while True:
                try:
                    url = job.address(http, item, pending)
                    size, sha = download(http, url, path + ".part", item["size"], job.magic, min_free,
                                         job.signin_needed)
                    break
                except Throttled as t:
                    throttled += 1
                    if throttled >= THROTTLE_TRIES:
                        error = "HTTP 429/503 %d times" % throttled
                        break
                    seconds = min(max(WAIT_BASE * 2 ** (throttled - 1), t.retry_after or 0), WAIT_MAX)
                    log(item["id"], ": the server asks to slow down (%s), waiting %d s" % (t, seconds))
                    _wait(seconds)
                    if STOP.is_set():
                        raise Stopped()
                except SessionLost:
                    if renewed:
                        error = "the session ended again right after a sign-in"
                        break
                    if signins >= MAX_SIGNINS:
                        log("%d sign-ins in a row without a fetched file: stopping" % signins, error=True)
                        code = EXIT_SIGNINS
                        raise Stopped()
                    log(item["id"], ": the session has ended, signing in again")
                    renewed = True
                    signins += 1
                    job.signin(http, log)
                except Stale as e:
                    if renewed:
                        error = str(e)
                        break
                    renewed = True
                    job.forget(item)
                except BadFile as e:
                    error = str(e)
                    break
            if error is None:
                os.replace(path + ".part", path)
                run.record_done(item, size, sha)
                run.files += 1
                run.bytes += size
                failed_in_row = signins = 0
                seconds = time.monotonic() - started
                log("%s: %.1f MB in %.1f s; %d of %d done" % (
                    item["id"], size / 1e6, seconds, len(run.done), len(job.items)))
                if run.files % STATUS_EVERY == 0:
                    run.save()
                continue
            job.forget(item)
            run.record_failed(item, error)
            failed_in_row += 1
            log(item["id"], ": failed (%s), attempt %d" % (error, attempts[item["id"]]), error=True)
            run.save()
            if failed_in_row >= MAX_FAILED_IN_ROW:
                log("%d failed files in a row: stopping (the server may be down; run again later)" % failed_in_row,
                    error=True)
                code = EXIT_FAILURES
                break
            if attempts[item["id"]] <= args.retries:
                pending.append(item)
    except Stopped:
        pass
    except DiskLow:
        log("less than %g GB free (with the next file) in %s: stopping" % (args.min_free_gb, job.area), error=True)
        code = EXIT_DISK
    except CredentialsRefused:
        log("the sign-in was refused: check CDD_USER and CDD_PASSWORD", error=True)
        code = EXIT_CREDENTIALS
    except Throttled as t:
        log("the server refused the sign-in or a search for now (%s): run again later" % t, error=True)
        code = EXIT_FAILURES
    except BadFile as e:
        log("the sign-in or a search failed: %s" % e, error=True)
        code = EXIT_FAILURES
    left = sum(1 for item in job.items if item["id"] not in run.done)
    if STOP.is_set() and code == EXIT_OK:
        run.state = "stopped by a signal"
    elif code != EXIT_OK:
        run.state = "stopped (exit code %d)" % code
    else:
        run.state = "finished" if left == 0 else "finished this run, %d left" % left
    run.save()
    log("%s: %d files (%.2f GB) this run, %d left" % (run.state, run.files, run.bytes / 1e9, left))
    return code


def _portugal_items(area, collections):
    path = os.path.join(area, "manifest.jsonl")
    if not os.path.exists(path):
        return None
    items = []
    for row in _read_jsonl(path):
        if collections and row["collection"] not in collections:
            continue
        if not SAFE_ID.fullmatch(row["id"]) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", row["folder"]):
            continue
        items.append({"id": row["id"], "group": row["collection"], "collection": row["collection"],
                      "path": "%s/%s/%s.tif" % (row["collection"], row["folder"], row["id"]),
                      "size": row.get("size"), "asset": row.get("asset") or "data"})
    return items


def _list_items(name):
    spec = LISTS[name]
    items = []
    for group, url, size in spec["files"]:
        file_name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        items.append({"id": file_name, "group": group, "path": file_name, "size": size, "url": url})
    return items


def _install_handlers():
    """SIGTERM and SIGINT set STOP; the previous handlers, to restore."""
    old = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            old[sig] = signal.signal(sig, lambda *_: STOP.set())
        except (ValueError, OSError):  # not the main thread
            pass
    return old


def _restore(old):
    for sig, handler in old.items():
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, TypeError):
            pass


def fetch(args, scrub, log):
    area = os.path.join(args.out, "portugal")
    user, password = os.environ.get("CDD_USER"), os.environ.get("CDD_PASSWORD")
    scrub.add(user)
    scrub.add(password)
    items = _portugal_items(area, args.collections)
    if items is None:
        log("no manifest in %s: run `plan` first" % area, error=True)
        return EXIT_ERROR
    log.path = os.path.join(area, "fetch.log")
    if not user or not password:
        log("CDD_USER and CDD_PASSWORD must be set in the environment", error=True)
        return EXIT_CREDENTIALS
    return fetch_run(CddJob(area, items, user, password), args, Http(scrub), log)


def fetch_list(args, scrub, log):
    spec = LISTS[args.name]
    area = os.path.join(args.out, spec["folder"])
    os.makedirs(area, exist_ok=True)
    log.path = os.path.join(area, "fetch.log")
    log("list %s (addresses and sizes read %s)" % (args.name, spec["read"]))
    return fetch_run(Job(area, _list_items(args.name), spec["magic"]), args, Http(scrub), log)


# Status

def _area_status(area, items):
    done = {row["id"]: row for row in _read_jsonl(os.path.join(area, "done.jsonl"))}
    saved = {}
    if os.path.exists(os.path.join(area, "status.json")):
        try:
            with open(os.path.join(area, "status.json"), encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            pass
    lines, left_bytes = [], 0
    groups = {}
    for item in items:
        g = groups.setdefault(item["group"], [0, 0, 0, 0])
        g[0] += 1
        if item["id"] in done:
            g[1] += 1
            g[2] += done[item["id"]].get("size") or 0
        else:
            g[3] += item["size"] or 0
    for name, (files, n, done_bytes, left) in groups.items():
        left_bytes += left
        lines.append("  %-14s %7d of %7d files, %8.1f GB done, %8.1f GB left" % (
            name, n, files, done_bytes / 1e9, left / 1e9))
    rate = (saved.get("this_run") or {}).get("bytes_per_second")
    lines.append("  state: %s (%s)" % (saved.get("state", "not started"), saved.get("updated", "-")))
    if rate:
        lines.append("  measured rate %.1f MB/s with pauses: about %.1f days left" % (
            rate / 1e6, left_bytes / rate / 86400))
    if saved.get("last_error"):
        e = saved["last_error"]
        lines.append("  last error: %s %s: %s" % (e.get("time"), e.get("id"), e.get("error")))
    return lines


def status(args, scrub, log):
    shown = False
    area = os.path.join(args.out, "portugal")
    items = _portugal_items(area, None)
    if items is not None:
        print("portugal (%s)" % area)
        for line in _area_status(area, items):
            print(scrub.text(line))
        shown = True
    for name, spec in LISTS.items():
        area = os.path.join(args.out, spec["folder"])
        if os.path.isdir(area):
            print("%s (%s)" % (name, area))
            for line in _area_status(area, _list_items(name)):
                print(scrub.text(line))
            shown = True
    if not shown:
        print("nothing planned or fetched in %s yet" % args.out)
    return EXIT_OK


# Command line

def _parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", default=default_out(), help="the folder of the data (default: downloads/ beside "
                                                            "the script)")
        return p

    p = common(sub.add_parser("plan", help="list every file of the collections (public search)"))
    p.add_argument("--collections", nargs="+", default=list(COLLECTIONS))
    p.add_argument("--bbox", nargs=4, type=float, metavar=("S", "N", "W", "E"))
    p.add_argument("--pause", type=float, default=3.0, help="the pause the time estimate assumes")
    for name in ("fetch", "fetch-list"):
        p = common(sub.add_parser(name, help="fetch the planned files" if name == "fetch" else
                                  "fetch a named list of plain addresses (%s)" % ", ".join(LISTS)))
        if name == "fetch-list":
            p.add_argument("name", choices=sorted(LISTS))
        else:
            p.add_argument("--collections", nargs="+", help="only these collections of the manifest")
        p.add_argument("--pause", type=float, default=3.0, help="seconds between files (default 3)")
        p.add_argument("--retries", type=int, default=2, help="tries of a failed file in this run after its first")
        p.add_argument("--min-free-gb", type=float, default=50.0, help="stop under this free space (default 50)")
        p.add_argument("--limit", type=int, help="at most this many files (a trial)")
    common(sub.add_parser("status", help="files and bytes done and left, the last error"))
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    scrub = Scrub()
    log = Log(scrub)
    STOP.clear()
    old = _install_handlers()
    try:
        command = {"plan": plan, "fetch": fetch, "fetch-list": fetch_list, "status": status}[args.command]
        return command(args, scrub, log)
    except Stopped:
        log("stopped")
        return EXIT_OK
    except Exception as error:  # never a traceback: it could carry an address
        log("error: %s: %s" % (type(error).__name__, error), error=True)
        return EXIT_ERROR
    finally:
        _restore(old)


if __name__ == "__main__":
    sys.exit(main())
