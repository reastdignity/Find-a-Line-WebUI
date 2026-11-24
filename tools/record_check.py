"""The completeness check of the data record (docs/regression-tests.md, "The completeness check of the data record"):
does a regression entry's stored record (tests/regression-data.json) name everything its search reads?

    python tools/record_check.py R1 R6 R18 --out C:\\fal\\record-check     # scratch caches there (removed at the end)
    python tools/record_check.py R82 --also northern_ireland/osni-dtm10m/sheet-index   # one more thing, named
    python tools/record_check.py R1 --reverse --keep                         # Nominatim's reverse rows of the centre

For each entry it builds a scratch cache holding only what the entry's record names, from the real cache by a hard
link per file (a copy only where a link cannot be made; never a junction): the files of each data layer, the world
coastline file's folder of the recorded edition or the OSM coastline tiles, the OSM tiles of the search area, each
file's index row, and the Nominatim answers the record names (those rows only). Each file's sha256 is compared with
the record's first: a file the real cache no longer holds, or holds with other bytes, is an error naming it, and a
name that is not relative to the cache is refused. Beyond the record, each named in the output, never silently: the
cache's LAYOUT; the "missing" marks of the folders the record touches (a tile without a row is asked for again); a
stand-in for the local mirror folder (FINDALINE_MIRROR) holding only the empty folders of the entry's needs_path
and of the mirror resolutions its record read (the source is available, no tile can come from it); a dummy value of
the two service keys; and, only when asked, what --also and --reverse name (the stored index answers of a kind that
cannot run without them: its proof is the weaker one; Nominatim's reverse answers of the entry's centre).

It then runs the entry through the harness (tests/regression.py <entry> --cache <scratch> --cold --no-seed --keep)
with the network blocked (block_env: the proxy variables and GDAL's to a dead local port, Overpass's address too, the
project's data server off as the harness sets it), after a check that requests, urllib and GDAL's /vsicurl/ all fail
on that block (check_block). The verdict per entry: `ok` only when the harness says ok, the run log's line says the
data were the record's ("same") and no tile was downloaded; besides, the requests the search tried (all blocked)
per host from the run log, the first error lines of its output, and whether its run's own record equals the stored
one. Nothing is written into tests/ (the harness's run log goes to the test lock's folder, as every run's); the real
cache is only read (its index and Nominatim's database through update._query's read-only connections; after each
entry the size and time of every linked file are checked unchanged). The scratch folder (--out, default a temporary
one) is removed at the end unless --keep, links removed as links, junctions never followed (remove_tree).

Run it again when a new kind of layer or index is added, or what a run records changes. Exit code: 0 every entry
ok, 1 an entry not ok, 2 a usage error (an unknown entry, a record or file refused, the block not holding).
"""

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import cache  # noqa: E402
import regression  # noqa: E402  (tests/regression.py: the records, the names, the real cache, the run log's folder)

DEAD = "http://127.0.0.1:9"  # a local port nothing listens on, as the offline tests block the network
BLOCK = {"HTTP_PROXY": DEAD, "HTTPS_PROXY": DEAD, "ALL_PROXY": DEAD, "NO_PROXY": "",
         "GDAL_HTTP_PROXY": "127.0.0.1:9", "FINDALINE_OVERPASS_URL": DEAD + "/api/interpreter"}
DUMMY_KEYS = ("OPENTOPOGRAPHY_API_KEY", "DATAFORDELER_API_KEY")  # the two entries that need one (needs_env)
DUMMY = "record-check-not-a-key"
MIRROR_ENV = "FINDALINE_MIRROR"
MARKER = "record-check.json"  # in --out: made by this tool, so a folder of anything else is never removed
WORLD = "osm/water-polygons"
SKIP_NAMES = re.compile(r"\.sqlite(?:-wal|-shm|-journal)?$|\.part$|\.lock$")  # never linked (a write would reach the
# real file through the link: databases are made new and filled by rows)
FIRST_ERRORS = 3  # error lines of the search's output shown per entry
ERROR_LINE = re.compile(r"index not available|Download failed|could not be connected|did not answer|WARNING|Error|"
                        r"refused|Failed to connect|No connection", re.I)


