"""The completeness check of the data record (docs/regression-tests.md, "The completeness check of the data record"):
does a regression entry's stored record (tests/regression-data.json) name everything its search reads?

    python tools/record_check.py R1 R6 R18 --out C:\\fal\\record-check     # scratch caches there (removed at the end)
    python tools/record_check.py R82 --also northern_ireland/osni-dtm10m/sheet-index   # one more thing, named
    python tools/record_check.py R1 --reverse --keep                         # Nominatim's reverse rows of the centre

For each entry it builds a scratch cache holding only what the entry's record names, from the real cache by a hard
link per file (never a junction; a copy only with --copy, never silently): the files of each data layer, the world
coastline file's folder of the recorded edition or the OSM coastline tiles, the OSM tiles of the search area, each
file's index row, and the Nominatim answers the record names (those rows only). Each file whose checksum the record
holds is compared with it first (the real index's row, then the file's bytes): a file the real cache no longer holds,
or holds with other bytes, is an error naming it, and a name that is not relative to the cache is refused. A file the
record holds no checksum for, and the world file's folder (taken by its edition's name), are linked unchecked; the
line of each entry counts them. Beyond the record, each named in the output, never silently: the cache's LAYOUT; the
"missing" marks of the folders the record touches (a tile without a row is asked for again); a stand-in for the local
mirror folder (FINDALINE_MIRROR) holding only the empty folders of the entry's needs_path and of the mirror
resolutions its record read (the source is available, no tile can come from it); a dummy value of the two service
keys; and, only when asked, what --also and --reverse name (the stored index answers of a kind that cannot run
without them: its proof is the weaker one; Nominatim's reverse answers of the entry's centre).

What may be shared by a hard link, and why it is safe: only files that every writer replaces whole (a data tile, an
OSM theme tile, a file of the world file's folder, a stored index answer): each writer of such a file writes a new
file and renames it over the name (cache.replacing, sources.layer._write_tile, a download's `.part`,
CachedIndex._store), which replaces the scratch name and never touches the real file. Never shared (written_in_place,
refused in place_file whatever route named the file, in any letter case, after resolving the path, and checked again
after the build by shared_with_real): the databases (`*.sqlite` and their `-wal`, `-shm`, `-journal`: the index, the
Nominatim answers, the rate and day counters), locks, `.part` files, `LAYOUT`, anything under `locks/`, and the
`.retry` markers. Two places of the code open a cache path directly: `PackageListing.fetch`
(sources/indexes/packages.py) writes a `.json.retry` marker beside a package answer after the provider answered 404
or 410, and `osmextract.download` writes an extract's outline after its download; with the network blocked neither is
reached (no provider answers), and the marker is refused anyway. A new writer that opens a cache file in place must
be added to written_in_place, or this tool would write through a link into the real cache.

It then runs the entry through the harness (tests/regression.py <entry> --cache <scratch> --cold --no-seed --keep;
never --update; TEMP inside the entry's folder, so the harness's log folder is removed with it; its whole process
tree ended when the run is stopped) with the network blocked (block_env: every proxy variable to a dead local port, Overpass's address
too, the project's data server off as the harness sets it), after a check that requests, urllib and GDAL's /vsicurl/
all stop at that port for http and https (check_block). The verdict per entry: `ok` only when the harness says ok,
the run log's line says the data were the record's ("same") and no tile was downloaded; besides, the requests the
search tried (all blocked) per host from the run log, the first error lines of its output, and whether its run's own
record equals the stored one. Nothing is written into tests/ (the harness's run log goes to the test lock's folder,
as every run's). The real cache is read, not written: its indexes and Nominatim's database through update._query's
read-only connections (SQLite itself may leave a `-shm`, or a `-shm` and a `-wal`, beside an index in the two cases
update._read_only names: a `-wal` left by a killed writer, a read retried after another process's checkpoint; no data
changes and the next writer's close removes them); after each entry the size and time of every linked file are
checked unchanged. The scratch folder (--out, default a temporary one) is removed whatever stops an entry or the tool
(an error, Ctrl+C), unless --keep: links removed as links, junctions never followed, an attribute never changed (a
read-only link is deleted by the delete that ignores the attribute, Windows 10 1809 and later; one that cannot be is
left and named).

Run it again when a new kind of layer or index is added, or what a run records changes. Exit code: 0 every entry
ok, 1 an entry not ok or not checked (an error stopped it, or Ctrl+C), 2 a usage error (an unknown entry, a refused
--also or --out, the block not holding), 3 every entry ok but a file of the scratch folder left behind.
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
# Every proxy variable requests, urllib, libcurl (GDAL without its own) and GDAL read, set to the dead port over
# whatever the user's environment holds; any other variable naming a proxy (NO_PROXY, GDAL_HTTP_PROXYUSERPWD, ...) is
# left out, NO_PROXY set empty; REQUEST_METHOD left out (urllib ignores HTTP_PROXY when it is set, as in a CGI script)
PROXIES = {"HTTP_PROXY": DEAD, "HTTPS_PROXY": DEAD, "ALL_PROXY": DEAD, "FTP_PROXY": DEAD,
           "GDAL_HTTP_PROXY": "127.0.0.1:9", "GDAL_HTTPS_PROXY": "127.0.0.1:9", "NO_PROXY": ""}
DROPPED = ("REQUEST_METHOD",)
OVERPASS = {"FINDALINE_OVERPASS_URL": DEAD + "/api/interpreter"}
DUMMY_KEYS = ("OPENTOPOGRAPHY_API_KEY", "DATAFORDELER_API_KEY")  # the two entries that need one (needs_env)
DUMMY = "record-check-not-a-key"
MIRROR_ENV = "FINDALINE_MIRROR"
MARKER = "record-check.json"  # in --out: made by this tool, so a folder of anything else is never removed
WORLD = "osm/water-polygons"
# The last part of a name of a file written in place (never shared by a link: the docstring); compared lower case
IN_PLACE = re.compile(r"\.sqlite$|\.sqlite-(?:wal|shm|journal)$|-wal$|-shm$|-journal$|\.part$|\.lock$|\.retry$")
FIRST_ERRORS = 3  # error lines of the search's output shown per entry
ERROR_LINE = re.compile(r"index not available|Download failed|could not be connected|did not answer|WARNING|Error|"
                        r"refused|Failed to connect|No connection", re.I)


class RecordError(Exception):
    """The record cannot be turned into a scratch cache: a name not relative to the cache, a file the real cache no
    longer holds or holds with other bytes, an answer that is gone, a file that may not be shared by a link."""


# --- What the record names ----------------------------------------------------------------------------------------

def checked_name(name: str) -> str:
    """A file name of a record as a path below the cache, or RecordError: relative to the cache with "/" (the
    harness's cache_name: no drive, no leading slash, no backslash, no "..")."""
    if not regression.cache_name(name):
        raise RecordError(f"{name!r} is not relative to the cache: refused")
    return name


def written_in_place(name: str) -> bool:
    """Whether a cache name (relative, "/" or the system's separator) is a file the tool or a search writes in place:
    a database or its side files, a lock, a .part, a .retry marker, LAYOUT, anything under locks/. In any letter case,
    and as Windows reads a name (trailing dots and spaces dropped)."""
    parts = [part.rstrip(". ").lower() for part in name.replace("\\", "/").split("/") if part]
    return bool(parts) and (parts[0] == cache.LOCKS or parts[-1] == "layout" or bool(IN_PLACE.search(parts[-1])))


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
    cache, sorted; files written in place left out), never through a link; RecordError when the folder is gone or
    holds a link."""
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
        found += [cache.relative(real, os.path.join(root, n)) for n in names if not written_in_place(n)]
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


def _inside(real: str, path: str) -> Optional[str]:
    """The name of a path below the real cache after resolving links ("/"), or None when it lies outside."""
    try:
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(real))
    except ValueError:  # another drive
        return None
    return None if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel) else \
        rel.replace(os.sep, "/")


def place_file(real: str, scratch: str, name: str, copy: bool = False) -> str:
    """One file of the real cache placed at the same name in the scratch cache by a hard link (a copy only with
    copy). Returns "linked" or "copied". RecordError, before anything is placed for it: a file written in place (a
    database, a lock, LAYOUT...: written_in_place, also as the path resolves), a file the real cache does not hold as
    a file of its own, one outside it, one that cannot be linked without copy (another volume, a path too long for
    the system: the error names the file)."""
    source = os.path.join(real, *name.split("/"))
    resolved = _inside(real, source)
    if written_in_place(name) or (resolved is not None and written_in_place(resolved)):
        raise RecordError(f"{name} is a file written in place (a database, a lock, LAYOUT, ...): never shared by a "
                          f"link with the real cache")
    if not os.path.isfile(source) or _is_link(source):
        raise RecordError(f"{name} is named by the record but the real cache no longer holds it")
    if resolved is None:
        raise RecordError(f"{name} lies outside the real cache after resolving its path: refused")
    target = os.path.join(scratch, *name.split("/"))
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.link(source, target)
        return "linked"
    except OSError as e:
        if not copy:
            raise RecordError(f"{name} cannot be linked into the scratch cache ({e}); --copy copies it") from None
    try:
        shutil.copy2(source, target)
    except OSError as e:
        raise RecordError(f"{name} cannot be copied into the scratch cache ({e})") from None
    return "copied"


def _volume(path: str) -> int:
    """The volume a path lies on (no hard link between two)."""
    return os.stat(path).st_dev


def _existing(path: str) -> str:
    """The nearest folder of path that exists."""
    path = os.path.abspath(path)
    while not os.path.exists(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    return path


def shared_with_real(real: str, scratch: str) -> List[str]:
    """The files of the scratch cache written in place (written_in_place: the indexes and their side files, the
    Nominatim database, the rate and day counters, LAYOUT, locks) that share their data with another name (a hard
    link: more than one link, or the same file as the real cache's of that name). None may: such a write would reach
    the real cache."""
    found = []
    for root, dirs, names in os.walk(scratch):
        dirs[:] = [d for d in dirs if not _is_link(os.path.join(root, d))]
        for name in names:
            path = os.path.join(root, name)
            rel = cache.relative(scratch, path)
            if not written_in_place(rel):
                continue
            twin = os.path.join(real, *rel.split("/"))
            if os.stat(path).st_nlink > 1 or (os.path.exists(twin) and os.path.samefile(path, twin)):
                found.append(rel)
    return sorted(found)


def refuse_shared(real: str, scratch: str, name: str):
    """RecordError when the scratch cache's database `name` (or one of its side files) exists and shares its data
    with another file (more than one link, the real cache's file of that name, or a path inside the real cache):
    the tool's own writes (copy_rows, copy_answers) check it before they open the database; shared_with_real checks
    the whole scratch cache after the build."""
    for path in (os.path.join(scratch, *name.split("/")) + side for side in ("", "-wal", "-shm", "-journal")):
        if not os.path.exists(path):
            continue
        twin = os.path.join(real, *cache.relative(scratch, path).split("/"))
        if (os.stat(path).st_nlink > 1 or _inside(real, path) is not None
                or (os.path.exists(twin) and os.path.samefile(path, twin))):
            raise RecordError(f"the scratch cache's {cache.relative(scratch, path)} is shared with another file: "
                              f"refused, nothing written into it")


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
            refuse_shared(real, scratch, f"{top}/index.sqlite")  # the tool's own first write: never into a link
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
    scratch cache's (those rows only; a new database, never a link: shared_with_real). With check, each answer's
    sha256 must be the record's (RecordError naming the row otherwise; a checksum not known is taken as it is).
    Returns the rows copied."""
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
    for table, query, value in wanted:  # every answer checked before the scratch database is made
        row = found.get((table, query))
        if row is None or row[1] is None:
            raise RecordError(f"the Nominatim answer {table}: {query!r} is not in the real cache")
        if check and value is not None and hashlib.sha256(row[1].encode("utf-8")).hexdigest() != value:
            raise RecordError(f"the Nominatim answer {table}: {query!r} differs from the record's")
    refuse_shared(real, scratch, "osm/nominatim.sqlite")
    db = osm._nominatim_db(scratch)
    try:
        with db:
            for table, query, _ in wanted:
                db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)", found[(table, query)])
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
          reverse: Optional[Tuple[float, float]] = None, copy: bool = False) -> dict:
    """The scratch cache of a record (the module's docstring). Returns what was placed: {"files", "checked" (files
    compared with the record's checksum), "unchecked" (named without a checksum), "world" (taken by the edition's
    name), "linked", "copied", "rows", "missing" {folder: marks}, "answers", "beyond" [what lies beyond the record,
    as words], "placed" {name: (size, mtime) of the real file}}. RecordError before anything is placed when the
    record names a file wrongly, the real cache lacks one or holds other bytes, a name is written in place, or the
    scratch folder lies on another volume without copy (the error says how much would be copied)."""
    names = named_files(record)
    edition = (record["coastline"] or {}).get("edition")
    world = world_files(real, edition) if edition else []
    extra, left_out = [], 0
    for prefix in also:
        found, skipped = _files_below(real, checked_name(prefix.rstrip("/")))
        extra += found
        left_out += skipped
    every = sorted(set(names) | set(world) | set(extra))
    for name in every:
        if written_in_place(name):
            raise RecordError(f"{name} is a file written in place (a database, a lock, LAYOUT, ...): never shared by "
                              f"a link with the real cache")
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
    if not copy and _volume(real) != _volume(_existing(scratch)):
        size = sum(os.path.getsize(os.path.join(real, *n.split("/"))) for n in every)
        raise RecordError(f"the scratch folder lies on another volume than the real cache: {size / 2 ** 20:.0f} MB "
                          f"would be copied; --copy copies them")
    os.makedirs(scratch, exist_ok=True)
    cache.check_layout(scratch)  # LAYOUT first: the harness refuses a folder with files and no LAYOUT
    placed, how = {}, {"linked": 0, "copied": 0}
    for name in every:
        how[place_file(real, scratch, name, copy)] += 1
        stat = os.stat(os.path.join(real, *name.split("/")))
        placed[name] = (stat.st_size, stat.st_mtime_ns)
    folders = touched_folders(record, list(names) + world)
    copied, missing = copy_rows(real, scratch, sorted(placed), folders)
    answers = copy_answers(real, scratch, (record["area"]["inputs"] or {}).get("nominatim") or {})
    beyond = ["LAYOUT", f"{sum(missing.values())} \"missing\" marks ("
              + (", ".join(f"{folder} {n}" for folder, n in missing.items() if n) or "none in its folders") + ")"]
    if also:
        beyond.append(f"--also: {len(extra)} files below {', '.join(also)} with their rows"
                      + (f" ({left_out} databases, locks or markers below it left out)" if left_out else ""))
    if reverse is not None:
        found = reverse_answers(real, *reverse)
        n = copy_answers(real, scratch, found, check=False)
        beyond.append(f"--reverse: {n} Nominatim reverse answers of the centre")
    checked = sum(value is not None for value in names.values())
    return {"files": len(names), "checked": checked, "unchecked": len(names) - checked, "world": len(world), **how,
            "rows": copied, "missing": missing, "answers": answers, "beyond": beyond, "placed": placed}


