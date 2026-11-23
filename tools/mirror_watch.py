"""
Whether the providers of the mirror's datasets have published something new (run by hand, or by the monthly workflow
.github/workflows/mirror-watch.yml; never by the app): docs/mirror-hosting/watch.md. The mirror serves our own tiles of
datasets whose providers publish them only as huge files (tools/sk_tiles.py, tools/mirror_tiles.py), and nothing else
notices when a provider replaces such a file or publishes a successor. Standard library only, Python 3.11 or newer, no
import of this project: it runs in a stock Python (a CI runner's python3) without the project's dependencies.

Two kinds of change, two checks. WATCH names each dataset's signals; a signal several datasets share is read once a
run, and each address is asked once (a feed read for its enclosures and for its entries is one request):
1. The same file replaced (a correction at the same address):
   File      a HEAD of the file: its size (Content-Length), Last-Modified and ETag against the baseline. An HTML page
             answering instead of the file (a challenge or a login page served with 200) is a provider that does not
             answer, never a change.
   Feed      an ATOM feed, where the provider's HEAD gives no size or date (SPW's): the entries whose id matches the
             signal's pattern, their `updated` and each of their enclosures' `length`. The feed's own `updated` is
             not compared (it moves when the feed is rewritten, the files staying).
2. A successor published at another address (a new survey cycle, a new campaign, a new model), which a HEAD on the
   old file never sees:
   Listing   a page, feed or record reduced to the sorted set of the strings its patterns extract (links, titles,
             dates, a count; a pattern's groups joined by a space): a string added or removed is reported.

What counts as the same file, and why each field is compared:
- size: a file of another size is another file, the plainest sign of a replacement;
- ETag: the server's own name of the file's version (nginx's and IIS's change with the file's time and size), so
  another ETag means another file even at the same size; a weak and a strong form of one tag (W/"x" and "x", as a
  proxy or compression may switch them) are the same;
- Last-Modified, also when it differs alone (same size, same ETag): a file rewritten at the same size, on a server
  whose ETag does not follow the content, shows only in its date. Nothing cleverer is decided: a report costs the user
  a look, a missed change costs stale tiles; a date that moved over the same file is ended with `adopt`.
Whatever was readable is compared. A field or a piece (a Feed's enclosure length, an entry's `updated`) the baseline
has and the answer lacks makes the signal not checkable when nothing readable differs; when something does, it is
changed and the missing piece is named beside it ("-> none"). A field the baseline recorded as absent (the provider
sent none when it was adopted) and the answer now has is a change ("none -> <value> (a new field)"), said until it is
adopted. A Feed's enclosure gone or new is a change; a Listing compares its set.

    python tools/mirror_watch.py check [dataset ...] [--baseline FILE] [--json] [--json-out FILE] [--previous FILE]
    python tools/mirror_watch.py adopt dataset ... [--baseline FILE]
    python tools/mirror_watch.py list [--baseline FILE]

The baseline (--baseline, by default mirror_watch.json beside the script, committed) holds one record per signal, keyed
by its kind and address: what was read (the size, Last-Modified and ETag; the entries' `updated` and the enclosures'
lengths; the listing's set), how (a Feed's entry pattern, a Listing's patterns) and the date it was read. Public facts
of providers only.

check: every signal of the datasets named (all by default) read once, then one line per dataset: `same`, `changed:
<what>: <from> -> <to>; ...` (every difference), `not checkable: <signal>: <why>; ...` (no answer, a refusal, a
status other than 200 (redirects are not followed: a 3xx names its target without a query), an answer cut short of
its Content-Length or larger than MAX_BODY, an HTML page for a file, an answer without a field the baseline has, a
feed that is not XML or has no matching entry, a page from which the patterns extract nothing, any other failure of
the answer's reading (its kind and a short text), the run's time up (RUN_SECONDS), no baseline record, a record read
another way). A provider that does not answer is never a change, and a change is never hidden by another signal's
failure: a dataset with both says both, ` | ` between them. A dataset without a Listing says `check 2: none` on its
line. --json prints the result as JSON instead of the lines; --json-out FILE writes that JSON to FILE after the lines
(a failed write is said in one line: exit 2 when nothing else made the exit code). --previous FILE reads the result of
the run before (a --json-out file): a dataset not checkable now that was checkable (or absent) then is `not checkable
(first time)` and does not make the exit code 3; not checkable in both runs does. A missing or unreadable previous
file is said in one line and taken as no previous run. Without --previous every not checkable dataset counts.

adopt: reads the signals of the datasets named and rewrites their records (through a temporary file and a rename),
printing what changed and, for a signal shared with other datasets, whose baseline moved with it; records of signals
no longer in WATCH are dropped. It refuses (exit 3, the file as it was) when any of those signals is not checkable or
lacks a piece its record needs (a File's size, a Feed's length or `updated`). It is how the first baseline is made and
how the user accepts a change he has looked at; nothing runs it by itself.

list: the rows: each dataset's signals, their addresses and the date their record was read.

Exit codes: 1 when any dataset changed; else 3 when any is not checkable (not counting a first time with --previous);
else 0; 2 for usage, an unreadable baseline, a --json-out that could not be written (when nothing else made the code)
or the tool's own failure.

Requests: a HEAD for a File (never a GET: no data file is ever downloaded), a GET for a Feed or a Listing (read up to
MAX_BODY), one at a time, each at least REQUEST_PAUSE after the previous answer (or failure) from the same host,
TIMEOUT seconds at most a socket wait, none started (and no body read on) after RUN_SECONDS of the run, only https,
with the tool's User-Agent and nothing else of the machine (no cookies, no proxy: it connects directly). The output
holds only provider addresses and the facts above; a request's error is named by its kind, a reader's by its kind and
a short text of the parser's. It never recuts, never adopts by itself and writes nothing but the baseline (adopt) and
--json-out.

A scheduler runs `check --previous <the last run's result> --json-out <this run's result>` and keeps the result for the
next run: exit 1 means a provider changed something (the user looks: a new edition or `adopt`, docs/mirror-hosting/
watch.md); exit 3 a provider not answering two runs in a row (a look by hand from another network); exit 2 a broken
job. The monthly workflow does that, keeping the result as an artifact.
"""