class RecordError(Exception):
    """The record cannot be turned into a scratch cache: a name not relative to the cache, a file the real cache no
    longer holds or holds with other bytes, an answer that is gone."""


# --- What the record names ----------------------------------------------------------------------------------------

def checked_name(name: str) -> str:
    """A file name of a record as a path below the cache, or RecordError: relative to the cache with "/" (the
    harness's cache_name: no drive, no leading slash, no backslash, no "..")."""
    if not regression.cache_name(name):
        raise RecordError(f"{name!r} is not relative to the cache: refused")
    return name


def named_files(record: dict) -> Dict[str, Optional[str]]:
    """{name: checksum or None} of every file a record names: each folder's files, the OSM coastline tiles, the
    search area's tiles (the world file's folder is listed from the real cache: world_files)."""
    files: Dict[str, Optional[str]] = {}
    for place in record["folders"].values():
        files.update(place["files"])
    if record["coastline"] and "tiles" in record["coastline"]:
        files.update(record["coastline"]["tiles"])
    inputs = record["area"]["inputs"]
    if inputs:
        files.update(inputs["tiles"])
    for name in files:
        checked_name(name)
    return files


def world_files(real: str, edition: str) -> List[str]:
    """The files of the world coastline file's folder of an edition in the real cache (names relative to the
    cache, sorted), never through a link; RecordError when the folder is gone or holds a link."""
    if not regression.edition_name(edition):
        raise RecordError(f"the world file's edition {edition!r} is no folder name: refused")
    folder = os.path.join(real, *WORLD.split("/"), edition)
    if not os.path.isdir(folder) or _is_link(folder):
        raise RecordError(f"{WORLD}/{edition} (the world file of the record) is not in the real cache")
    found = []
    for root, dirs, names in os.walk(folder):
        for d in dirs:
            if _is_link(os.path.join(root, d)):
                raise RecordError(f"{cache.relative(real, os.path.join(root, d))} is a link: refused")
        for name in names:
            if not SKIP_NAMES.search(name):
                found.append(cache.relative(real, os.path.join(root, name)))
    return sorted(found)


def touched_folders(record: dict, names: Sequence[str]) -> List[str]:
    """The folders whose "missing" marks are copied: the record's layer folders and the folders of its tiles."""
    folders = {f for f in set(record["folders"]) | {name.rsplit("/", 1)[0] for name in names if "/" in name}
               if regression.cache_name(f)}
    return sorted(f for f in folders if not any(f.startswith(other + "/") for other in folders))  # outermost


# --- The scratch cache --------------------------------------------------------------------------------------------