def _files_below(real: str, prefix: str) -> Tuple[List[str], int]:
    """(the files below a folder of the real cache, or that one file, as relative names; how many below it were
    left out as written in place), never through a link. RecordError for a name written in place, a link or a name
    the real cache does not hold."""
    if written_in_place(prefix):
        raise RecordError(f"{prefix} is a file written in place (a database, a lock, LAYOUT, ...): refused")
    path = os.path.join(real, *prefix.split("/"))
    if _is_link(path):
        raise RecordError(f"{prefix} is a link: refused")
    if os.path.isfile(path):
        return [prefix], 0
    if not os.path.isdir(path):
        raise RecordError(f"{prefix} is not in the real cache")
    found, skipped = [], 0
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if not _is_link(os.path.join(root, d))]
        for n in names:
            if written_in_place(n):
                skipped += 1
            else:
                found.append(cache.relative(real, os.path.join(root, n)))
    return sorted(found), skipped


def unchanged(real: str, placed: Dict[str, Tuple[int, int]]) -> List[str]:
    """The placed real files whose size or modification time changed since they were placed, or that are gone
    (none: only read)."""
    moved = []
    for name, (size, mtime) in placed.items():
        try:
            stat = os.stat(os.path.join(real, *name.split("/")))
        except OSError:
            moved.append(name)
            continue
        if (stat.st_size, stat.st_mtime_ns) != (size, mtime):
            moved.append(name)
    return moved