import argparse
import dataclasses
import datetime
import html
import http.client
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import ClassVar, Dict, List, Optional, Tuple

AGENT = "Find-a-Line/0.1 (highline finder; mirror watch)"
REQUEST_PAUSE = 1.5      # seconds between an answer and the next request to the same host
TIMEOUT = 60             # seconds a socket may wait
RUN_SECONDS = 600        # a run's time: no request started, no body read on after it (the job allows 15 min)
MAX_BODY = 20_000_000    # bytes of a page, feed or record read at most; a larger answer is not checkable
CHUNK = 1 << 16          # bytes of a body read at a time (the run's time checked between them)
SCHEMES = {"https"}      # the only scheme asked (the tests' local server adds http)
HTML_TYPES = ("text/html", "application/xhtml+xml")   # a File answered by a page: not the file
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mirror_watch.json")
FORMAT = 1               # of the --json result
ATOM = "{http://www.w3.org/2005/Atom}"
EXIT_SAME, EXIT_CHANGED, EXIT_USAGE, EXIT_NOT_CHECKABLE = 0, 1, 2, 3
DEFAULT_PORTS = {"https": 443, "http": 80}
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
DIGITS = re.compile(r"[0-9]+")

_clock = time.monotonic  # the pacing's and the run's clock
_wait = time.sleep


# The signals

@dataclasses.dataclass(frozen=True)
class File:
    """A provider's file, asked with a HEAD: its size, Last-Modified and ETag."""
    url: str
    label: str = ""   # the name in the output; by default the file's name
    kind: ClassVar[str] = "file"


@dataclasses.dataclass(frozen=True)
class Feed:
    """An ATOM feed: the entries whose <id> matches `entries` (re.search), their <updated> and the `length` of each of
    their enclosures."""
    url: str
    entries: str
    label: str = ""
    kind: ClassVar[str] = "feed"


@dataclasses.dataclass(frozen=True)
class Listing:
    """A page, feed or record reduced to the set of the strings its patterns extract (re.finditer over the decoded
    text; a pattern's groups joined by a space, entities decoded, white space collapsed)."""
    url: str
    patterns: Tuple[str, ...]
    label: str = ""
    kind: ClassVar[str] = "listing"


def key_of(signal) -> str:
    """A signal's record in the baseline: its kind and address."""
    return f"{signal.kind} {signal.url}"


def name_of(signal) -> str:
    return signal.label or urllib.parse.urlsplit(signal.url).path.rsplit("/", 1)[-1] or signal.url


# What each kind compares, and how it was read (a record read another way is not compared)
FIELDS = {"file": ("size", "last_modified", "etag"), "feed": ("updated", "lengths"), "listing": ("items",)}
HOW = {"file": (), "feed": ("entries",), "listing": ("patterns",)}
META = ("kind", "url", "read")