def _is_link(path: str) -> bool:
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def place_file(real: str, scratch: str, name: str) -> str:
    """One file of the real cache placed at the same name in the scratch cache: a hard link, else a copy.
    Returns "linked" or "copied"; RecordError when the real cache does not hold it as a file of its own."""
    source = os.path.join(real, *name.split("/"))
    if not os.path.isfile(source) or _is_link(source):
        raise RecordError(f"{name} is named by the record but the real cache no longer holds it")
    target = os.path.join(scratch, *name.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        os.link(source, target)
        return "linked"
    except OSError:  # another volume, too many links
        shutil.copy2(source, target)
        return "copied"


def _real_rows(real: str, top: str, ask: Callable[[sqlite3.Connection], list]) -> list:
    """Rows read from a real top-level folder's index.sqlite without writing anything (update._query)."""
    import update
    found = update._query(os.path.join(real, top, "index.sqlite"), lambda db: {"rows": ask(db)})
    return found.get("rows", [])


def copy_rows(real: str, scratch: str, names: Sequence[str], folders: Sequence[str]) -> Tuple[int, Dict[str, int]]:
    """The index rows of the named files and the "missing" rows of the folders, from the real cache into the
    scratch cache's index.sqlite of each top-level folder. Returns (file rows copied, {folder: missing marks})."""
    by_top: Dict[str, set] = {}
    for name in names:
        top, _, inner = name.partition("/")
        by_top.setdefault(top, set()).add(inner)
    prefixes: Dict[str, List[str]] = {}
    for folder in folders:
        top, _, inner = folder.partition("/")
        prefixes.setdefault(top, []).append(inner + "/" if inner else "")
    copied, missing = 0, {folder: 0 for folder in folders}
    for top in sorted(set(by_top) | set(prefixes)):
        inners, marks = by_top.get(top, set()), prefixes.get(top, [])
        rows = _real_rows(real, top, lambda db: db.execute("SELECT * FROM files").fetchall())
        keep = []
        for row in rows:
            if row[0] in inners:
                keep.append(row)
                copied += 1
            elif row[1] == "missing":
                hit = next((p for p in marks if row[0].startswith(p)), None)
                if hit is not None:
                    keep.append(row)
                    missing[f"{top}/{hit[:-1]}" if hit else top] += 1
        if keep:
            db = cache._connect(scratch, top)
            try:
                with db:
                    db.executemany("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)", keep)
            finally:
                db.close()
    return copied, missing


def stored_rows(real: str, names: Sequence[str]) -> Dict[str, Tuple]:
    """{name: (status, sha256)} of the real cache's index rows of the named files (a name without a row is left
    out)."""
    by_top: Dict[str, List[str]] = {}
    for name in names:
        top, _, inner = name.partition("/")
        by_top.setdefault(top, []).append(inner)
    found = {}
    for top, inners in by_top.items():
        wanted = set(inners)
        for row in _real_rows(real, top, lambda db: db.execute("SELECT path, status, sha256 FROM files").fetchall()):
            if row[0] in wanted:
                found[f"{top}/{row[0]}"] = (row[1], row[2])
    return found


def copy_answers(real: str, scratch: str, answers: Dict[str, Dict[str, Optional[str]]],
                 check: bool = True) -> int:
    """Nominatim's stored answers {table: {query: checksum}} from the real cache's osm/nominatim.sqlite into the
    scratch cache's (those rows only). With check, each answer's sha256 must be the record's (RecordError naming
    the row otherwise; a checksum not known is taken as it is). Returns the rows copied."""
    import osm
    wanted = [(table, query, value) for table, queries in sorted(answers.items())
              for query, value in sorted(queries.items())]
    if not wanted:
        return 0
    tables = {table for table, _, _ in wanted}
    if not tables <= {"search", "reverse", "places"}:
        raise RecordError(f"a Nominatim table the database does not have: {sorted(tables)}")

    def ask(db):
        return [(table, query, db.execute(f"SELECT query, answer, fetched_at FROM {table} WHERE query = ?",
                                          (query,)).fetchone()) for table, query, _ in wanted]
    import update
    rows = update._query(os.path.join(real, "osm", "nominatim.sqlite"), lambda db: {"rows": ask(db)}).get("rows", [])
    found = {(table, query): row for table, query, row in rows}
    db = osm._nominatim_db(scratch)
    try:
        with db:
            for table, query, value in wanted:
                row = found.get((table, query))
                if row is None or row[1] is None:
                    raise RecordError(f"the Nominatim answer {table}: {query!r} is not in the real cache")
                if check and value is not None and hashlib.sha256(row[1].encode("utf-8")).hexdigest() != value:
                    raise RecordError(f"the Nominatim answer {table}: {query!r} differs from the record's")
                db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)", row)
    finally:
        db.close()
    return len(wanted)


def reverse_answers(real: str, lat: float, lon: float) -> Dict[str, Dict[str, None]]:
    """{"reverse": {query: None}} of the real cache's stored reverse lookups of a point (osm.reverse's key: lat and
    lon rounded to 5 decimals, any other parameters): the source's country and region, the run's name."""
    import update

    def ask(db):
        return [query for (query,) in db.execute("SELECT query FROM reverse").fetchall()]
    queries = update._query(os.path.join(real, "osm", "nominatim.sqlite"), lambda db: {"rows": ask(db)}).get("rows", [])
    point = (round(lat, 5), round(lon, 5))
    keys = {}
    for query in queries:
        with contextlib.suppress(ValueError, TypeError, AttributeError):
            key = json.loads(query)
            if (key.get("lat"), key.get("lon")) == point:
                keys[query] = None
    return {"reverse": keys} if keys else {}