def delete_ignoring_read_only(path: str) -> bool:
    """Delete one name of a file without changing its attributes, also when it is read-only (Windows 10 1809 and
    later: SetFileInformationByHandle's FileDispositionInfoEx with FILE_DISPOSITION_FLAG_IGNORE_READONLY_ATTRIBUTE).
    A hard link's attribute is the real file's too, so it is never cleared to delete the link. Whether it was deleted
    (False elsewhere or when the system refuses)."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.HANDLE)
    kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    delete, share_all, open_existing, open_reparse_point = 0x00010000, 0x7, 3, 0x00200000
    handle = kernel.CreateFileW(os.path.abspath(path), delete, share_all, None, open_existing, open_reparse_point,
                                None)
    if handle in (None, wintypes.HANDLE(-1).value):
        return False
    try:
        # FILE_DISPOSITION_FLAG_DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE; class 21: FileDispositionInfoEx
        flags = wintypes.DWORD(0x1 | 0x2 | 0x10)
        return bool(kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)))
    finally:
        kernel.CloseHandle(handle)


def remove_tree(path: str, left: Optional[List[str]] = None) -> List[str]:
    """Remove a folder this tool made: a link (a symbolic link, a junction) is removed as a link, never followed;
    files and folders below it removed. Attributes are never changed (a hard-linked file shares them): a read-only
    file is deleted by delete_ignoring_read_only, and one that cannot be is left. Returns what was left (with the
    folders holding it)."""
    left = [] if left is None else left
    if not os.path.lexists(path):
        return left
    if _is_link(path):
        if os.path.isdir(path):
            os.rmdir(path)  # a junction or a directory link: the link only
        else:
            os.unlink(path)
        return left
    if not os.path.isdir(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except PermissionError:
            if not delete_ignoring_read_only(path):
                left.append(path)
        return left
    with os.scandir(path) as entries:
        children = [entry.path for entry in entries]
    before = len(left)
    for child in children:
        remove_tree(child, left)
    if len(left) == before:
        try:
            os.rmdir(path)
        except OSError:
            left.append(path)
    return left


# --- The run ------------------------------------------------------------------------------------------------------

def block_env(base: Optional[Dict[str, str]] = None, mirror: Optional[str] = None) -> Dict[str, str]:
    """The environment of the harness: base (os.environ) with the network blocked (PROXIES over every variable
    naming a proxy in any letter case, REQUEST_METHOD left out, Overpass's address), every service key of settings
    left out and the two of the entries set to a dummy, FINDALINE_MIRROR the stand-in or nothing. On Windows a name
    is one variable whatever its case, so each is set once; elsewhere both cases are set."""
    import settings
    env = dict(os.environ if base is None else base)
    keys = {name.upper() for model in (settings.ServiceKeys, settings.WebKeys) for name in model.model_fields}
    for name in list(env):
        upper = name.upper()
        if upper in keys or "PROXY" in upper or upper in DROPPED or upper in OVERPASS or upper == MIRROR_ENV:
            del env[name]
    env.update(PROXIES)
    if os.name != "nt":
        env.update({name.lower(): value for name, value in PROXIES.items()})
    env.update(OVERPASS)
    env.update({name: DUMMY for name in DUMMY_KEYS})
    if mirror:
        env[MIRROR_ENV] = mirror
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# Each client asks an unresolvable name over http and https: a direct connection would fail on the name, so a refusal
# can only come from the proxy, and each must name or use the dead port: requests' ProxyError names
# host='127.0.0.1', port=9; urllib's refusal while its proxies are the dead port; curl's "via 127.0.0.1" while GDAL's
# proxies are the dead port
BLOCK_CHECK = r"""
import json, os, re, urllib.request
dead = "http://127.0.0.1:9"
found = {}
proxies = urllib.request.getproxies()
for url in ("http://record-check.invalid/x.tif", "https://record-check.invalid/x.tif"):
    scheme = url.split(":")[0]
    try:
        import requests
        requests.get(url, timeout=10)
        found["requests " + scheme] = "answered"
    except Exception as e:
        text = repr(e)
        ok = type(e).__name__ == "ProxyError" and re.search(r"host=\\*'127\.0\.0\.1\\*', port=9\b", text)
        found["requests " + scheme] = "blocked" if ok else text[:300]
    try:
        urllib.request.urlopen(url, timeout=10)
        found["urllib " + scheme] = "answered"
    except Exception as e:
        reason = getattr(e, "reason", e)
        ok = isinstance(reason, ConnectionRefusedError) and proxies.get(scheme) == dead
        found["urllib " + scheme] = "blocked" if ok else (repr(e) + " proxies: " + repr(proxies.get(scheme)))[:300]
    try:
        import rasterio
        with rasterio.Env(GDAL_HTTP_MAX_RETRY="0"):
            rasterio.open("/vsicurl/" + url)
        found["gdal " + scheme] = "answered"
    except Exception as e:
        gdal_proxies = [os.environ.get(name) for name in ("GDAL_HTTP_PROXY", "GDAL_HTTPS_PROXY")]
        ok = " via 127.0.0.1 " in str(e) and gdal_proxies == ["127.0.0.1:9", "127.0.0.1:9"]
        found["gdal " + scheme] = "blocked" if ok else str(e)[:300]
print(json.dumps(found))
"""


def check_block(env: Dict[str, str]) -> Dict[str, str]:
    """Each HTTP client a search uses (requests, urllib, GDAL's /vsicurl/) asked over http and https under env:
    {client and scheme: why not} for each the dead port did not stop (empty: the block holds)."""
    done = subprocess.run([sys.executable, "-c", BLOCK_CHECK], cwd=REPO, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=180)
    try:
        found = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"check": (done.stderr or done.stdout)[-300:]}
    expected = {f"{client} {scheme}" for client in ("requests", "urllib", "gdal") for scheme in ("http", "https")}
    failed = {key: text for key, text in found.items() if text != "blocked"}
    failed.update({key: "not asked" for key in expected - set(found)})
    return failed


def harness_command(entry: str, scratch_cache: str) -> List[str]:
    """The harness's command for an entry on a scratch cache: --cold --no-seed (nothing seeded from the real
    cache), --keep (the logs read, then removed here); never --update or --update-data."""
    return [sys.executable, os.path.join(REPO, "tests", "regression.py"), entry, "--cache", scratch_cache, "--cold",
            "--no-seed", "--keep"]


def end_tree(pid: int):
    """End a process and every process below it (the harness and its search), children first; gone ones skipped."""
    import psutil
    try:
        top = psutil.Process(pid)
        procs = top.children(recursive=True) + [top]
    except psutil.NoSuchProcess:
        return
    for proc in procs:
        with contextlib.suppress(psutil.NoSuchProcess):
            proc.kill()
    psutil.wait_procs(procs, timeout=30)


def run_harness(entry: str, scratch_cache: str, env: Dict[str, str]) -> subprocess.CompletedProcess:
    """The entry through the harness on the scratch cache (harness_command), in a process group of its own (a
    console's Ctrl+C reaches the tool only); whatever stops the wait (Ctrl+C, an error) ends the harness's whole
    process tree first, so its search writes nothing more into the scratch folder before it is removed."""
    command = harness_command(entry, scratch_cache)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", creationflags=flags, start_new_session=os.name != "nt")
    try:
        stdout, stderr = proc.communicate()
    except BaseException:
        end_tree(proc.pid)
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


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
                keep: bool, run: Callable = run_harness, say: Callable = print,
                copy: bool = False) -> Tuple[bool, List[str]]:
    """One entry: its scratch cache built, checked for files shared with the real cache, run, judged and reported.
    The harness runs with TEMP inside the entry's folder, so its log folder (with its `cache` junction) and the
    search's temporary files lie there. Returns (whether it is ok, what of the entry's folder was left behind).
    Whatever stops it (RecordError, any error, Ctrl+C) passes on after the harness's process tree has ended
    (run_harness) and the entry's folder has been removed, links as links (unless keep; a scratch cache holding a
    database shared with another file is removed whatever keep says); what cannot be removed is named in one line."""
    record, test = data[entry], tests[entry]
    folder = os.path.join(out, entry)
    left: List[str] = []
    work = None
    if os.path.lexists(folder):
        remove_tree(folder, left)
        if left:
            raise RecordError(f"an earlier scratch folder of {entry} could not be removed: {', '.join(left[:3])}")
    scratch = os.path.join(folder, "cache")
    try:
        centre = None
        if reverse:
            args = regression.full_args(tests, entry)
            lat, lon = regression._option(args, "--lat"), regression._option(args, "--lon")
            centre = (float(lat), float(lon)) if lat is not None and lon is not None else None
        built = build(record, real, scratch, also, centre, copy)
        if reverse and centre is None:
            built["beyond"].append("--reverse: the entry has no --lat/--lon (nothing copied)")
        stand_in = mirror_stand_in(record, test, os.path.join(folder, "mirror"))
        mirror = os.path.join(folder, "mirror") if stand_in else None
        if stand_in:
            built["beyond"].append(f"the mirror stand-in (no tile): {', '.join(stand_in)}")
        if test.get("needs_env") in DUMMY_KEYS:
            built["beyond"].append(f"{test['needs_env']} a dummy value")
        shared = shared_with_real(real, scratch)
        if shared:
            raise RecordError(f"files written in place share their data with another file: {', '.join(shared)}; "
                              f"not run")
        say(f"{entry}: {built['checked']} files checked against the record's checksum, {built['unchecked']} without a "
            f"checksum in the record (linked unchecked), {built['world']} of the world file taken by its edition's "
            f"name, not by their bytes ({built['linked']} linked, {built['copied']} copied); {built['rows']} index "
            f"rows, {built['answers']} Nominatim answers")
        say(f"    beyond the record: {'; '.join(built['beyond'])}")
        env = block_env(mirror=mirror)
        temporary = os.path.join(folder, "tmp")  # the harness's log folder and the search's temporary files: inside
        os.makedirs(temporary, exist_ok=True)  # the entry's folder, so removed with it whatever stops the run
        env.update({name: temporary for name in ("TEMP", "TMP", "TMPDIR")})
        log = os.path.join(regression._lock_dir() or "", regression.RUN_LOG)
        start = os.path.getsize(log) if os.path.isfile(log) else 0
        done = run(entry, scratch, env)
        work = logs_folder(done.stdout)
        line = log_line(log, start, scratch)
        ok, words, found = verdict(line, entry)
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
        return ok, left
    finally:
        # A scratch cache holding a database shared with another file goes whatever --keep says: nothing may run on it
        danger = os.path.isdir(scratch) and bool(shared_with_real(real, scratch))
        if keep and not danger:
            say(f"    kept: {folder}" + (f" (the harness's logs in {work})" if work else ""))
        else:
            if danger:
                say(f"    the scratch cache holds a file shared with another one: removed (--keep or not)")
            remove_tree(folder, left)  # the harness's log folder lies inside it (TEMP), its junction a link
        if left:
            say(f"    left behind (a read-only file whose attribute is shared with the real file is never changed): "
                f"{', '.join(left[:5])}" + (f" and {len(left) - 5} more" if len(left) > 5 else ""))


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
                             "kind's stored index answers when it cannot run without them; never a database, a lock "
                             "or LAYOUT")
    parser.add_argument("--reverse", action="store_true",
                        help="also Nominatim's stored reverse answers of the entry's centre (--lat/--lon)")
    parser.add_argument("--copy", action="store_true",
                        help="copy the files that cannot be linked (the real cache on another volume)")
    args = parser.parse_args(argv)
    for prefix in args.also:
        if not regression.cache_name(prefix.rstrip("/")) or written_in_place(prefix):
            parser.error(f"--also {prefix}: not relative to the cache, or a file written in place (a database, a "
                         f"lock, LAYOUT, ...): refused")
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
    failed = check_block(block_env())
    if failed:
        parser.error("the network block does not hold for " + "; ".join(f"{k}: {v}" for k, v in failed.items()))
    real = regression.real_cache_dir()
    try:
        out = prepare_out(args.out, real)
    except RecordError as e:
        parser.error(str(e))
    print(f"The network block holds (requests, urllib, GDAL's /vsicurl/ stop at {DEAD} for http and https); "
          f"scratch caches in {out}")
    results: Dict[str, str] = {}
    left: List[str] = []
    try:
        for entry in args.ids:
            try:
                ok, entry_left = check_entry(entry, tests, data, real, out, args.also, args.reverse, args.keep,
                                             copy=args.copy)
                results[entry] = "ok" if ok else "not ok"
                left += entry_left
            except RecordError as e:
                print(f"{entry}: NOT CHECKED: {e}")
                results[entry] = "not checked"
            except Exception as e:  # an error of its own stops this entry, not the others
                print(f"{entry}: NOT CHECKED: {type(e).__name__}: {e}")
                results[entry] = "not checked"
    except KeyboardInterrupt:
        print("Stopped (Ctrl+C)")
    finally:
        if not args.keep:
            remove_tree(out, left)
    for entry in args.ids:
        results.setdefault(entry, "not checked")
    bad = [entry for entry, state in results.items() if state != "ok"]
    print(f"\n{len(results) - len(bad)} ok, {len(bad)} not ok or not checked"
          + (f": {', '.join(f'{e} ({results[e]})' for e in bad)}" if bad else "")
          + (f"; left behind: {', '.join(left[:5])}" if left else ""))
    return 1 if bad else 3 if left else 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    sys.exit(main())