# The providers. Slovakia: ÚGKK SR's national ZIPs of DMR 5.0 and DMP 1.0 (tools/sk_tiles.py) and its provision page
# of the LLS products: its data ZIPs, the lots of the second cycle (DMR 6.0, DMP 2.0) and the national models; a new
# lot or a national second-cycle ZIP is the successor. Left out: the footprint archives (LLS/Footprints/), the
# overview archives (on www.skgeodesy.sk) and the INSPIRE copies of the same models in ETRS89 (static/INSPIRE/)
_SK = "https://opendata.skgeodesy.sk/static/LLS/"
DMR5 = File(_SK + "DMR5/DMR5_0_sjtsk03_bpv.zip")
DMP1 = File(_SK + "DMP1/DMP1_0_sjtsk03_bpv.zip")
SK_PAGE = Listing("https://www.skgeodesy.sk/geoportal/zbgis/lls/poskytovanie/",
                  (r"""href=["'](https://opendata\.skgeodesy\.sk/static/LLS/(?!Footprints/)[^"']+\.zip)["']""",),
                  "skgeodesy LLS provision page")
# Madeira: DROTe's two ZIPs (2 m of Madeira; 5 m of the other islands, one file for three datasets) and the SNIG
# record abba9a83 that lists both: its dates and its download links (a CI_OnlineResource of a WWW:DOWNLOAD protocol);
# its contact, organisation, viewer and WMS links are left out
_IRIG = "https://irig-storage.madeira.gov.pt/irig-catalogo/"
MDT_2M = File(_IRIG + "MDT_2m.zip")
MDT_5M = File(_IRIG + "mdt_5m.zip")
SNIG = Listing("https://snig.dgterritorio.gov.pt/rndg/srv/api/records/abba9a83-cb1c-4d2c-ad1d-ccb592247754"
               "/formatters/xml",
               (r"<gco:Date>([^<]+)</gco:Date>", r"<gco:DateTime>([^<]+)</gco:DateTime>",
                r"(?s)<gmd:URL>([^<]+)</gmd:URL>\s*</gmd:linkage>\s*<gmd:protocol>\s*"
                r"<gco:CharacterString>WWW:DOWNLOAD[^<]*</gco:CharacterString>"),
               "SNIG record abba9a83")
# Valle d'Aosta: the region's one ZIP of the DTM 2005/2008 and its geoportal's page of DTM products (the download
# keys `carta=` and the products' information sheets); the download folder itself answers 403
AOSTA_ZIP = File("https://geoprodotti.regione.vda.it/download/DTM0508_002/DTM0508_002_UNICO.zip")
VDA_PAGE = Listing("https://geoportale.regione.vda.it/download/dtm/",
                   (r"geodownload\.asp\?carta=([A-Za-z0-9_]+)", r"metadata_documents/([A-Za-z0-9_.%-]+\.pdf)"),
                   "VdA geoportal DTM page")
# Wallonia: SPW's ATOM feeds of the MNT and the MNS 2021-2022 (a HEAD of their ZIPs gives no size and no date): the
# per-province entry in EPSG:3812 with its five ZIPs (tools/cdd_fetch.py LISTS["wallonia"]); the feeds' entry ids;
# and SPW's metadata catalogue (Metawal's CSW) for the dataset records titled "Relief" and "Wallonie", with their
# count (a count above maxRecords would cut the list)
_SPW = "https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/"
_MNT = _SPW + "a004e570-99d6-4fe5-b83d-49b774409278/atom_dataset.xml"
_MNS = _SPW + "5a4c28fe-d30c-493e-861e-a80ebc703b64/atom_dataset.xml"
_ENTRY_IDS = (r"(?s)<entry\b[^>]*>.*?<id>([^<]+)</id>",)
MNT_FEED = Feed(_MNT, r"_GEOTIFF_3812_PROV$", "SPW MNT feed")
MNS_FEED = Feed(_MNS, r"_GEOTIFF_3812_PROV$", "SPW MNS feed")
MNT_ENTRIES = Listing(_MNT, _ENTRY_IDS, "SPW MNT feed entries")
MNS_ENTRIES = Listing(_MNS, _ENTRY_IDS, "SPW MNS feed entries")
METAWAL = Listing("https://metawal.wallonie.be/geonetwork/srv/fre/csw?service=CSW&version=2.0.2&request=GetRecords"
                  "&typeNames=csw:Record&resultType=results&elementSetName=brief&maxRecords=100&sortBy=Identifier:A"
                  "&constraintLanguage=CQL_TEXT&constraint_language_version=1.1.0&constraint=Title%20like%20%27%25"
                  "Relief%25%27%20AND%20Title%20like%20%27%25Wallonie%25%27%20AND%20Type%20%3D%20%27dataset%27",
                  (r"(numberOfRecordsMatched=\"\d+\")",
                   r"(?s)<dc:identifier[^>]*>([^<]+)</dc:identifier>\s*<dc:title[^>]*>([^<]+)</dc:title>"),
                  "Metawal Relief de la Wallonie records")