def mirror_stand_in(record: dict, test: dict, folder: str) -> List[str]:
    """The empty folders of a stand-in for the local mirror (FINDALINE_MIRROR) below folder: the entry's needs_path
    and, for each of our own tiled layers whose cache folder the record names, that resolution's mirror folder (its
    presence chooses native or averaged tiles: GridTiles). Returns the mirror folders made (relative)."""
    import sources as src
    from sources.layers.gridtiles import GridTiles
    made = set(test.get("needs_path", ()))
    seen = set()
    for source in src.SOURCES.values():
        for layer in (source.nmt, source.nmpt):
            if not isinstance(layer, GridTiles) or id(layer) in seen:
                continue
            seen.add(id(layer))
            for res, reader in layer.readers.items():
                if layer.index.tilings[res].folder in record["folders"] and reader.mirror:
                    made.add(reader.mirror)
    for name in made:
        os.makedirs(os.path.join(folder, *name.split("/")), exist_ok=True)
    return sorted(made)


def build(record: dict, real: str, scratch: str, also: Sequence[str] = (),
          reverse: Optional[Tuple[float, float]] = None) -> dict:
    """The scratch cache of a record (the module's docstring). Returns what was placed: {"files", "linked",
    "copied", "rows", "missing" {folder: marks}, "answers", "beyond" [what lies beyond the record, as words],
    "placed" {name: (size, mtime) of the real file}}; RecordError before anything is placed when the record
    names a file wrongly, the real cache lacks one or holds other bytes."""
    names = named_files(record)
    edition = (record["coastline"] or {}).get("edition")
    world = world_files(real, edition) if edition else []
    extra = []
    for prefix in also:
        checked_name(prefix.rstrip("/"))
        extra += _files_below(real, prefix.rstrip("/"))
    rows = stored_rows(real, list(names))
    for name, value in names.items():  # the bytes first: the real cache may have moved on since the record
        source = os.path.join(real, *name.split("/"))
        if not os.path.isfile(source):
            raise RecordError(f"{name} is named by the record but the real cache no longer holds it")
        if value is not None:
            if rows.get(name, (None, None))[1] not in (None, value):
                raise RecordError(f"{name}: the real cache's index holds another checksum than the record")
            if _sha256(source) != value:
                raise RecordError(f"{name}: the real cache's file differs from the record's checksum")
    os.makedirs(scratch, exist_ok=True)
    cache.check_layout(scratch)  # LAYOUT first: the harness refuses a folder with files and no LAYOUT
    placed, how = {}, {"linked": 0, "copied": 0}
    for name in sorted(set(names) | set(world) | set(extra)):
        how[place_file(real, scratch, name)] += 1
        stat = os.stat(os.path.join(real, *name.split("/")))
        placed[name] = (stat.st_size, stat.st_mtime_ns)
    folders = touched_folders(record, list(names) + world)
    copied, missing = copy_rows(real, scratch, sorted(placed), folders)
    answers = copy_answers(real, scratch, (record["area"]["inputs"] or {}).get("nominatim") or {})
    beyond = ["LAYOUT", f"{sum(missing.values())} \"missing\" marks ("
              + (", ".join(f"{folder} {n}" for folder, n in missing.items() if n) or "none in its folders") + ")"]
    if extra:
        beyond.append(f"--also: {len(extra)} files below {', '.join(also)} with their rows")
    if reverse is not None:
        found = reverse_answers(real, *reverse)
        n = copy_answers(real, scratch, found, check=False)
        beyond.append(f"--reverse: {n} Nominatim reverse answers of the centre")
    return {"files": len(names), "world": len(world), **how, "rows": copied, "missing": missing,
            "answers": answers, "beyond": beyond, "placed": placed}


def _files_below(real: str, prefix: str) -> List[str]:
    """The files below a folder of the real cache (or that one file), relative names, never through a link."""
    path = os.path.join(real, *prefix.split("/"))
    if os.path.isfile(path):
        return [prefix]
    if not os.path.isdir(path) or _is_link(path):
        raise RecordError(f"{prefix} is not in the real cache")
    found = []
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if not _is_link(os.path.join(root, d))]
        found += [cache.relative(real, os.path.join(root, n)) for n in names if not SKIP_NAMES.search(n)]
    return sorted(found)


def unchanged(real: str, placed: Dict[str, Tuple[int, int]]) -> List[str]:
    """The placed real files whose size or modification time changed since they were placed (none: only read)."""
    moved = []
    for name, (size, mtime) in placed.items():
        stat = os.stat(os.path.join(real, *name.split("/")))
        if (stat.st_size, stat.st_mtime_ns) != (size, mtime):
            moved.append(name)
    return moved


def remove_tree(path: str):
    """Remove a folder this tool made: a link (a symbolic link, a junction) is removed as a link, never followed;
    files and folders below it removed. Attributes are never changed (a hard-linked file shares them)."""
    if not os.path.lexists(path):
        return
    if _is_link(path):
        if os.path.isdir(path):
            os.rmdir(path)  # a junction or a directory link: the link only
        else:
            os.unlink(path)
        return
    if not os.path.isdir(path):
        os.remove(path)
        return
    with os.scandir(path) as entries:
        children = [entry.path for entry in entries]
    for child in children:
        remove_tree(child)
    os.rmdir(path)


# --- The run ------------------------------------------------------------------------------------------------------

def block_env(base: Optional[Dict[str, str]] = None, mirror: Optional[str] = None) -> Dict[str, str]:
    """The environment of the harness: base (os.environ) with the network blocked (BLOCK), every service key of
    settings left out and the two of the entries set to a dummy, FINDALINE_MIRROR the stand-in or nothing."""
    import settings
    env = dict(os.environ if base is None else base)
    keys = {name.upper() for model in (settings.ServiceKeys, settings.WebKeys) for name in model.model_fields}
    for name in list(env):
        if name.upper() in keys or name.upper() in {k.upper() for k in BLOCK} or name.upper() == MIRROR_ENV:
            del env[name]
    env.update(BLOCK)
    if os.name != "nt":  # libcurl reads the lower-case name for http; Windows' environment ignores case
        env.update({name.lower(): value for name, value in BLOCK.items() if name.endswith("_PROXY")})
    env.update({name: DUMMY for name in DUMMY_KEYS})
    if mirror:
        env[MIRROR_ENV] = mirror
    env["PYTHONIOENCODING"] = "utf-8"
    return env


BLOCK_CHECK = r"""
import json, sys, urllib.request
url = "http://record-check.invalid/x.tif"
found = {}
try:
    import requests
    requests.get(url, timeout=10)
    found["requests"] = "answered"
except Exception as e:
    found["requests"] = str(e)[:300]
try:
    urllib.request.urlopen(url, timeout=10)
    found["urllib"] = "answered"
except Exception as e:
    found["urllib"] = str(e)[:300]
try:
    import rasterio
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="0"):
        rasterio.open("/vsicurl/" + url)
    found["gdal"] = "answered"
except Exception as e:
    found["gdal"] = str(e)[:300]
print(json.dumps(found))
"""


def check_block(env: Dict[str, str]) -> Dict[str, str]:
    """Each HTTP client a search uses (requests, urllib, GDAL's /vsicurl/) asked for a name that cannot resolve,
    under env: {client: why not} for a client the block did not stop at the dead port (empty: it holds)."""
    done = subprocess.run([sys.executable, "-c", BLOCK_CHECK], cwd=REPO, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    try:
        found = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"check": (done.stderr or done.stdout)[-300:]}
    # The dead port named, or the refusal of a connection: the name cannot resolve, so only the proxy refuses
    # (WinError 10061: the system's words are in its language)
    proxy = re.compile(r"127\.0\.0\.1|ProxyError|Unable to connect to proxy|refused|WinError 10061|"
                       r"ECONNREFUSED", re.I)
    return {client: text for client, text in found.items() if text == "answered" or not proxy.search(text)}


def run_harness(entry: str, scratch_cache: str, env: Dict[str, str]) -> subprocess.CompletedProcess:
    """The entry through the harness on the scratch cache, its logs kept (read, then removed here)."""
    return subprocess.run([sys.executable, os.path.join(REPO, "tests", "regression.py"), entry, "--cache",
                           scratch_cache, "--cold", "--no-seed", "--keep"], cwd=REPO, env=env, capture_output=True,
                          text=True, encoding="utf-8")