# Every dataset on the mirror, or cut for it, with its signals: a dataset is published only with a row here
# (tests/test_mirror_pairs.py); a row may come before its dataset is published
WATCH: Dict[str, Tuple] = {
    "slovakia": (DMR5, DMP1, SK_PAGE),
    "madeira": (MDT_2M, SNIG),
    "porto-santo": (MDT_5M, SNIG),
    "desertas": (MDT_5M, SNIG),
    "selvagens": (MDT_5M, SNIG),
    "aosta": (AOSTA_ZIP, VDA_PAGE),
    "wallonia": (MNT_FEED, MNS_FEED, MNT_ENTRIES, MNS_ENTRIES, METAWAL),
}


class Usage(Exception):
    """Exit 2: a wrong argument, an unreadable baseline."""


class NotCheckable(Exception):
    """A signal that could not be read or compared; its text is the reason shown."""


def signals_of(datasets) -> list:
    """The distinct signals of the datasets, in WATCH's order; two signals of one key must be the same signal."""
    found: Dict[str, object] = {}
    for dataset in datasets:
        for signal in WATCH[dataset]:
            other = found.setdefault(key_of(signal), signal)
            if other != signal:
                raise Usage(f"two signals read one address another way: {key_of(signal)}")
    return list(found.values())


def sharing(signal) -> List[str]:
    return [d for d, row in WATCH.items() if signal in row]


# Requests