def log_line(log: str, start: int, scratch_cache: str) -> Optional[dict]:
    """The run log's line of this run: the last one appended after `start` (bytes) whose cache is the scratch
    cache (other sessions append to the same file)."""
    try:
        with open(log, "rb") as f:
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    found = None
    for line in lines:
        with contextlib.suppress(ValueError):
            record = json.loads(line)
            if isinstance(record, dict) and regression.same_folder(record.get("cache", ""), scratch_cache):
                found = record
    return found


def logs_folder(stdout: str) -> Optional[str]:
    """The harness's log folder, from its summary line ("N ok, ...; logs in <folder>")."""
    found = re.findall(r"^\d+ ok, .*; logs in (.+)$", stdout, re.M)
    return found[-1].strip() if found else None


def first_errors(output: str) -> List[str]:
    """The search's first lines that tell of a request or a failure (FIRST_ERRORS of them)."""
    return [line.strip()[:240] for line in output.splitlines() if ERROR_LINE.search(line)][:FIRST_ERRORS]


def own_record(work: str, entry: str) -> Optional[dict]:
    """The data record of the entry's run in the harness's log folder (regression.read_record)."""
    return regression.read_record(os.path.join(work, entry, "runs")) if work else None


def record_words(stored: dict, found: Optional[dict]) -> str:
    """Whether the run's own record names what the stored one names: the files with their checksums, the coastline,
    the search area and its inputs, the source."""
    if found is None:
        return "the run made no run.json"
    parts = [key for key in ("folders", "coastline", "area", "source") if stored[key] != found[key]]
    if not parts:
        return "the run's own record names the same data"
    compared = regression.compare_records(stored, found)
    return "the run's own record differs in " + ", ".join(parts) + (
        f" ({'; '.join(compared['parts'])})" if compared["parts"] else "")


def verdict(line: Optional[dict], entry: str) -> Tuple[bool, str, dict]:
    """(ok, the outcome's words, the entry's run log entry) from the run log's line: ok only when the harness's
    outcome is ok, its data "same" and no tile was downloaded."""
    found = (line or {}).get("entries", {}).get(entry)
    if not found:
        return False, "no run log line of the entry", {}
    words = found.get("outcome", "?") + (f" ({found['reason']})" if found.get("reason") else "")
    downloaded = (found.get("tiles") or {}).get("downloaded", 0)
    ok = found.get("outcome") == "ok" and found.get("data") == "same" and not downloaded
    if found.get("data") != "same":
        words += f"; data {found.get('data')}"
    if downloaded:
        words += f"; {downloaded} tiles downloaded"
    return ok, words, found


def hosts_words(found: dict) -> str:
    hosts = found.get("hosts") or {}
    if not hosts:
        return "none"
    return ", ".join(f"{host} {v['requests']} ({v['failed']} failed)" for host, v in sorted(hosts.items()))


def check_entry(entry: str, tests: dict, data: dict, real: str, out: str, also: Sequence[str], reverse: bool,
                keep: bool, run: Callable = run_harness, say: Callable = print) -> bool:
    """One entry: its scratch cache built, run, judged and reported; whether it is ok."""
    record, test = data[entry], tests[entry]
    folder = os.path.join(out, entry)
    if os.path.lexists(folder):
        remove_tree(folder)
    scratch = os.path.join(folder, "cache")
    centre = None
    if reverse:
        args = regression.full_args(tests, entry)
        lat, lon = regression._option(args, "--lat"), regression._option(args, "--lon")
        centre = (float(lat), float(lon)) if lat is not None and lon is not None else None
    built = build(record, real, scratch, also, centre)
    if reverse and centre is None:
        built["beyond"].append("--reverse: the entry has no --lat/--lon (nothing copied)")
    stand_in = mirror_stand_in(record, test, os.path.join(folder, "mirror"))
    mirror = os.path.join(folder, "mirror") if stand_in else None
    if stand_in:
        built["beyond"].append(f"the mirror stand-in (no tile): {', '.join(stand_in)}")
    if test.get("needs_env") in DUMMY_KEYS:
        built["beyond"].append(f"{test['needs_env']} a dummy value")
    say(f"{entry}: {built['files']} files of the record and {built['world']} of the world file "
        f"({built['linked']} linked, {built['copied']} copied, each checksum the record's), {built['rows']} index "
        f"rows, {built['answers']} Nominatim answers")
    say(f"    beyond the record: {'; '.join(built['beyond'])}")
    env = block_env(mirror=mirror)
    log = os.path.join(regression._lock_dir() or "", regression.RUN_LOG)
    start = os.path.getsize(log) if os.path.isfile(log) else 0
    done = run(entry, scratch, env)
    line = log_line(log, start, scratch)
    ok, words, found = verdict(line, entry)
    work = logs_folder(done.stdout)
    output = ""
    if work and os.path.isfile(os.path.join(work, entry, "output.log")):
        with open(os.path.join(work, entry, "output.log"), encoding="utf-8", errors="replace") as f:
            output = f.read()
    say(f"    verdict: {'ok' if ok else 'NOT OK'}: {words}")
    say(f"    requests tried (all blocked): {hosts_words(found)}")
    for error in first_errors(output):
        say(f"    first: {error}")
    say(f"    {record_words(record, own_record(work, entry))}")
    if not ok and done.returncode not in (0, 1, 3):
        say(f"    the harness ended with {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")
    moved = unchanged(real, built["placed"])
    if moved:
        ok = False
        say(f"    the real cache's files changed meanwhile: {', '.join(moved[:5])}")
    if work and os.path.isdir(work) and os.path.basename(work).startswith("findaline-regression-") and not keep:
        remove_tree(work)
    elif work:
        say(f"    the harness's logs kept in {work}")
    if not keep:
        remove_tree(folder)
    return ok