def _host(url: str) -> Tuple[str, str]:
    """(scheme, "host:port") with the scheme's default port filled in."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, "%s:%s" % ((parts.hostname or "").lower(), parts.port or DEFAULT_PORTS.get(scheme, ""))


def _plain(url: str) -> str:
    """An address without its query or fragment (a redirect's target may carry a signature)."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _number(text) -> Optional[int]:
    """A whole number written in ASCII digits only (never "²", which str.isdigit takes), else None."""
    text = (text or "").strip()
    return int(text) if DIGITS.fullmatch(text) else None


@dataclasses.dataclass
class Answer:
    status: int
    headers: object       # http.client.HTTPMessage
    body: Optional[bytes]


class Http:
    """One opener without redirects, cookies or a proxy; one request at a time, at least REQUEST_PAUSE after the
    previous answer (or failure) from the same host; each (method, address) asked once a run (its answer or its
    failure kept); nothing asked or read on after RUN_SECONDS from its making."""

    def __init__(self):
        self.opener = urllib.request.OpenerDirector()
        for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(),
                        urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
            self.opener.add_handler(handler)
        self.last: Dict[str, float] = {}
        self.memo: Dict[Tuple[str, str], object] = {}
        self.deadline = _clock() + RUN_SECONDS

    def ask(self, method: str, url: str) -> Answer:
        """The 200 answer to the request; NotCheckable otherwise."""
        key = (method, url)
        if key not in self.memo:
            try:
                self.memo[key] = self._ask(method, url)
            except NotCheckable as failed:
                self.memo[key] = failed
        found = self.memo[key]
        if isinstance(found, NotCheckable):
            raise found
        return found

    def _time_up(self) -> None:
        if _clock() > self.deadline:
            raise NotCheckable("the run's time was up")

    def _ask(self, method: str, url: str) -> Answer:
        scheme, host = _host(url)
        if scheme not in SCHEMES:
            raise NotCheckable(f"an address on {scheme or 'no scheme'}: refused (only {', '.join(sorted(SCHEMES))})")
        self._time_up()
        pause = REQUEST_PAUSE - (_clock() - self.last.get(host, -1e9))
        if pause > 0:
            _wait(pause)
        self._time_up()
        request = urllib.request.Request(url, method=method, headers={"User-Agent": AGENT})
        try:
            try:
                answer = self.opener.open(request, timeout=TIMEOUT)
            except urllib.error.HTTPError as error:  # an answer too
                answer = error
            with answer:
                status, headers = answer.getcode(), answer.headers
                if status != 200:
                    where = headers.get("Location") if 300 <= status < 400 else None
                    target = f" (a redirect to {_plain(urllib.parse.urljoin(url, where))})" if where else ""
                    raise NotCheckable(f"HTTP {status}{target}")
                body = self._body(answer, headers) if method == "GET" else None
        except urllib.error.URLError as error:
            reason = error.reason
            raise NotCheckable("no answer (%s)" % (type(reason).__name__ if isinstance(reason, BaseException)
                                                   else "refused")) from None
        except OSError as error:  # a reset, a timeout, the connection closed without an answer
            raise NotCheckable("no answer (%s)" % type(error).__name__) from None
        except (http.client.HTTPException, ValueError) as error:
            raise NotCheckable("a broken answer (%s)" % type(error).__name__) from None
        finally:
            self.last[host] = _clock()
        return Answer(status, headers, body)

    def _body(self, answer, headers) -> bytes:
        """The whole body, read a CHUNK at a time (one socket read each, the run's time checked between them); an
        answer larger than MAX_BODY or shorter than its Content-Length (the connection closed early: http.client
        returns the short body without an error) is not checkable."""
        chunks, size = [], 0
        while size <= MAX_BODY:
            self._time_up()
            chunk = answer.read1(CHUNK)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_BODY:
            raise NotCheckable(f"the answer is larger than {MAX_BODY} bytes")
        declared = _number(headers.get("Content-Length"))
        if declared is not None and declared != size:
            raise NotCheckable(f"an answer cut short ({size} of {declared} bytes)")
        return b"".join(chunks)


# Reading a signal: its facts (None for a piece the answer lacks), or NotCheckable

def _short(text: str) -> str:
    """The last part of an address or id, for the output."""
    return text.rstrip("/").rsplit("/", 1)[-1] or text


def read_file(http: Http, signal: File) -> Dict:
    headers = http.ask("HEAD", signal.url).headers
    kind = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if kind in HTML_TYPES:
        raise NotCheckable("an HTML page instead of the file")
    return {"size": _number(headers.get("Content-Length")), "last_modified": headers.get("Last-Modified"),
            "etag": headers.get("ETag")}


def read_feed(http: Http, signal: Feed) -> Dict:
    """The matching entries' `updated` and their enclosures' lengths (None where an entry has no readable <updated>
    or an enclosure no readable length); "unaddressed": the entries with an enclosure without an address."""
    body = http.ask("GET", signal.url).body
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise NotCheckable("not XML") from None
    if root.tag != ATOM + "feed":
        raise NotCheckable("not an ATOM feed")
    pattern = re.compile(signal.entries)
    updated, lengths, unaddressed = {}, {}, []
    for entry in root.findall(ATOM + "entry"):
        entry_id = (entry.findtext(ATOM + "id") or "").strip()
        if not pattern.search(entry_id):
            continue
        updated[entry_id] = (entry.findtext(ATOM + "updated") or "").strip() or None
        for link in entry.findall(ATOM + "link"):
            if link.get("rel") != "enclosure":
                continue
            href = (link.get("href") or "").strip()
            if href:
                lengths[href] = _number(link.get("length"))
            else:
                unaddressed.append(entry_id)
    if not updated:
        raise NotCheckable("no entry matches")
    if not lengths:
        raise NotCheckable("no enclosure in the matching entries")
    return {"updated": updated, "lengths": lengths, "unaddressed": unaddressed}


def _text(answer: Answer) -> str:
    charset = answer.headers.get_content_charset() or "utf-8"
    try:
        return answer.body.decode("utf-8-sig" if charset.lower() in ("utf-8", "utf8") else charset, errors="replace")
    except LookupError:
        return answer.body.decode("utf-8-sig", errors="replace")


def extract(signal: Listing, text: str) -> List[str]:
    """The sorted set of the strings the listing's patterns extract from text."""
    found = set()
    for pattern in signal.patterns:
        for match in re.finditer(pattern, text):
            value = " ".join(html.unescape(g) for g in match.groups() if g)
            value = " ".join(value.split())
            if value:
                found.add(value)
    return sorted(found)


def read_listing(http: Http, signal: Listing) -> Dict:
    items = extract(signal, _text(http.ask("GET", signal.url)))
    if not items:
        raise NotCheckable("the patterns found nothing")
    return {"items": items}


READERS = {"file": read_file, "feed": read_feed, "listing": read_listing}


def read(http: Http, signal):
    """(facts, None) or (None, why). Any failure of a reader is that signal's, never the run's."""
    try:
        return READERS[signal.kind](http, signal), None
    except NotCheckable as failed:
        return None, str(failed)
    except Exception as error:  # an encoding XML does not know, a value int() refuses, ...
        text = " ".join(str(error).split())[:80]
        return None, f"a broken answer ({type(error).__name__}{': ' + text if text else ''})"


def lacking(signal, facts: Dict) -> List[str]:
    """What a record would need and the answer lacks: adopt refuses it."""
    if signal.kind == "file":
        return [] if facts["size"] is not None else ["no size: the answer has no Content-Length"]
    if signal.kind == "feed":
        return ([f"entry {_short(k)} has no updated" for k, v in facts["updated"].items() if v is None]
                + [f"{_short(k)} has no length" for k, v in facts["lengths"].items() if v is None]
                + [f"an enclosure of entry {_short(k)} has no address" for k in facts["unaddressed"]])
    return []


def record_of(signal, facts: Dict, day: str) -> Dict:
    """The baseline's record of a signal: META, HOW and FIELDS of its kind, nothing else."""
    record = {"kind": signal.kind, "url": signal.url, "read": day}
    for field in HOW[signal.kind]:
        value = getattr(signal, field)
        record[field] = list(value) if isinstance(value, tuple) else value
    for field in FIELDS[signal.kind]:
        record[field] = facts[field]
    return record


def read_another_way(signal, record: Dict) -> bool:
    expected = record_of(signal, dict.fromkeys(FIELDS[signal.kind]), "")
    return any(record.get(k) != expected[k] for k in ("kind", "url") + HOW[signal.kind])


# Comparing

LABELS = {"size": "size", "etag": "ETag", "last_modified": "Last-Modified"}
ABSENT = {"size": "Content-Length", "etag": "ETag", "last_modified": "Last-Modified"}
PIECES = {"updated": ("entry {} updated", "updated of entry {}"), "lengths": ("{} length", "length of {}")}


def _tag(etag: str) -> str:
    """An ETag without its weak mark: W/"x" and "x" name one version."""
    return etag[2:] if etag.startswith("W/") else etag


def compare(signal, base: Dict, now: Dict) -> Tuple[List[str], List[Tuple[str, str, object]]]:
    """(changes, missing) of a signal's facts now against its record: each change as "<what>: <from> -> <to>", each
    piece the record has and the answer lacks as (what the answer has not, what it is, the recorded value; None when
    there is none to name)."""
    name, changes, missing = name_of(signal), [], []
    if signal.kind == "file":
        for field in ("size", "etag", "last_modified"):
            before, after, what = base.get(field), now.get(field), f"{name} {LABELS[field]}"
            if before is None and after is None:
                continue
            if before is None:
                changes.append(f"{what}: none -> {after} (a new field)")
            elif after is None:
                missing.append((ABSENT[field], what, before))
            elif (_tag(after) != _tag(before)) if field == "etag" else (after != before):
                changes.append(f"{what}: {before} -> {after}")
    elif signal.kind == "feed":
        for field, (shown, absent) in PIECES.items():
            before, after = base.get(field) or {}, now.get(field) or {}
            for key in sorted(set(before) | set(after)):
                what = f"{name} {shown.format(_short(key))}"
                if key not in after:
                    changes.append(f"{what}: {before[key]} -> gone")
                elif key not in before:
                    changes.append(f"{what}: new -> {'none' if after[key] is None else after[key]}")
                elif after[key] is None:
                    missing.append((absent.format(_short(key)), what, before[key]))
                elif after[key] != before[key]:
                    changes.append(f"{what}: {before[key]} -> {after[key]}")
        for entry_id in now.get("unaddressed") or ():
            missing.append((f"address of an enclosure of entry {_short(entry_id)}",
                            f"{name} an enclosure of entry {_short(entry_id)}", None))
    else:
        before, after = set(base.get("items") or ()), set(now.get("items") or ())
        changes += [f"{name} added: {item}" for item in sorted(after - before)]
        changes += [f"{name} removed: {item}" for item in sorted(before - after)]
    return changes, missing


def _gone(missing) -> List[str]:
    """The missing pieces beside a change."""
    return [f"{what}: {before} -> none" if before is not None else f"{what}: unreadable" for _, what, before in missing]


@dataclasses.dataclass
class SignalResult:
    signal: object
    facts: Optional[Dict]
    changed: List[str]
    why: Optional[str]     # not checkable

    @property
    def state(self) -> str:
        return "changed" if self.changed else "not checkable" if self.why else "same"


def judge(signal, record: Optional[Dict], facts: Optional[Dict], why: Optional[str]) -> SignalResult:
    if why is not None:
        return SignalResult(signal, None, [], why)
    if record is None:
        return SignalResult(signal, facts, [], "no baseline record (run adopt)")
    if read_another_way(signal, record):
        return SignalResult(signal, facts, [], "the baseline was read another way (run adopt)")
    changes, missing = compare(signal, record, facts)
    if changes:  # something readable differs: the missing pieces are said beside it
        return SignalResult(signal, facts, changes + _gone(missing), None)
    if missing:
        return SignalResult(signal, facts, [], "the answer has no " + ", ".join(absent for absent, _, _ in missing))
    return SignalResult(signal, facts, [], None)


@dataclasses.dataclass
class DatasetResult:
    name: str
    changed: List[str]
    not_checkable: List[str]
    check_2: bool
    first_time: bool = False

    @property
    def state(self) -> str:
        return "changed" if self.changed else "not checkable" if self.not_checkable else "same"

    def line(self) -> str:
        parts = []
        if self.changed:
            parts.append("changed: " + "; ".join(self.changed))
        if self.not_checkable:
            parts.append(("not checkable (first time): " if self.first_time else "not checkable: ")
                         + "; ".join(self.not_checkable))
        if not parts:
            parts.append("same")
        if not self.check_2:
            parts.append("check 2: none")
        return f"{self.name}: " + " | ".join(parts)


# The baseline

ABOUT = ("tools/mirror_watch.py's baseline: what each provider answered when its record was adopted (public facts "
         "only); rewritten by `adopt`, never by hand")


def load_baseline(path: str) -> Dict[str, Dict]:
    """The records by key ({} when the file does not exist); Usage when it is not the tool's."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise Usage("the baseline cannot be read as JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("signals"), dict) or not all(
            isinstance(r, dict) for r in data["signals"].values()):
        raise Usage("the baseline is not the tool's (no \"signals\" object of records)")
    return data["signals"]


def _write_json(path: str, data) -> None:
    """data written whole through a temporary file beside path and a rename, LF line ends."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".mirror_watch.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_baseline(path: str, records: Dict[str, Dict]) -> None:
    _write_json(path, {"about": ABOUT, "signals": records})


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# The commands

def _datasets(names) -> List[str]:
    unknown = [n for n in names if n not in WATCH]
    if unknown:
        raise Usage(f"unknown dataset: {', '.join(unknown)} (watched: {', '.join(WATCH)})")
    return list(dict.fromkeys(names)) or list(WATCH)


def read_previous(path: str) -> Tuple[Optional[Dict], str]:
    """(the previous run's datasets, or None; what the line says of it)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, "none (no such file)"
    except (OSError, ValueError):
        return None, "none (the file cannot be read as JSON)"
    if not isinstance(data, dict) or data.get("tool") != "mirror_watch" or not isinstance(data.get("datasets"), dict):
        return None, "none (not a result of this tool)"
    checked = data.get("checked")
    return data["datasets"], ("the run of " + checked if isinstance(checked, str) and STAMP.fullmatch(checked)
                              else "a run of an unknown time")


def _was_not_checkable(previous: Optional[Dict], name: str) -> bool:
    entry = (previous or {}).get(name)
    return isinstance(entry, dict) and isinstance(entry.get("not_checkable"), list) and bool(entry["not_checkable"])


def run_check(names, baseline: str, previous_path: Optional[str] = None) -> Dict:
    """The result of a check, as --json prints it."""
    datasets = _datasets(names)
    records = load_baseline(baseline)
    previous, previous_note = (read_previous(previous_path) if previous_path else (None, None))
    http = Http()
    results = {}
    for signal in signals_of(datasets):
        facts, why = read(http, signal)
        results[key_of(signal)] = judge(signal, records.get(key_of(signal)), facts, why)
    rows = []
    for name in datasets:
        mine = [results[key_of(s)] for s in dict.fromkeys(WATCH[name])]
        row = DatasetResult(name, [c for r in mine for c in r.changed],
                            [f"{name_of(r.signal)}: {r.why}" for r in mine if r.why],
                            any(s.kind == "listing" for s in WATCH[name]))
        row.first_time = bool(previous_path and row.not_checkable and not _was_not_checkable(previous, name))
        rows.append(row)
    if any(r.changed for r in rows):
        code = EXIT_CHANGED
    elif any(r.not_checkable and not r.first_time for r in rows):
        code = EXIT_NOT_CHECKABLE
    else:
        code = EXIT_SAME
    return {
        "tool": "mirror_watch", "format": FORMAT, "checked": _now(), "exit": code, "previous": previous_note,
        "datasets": {r.name: {"state": r.state, "changed": r.changed, "not_checkable": r.not_checkable,
                              "first_time": r.first_time, "check_2": r.check_2, "line": r.line()} for r in rows},
        "signals": {k: {"name": name_of(r.signal), "kind": r.signal.kind, "url": r.signal.url, "state": r.state,
                        "changed": r.changed, "why": r.why, "now": r.facts} for k, r in results.items()},
    }


def check(args) -> int:
    result = run_check(args.datasets, args.baseline, args.previous)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["previous"] is not None:
            print("previous run: " + result["previous"])
        for row in result["datasets"].values():
            print(row["line"])
    code = result["exit"]
    if args.json_out:  # after the lines: a failed write never loses them
        try:
            _write_json(args.json_out, result)
        except OSError as error:
            print(f"the result file: not written ({type(error).__name__})", file=sys.stderr if args.json else None)
            code = code or EXIT_USAGE
    return code


def adopt(args) -> int:
    datasets = _datasets(args.datasets)
    records = load_baseline(args.baseline)
    http = Http()
    signals = signals_of(datasets)
    read_now = {key_of(s): read(http, s) for s in signals}
    refused = []
    for signal in signals:
        facts, why = read_now[key_of(signal)]
        refused += [(signal, why)] if why is not None else [(signal, w) for w in lacking(signal, facts)]
    if refused:
        print("not adopted, the baseline left as it was:")
        for signal, why in refused:
            print(f"  {name_of(signal)}: not checkable: {why}")
        return EXIT_NOT_CHECKABLE
    day = _today()
    for signal in signals:
        key, facts = key_of(signal), read_now[key_of(signal)][0]
        old = records.get(key)
        if old is None:
            said = f"{name_of(signal)}: new record"
        elif read_another_way(signal, old):
            said = f"{name_of(signal)}: read another way before: replaced"
        else:
            changes, missing = compare(signal, old, facts)
            said = "; ".join(changes + _gone(missing)) or f"{name_of(signal)}: same"
        others = [d for d in sharing(signal) if d not in datasets]
        print(said + (f" (also the baseline of {', '.join(others)})" if others else ""))
        records[key] = record_of(signal, facts, day)
    watched = [key_of(s) for s in signals_of(list(WATCH))]
    for key in [k for k in records if k not in watched]:
        print(f"dropped: {key} (no longer watched)")
    write_baseline(args.baseline, {k: records[k] for k in watched if k in records})
    print(f"the baseline rewritten: {sum(k in records for k in watched)} records")
    return EXIT_SAME


def list_rows(args) -> int:
    records = load_baseline(args.baseline)
    for name, row in WATCH.items():
        print(name)
        for signal in dict.fromkeys(row):
            record = records.get(key_of(signal))
            read_on = f"read {record.get('read')}" if record else "no baseline record"
            print(f"  {signal.kind:<8} {name_of(signal)}  ({read_on})  {signal.url}")
        if not any(s.kind == "listing" for s in row):
            print("  check 2: none")
    return EXIT_SAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="compare the providers' answers with the baseline")
    p.add_argument("datasets", nargs="*", help="the datasets (default: all)")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("--json-out", metavar="FILE", help="also write the result as JSON to FILE")
    p.add_argument("--previous", metavar="FILE", help="the previous run's --json-out: a dataset not checkable for "
                                                       "the first time does not make the exit code 3")
    p = sub.add_parser("adopt", help="read the signals and rewrite those datasets' baseline")
    p.add_argument("datasets", nargs="+")
    sub.add_parser("list", help="the rows: datasets, signals, the baseline's dates")
    for p in sub.choices.values():
        p.add_argument("--baseline", default=BASELINE, metavar="FILE", help="the baseline (default: "
                                                                            "mirror_watch.json beside the script)")
    return parser


def main(argv=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:  # argparse: 2 for usage, 0 for --help
        return stop.code if isinstance(stop.code, int) else EXIT_USAGE
    try:
        return {"check": check, "adopt": adopt, "list": list_rows}[args.command](args)
    except Usage as error:
        print(f"usage: {error}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as error:  # never a traceback: only the kind of the error
        print(f"error: {type(error).__name__}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 whatever the console's code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