def prepare_out(out: Optional[str], real: str) -> str:
    """The scratch folder: a new temporary one, or --out when it is new, empty or made by this tool (MARKER), and
    neither the real cache nor inside it."""
    if out is None:
        out = tempfile.mkdtemp(prefix="findaline-record-check-")
    out = os.path.abspath(out)
    real_path = os.path.normcase(os.path.realpath(real))
    here = os.path.normcase(os.path.realpath(out))
    if here == real_path or here.startswith(real_path + os.sep) or real_path.startswith(here + os.sep):
        raise RecordError(f"--out {out} is the real cache, inside it or holds it: refused")
    if os.path.isdir(out) and os.listdir(out) and not os.path.isfile(os.path.join(out, MARKER)):
        raise RecordError(f"--out {out} holds files this tool did not make: refused")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, MARKER), "w", encoding="utf-8") as f:
        json.dump({"tool": "tools/record_check.py"}, f)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="+", help="regression entries (tests/regression.json) with a stored record")
    parser.add_argument("--out", help="the folder of the scratch caches (default: a new temporary one)")
    parser.add_argument("--keep", action="store_true", help="keep the scratch caches and the harness's logs")
    parser.add_argument("--also", action="append", default=[],
                        help="a file or folder of the real cache placed too (named beyond the record; repeatable): a "
                             "kind's stored index answers when it cannot run without them")
    parser.add_argument("--reverse", action="store_true",
                        help="also Nominatim's stored reverse answers of the entry's centre (--lat/--lon)")
    args = parser.parse_args(argv)
    tests = regression.load()
    try:
        data = regression.load_data()
    except ValueError as e:
        parser.error(str(e))
    for entry in args.ids:
        if entry not in tests:
            parser.error(f"unknown entry {entry}")
        if tests[entry].get("kind") == "osm" or entry not in data:
            parser.error(f"{entry} has no stored data record")
    real = regression.real_cache_dir()
    try:
        out = prepare_out(args.out, real)
    except RecordError as e:
        parser.error(str(e))
    failed = check_block(block_env())
    if failed:
        parser.error("the network block does not hold for " + "; ".join(f"{k}: {v}" for k, v in failed.items()))
    print(f"The network block holds (requests, urllib, GDAL's /vsicurl/ stop at {DEAD}); scratch caches in {out}")
    results = {}
    for entry in args.ids:
        try:
            results[entry] = check_entry(entry, tests, data, real, out, args.also, args.reverse, args.keep)
        except RecordError as e:
            print(f"{entry}: NOT RUN: {e}")
            results[entry] = False
            if not args.keep:
                remove_tree(os.path.join(out, entry))
    if not args.keep:
        remove_tree(out)
    bad = [entry for entry, ok in results.items() if not ok]
    print(f"\n{len(results) - len(bad)} ok, {len(bad)} not ok" + (f": {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    sys.exit(main())
