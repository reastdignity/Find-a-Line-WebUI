"""
Publishing the mirror's datasets to the home server (run by hand on the PC that holds the master copy, not by the
app): docs/mirror-hosting/spec.md, solution B. The master is the mirror folder (FINDALINE_MIRROR, the folder above
slovakia/: <mirror>/<dataset>/<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif with one index.json per product folder,
tools/sk_tiles.py and tools/mirror_tiles.py); the server is reached with rclone (1.76 or newer, on PATH or named by
FINDALINE_RCLONE) over SFTP, as a remote of the user's own rclone config whose shell hashes with sha256sum
(`hashes = sha256`, `sha256sum_command = sha256sum`). Under the server's <root>: staging/ (the lock staging/.lock
too), public/ (served: public/v1/tiles/<dataset>/, public/v1/datasets.json), trash/, logs/ (the server's request
log).

    python tools/mirror_publish.py verify <folder or remote:path> [--read-back]
    python tools/mirror_publish.py publish <dataset> --to <remote>:<root> [--same-values] [--break-lock] [--read-back]
    python tools/mirror_publish.py unpublish <dataset> --to <remote>:<root> [--break-lock]
    python tools/mirror_publish.py clean --to <remote>:<root> [--keep-days 7] [--break-lock]
    python tools/mirror_publish.py stats --from <remote>:<root>/logs

Every command takes --config FILE (the rclone config to use; rclone's own default otherwise) and --log FILE
(rclone's own messages appended there; they are never printed: they may name the remote's host and user). --to and
--from name an rclone remote (name:path, the name two characters or more); a dataset's name is [a-z0-9_-]+ (the
served pattern's), anything else is refused before any request.

verify: for every index.json below the folder or remote path: every tile it lists with a sha256 is there with that
sha256, no tile file (<i>_<j>.tif) it does not list, the index not "partial". On a folder the tool hashes the files
itself (other files than tiles, a .part of a cut, are not looked at: they are never copied); on a remote the server
hashes them (rclone checksum sha256 against a SUM file made from the index), and every file of a product folder but
index.json must be a listed tile. A product folder holding tiles without an index.json, and an index that is not
what the cutting tools write (its tiles' keys, their sha256 as 64 hex digits, "block" present and 10), are faults.
--read-back hashes by reading the files back (rclone checksum --download) where the
remote has no sha256. Exit code 1 and the list of faults otherwise.

publish: refuses (before anything is written) a dataset without a complete, approved row in PUBLISHABLE, one whose
master fails verify (the master is hashed on every run, a resumed one too: U36), one lacking a folder of a resolution
the catalogue declares for its source (GridTiles(averaged=)), a remote that reports no sha256 (unless --read-back) and
a server locked by another run. Then:
1. takes the lock (staging/.lock: the PC, the time, the command and a token of this run, read back after writing:
   the run goes on only with its own token there, and reads it again before the staged copy's deletes, each move,
   datasets.json and each removal of clean, stopping when another run's token is there; the seconds between such a
   read and the rclone call after it cannot be closed over SFTP; released only while it still holds that token;
   --break-lock after a crash). Under the lock it refuses, the lock released: a server whose sha256 of the lock file is not ours
   (a config may claim a hash the server cannot compute: U35; not with --read-back), a dataset already published
   unless --same-values (a re-encoding with the same values: a recut with other values is a new edition, a new
   folder name), and a <root> with less free space than the bytes not staged yet plus MARGIN_BYTES. The free space
   is rclone about's "free"; over SFTP that is the filesystem's free blocks (statvfs f_bfree, pkg/sftp's
   FreeSpace), which on Linux include the blocks reserved for root: the account may be able to write less;
2. copies exactly the files the indexes list and the indexes into staging/<dataset>/ (rclone copy --files-from: a
   rerun skips what is there), and writes the dataset's card README.md there from CARDS;
3. verifies the staged copy on the server against the master's sha256 (every file, the card too; any other file is a
   fault). A changed or unlisted staged file is deleted, the lock released and the tool stops: run it again;
4. moves public/v1/tiles/<dataset> to trash/<dataset>-<UTC> when it exists, then staging/<dataset> to
   public/v1/tiles/<dataset> (rclone moveto: a rename on the server; a target that exists is never moved onto, since
   rclone would merge into it), and after each move checks that the source is gone and the target holds the files
   expected. From the first move until datasets.json is written every failure stops the tool with the lock kept
   and says where the dataset is complete;
5. writes public/v1/datasets.json from the server's copy of every published dataset (through
   public/v1/.datasets.json.new, a dot-file the server does not serve, and a rename), releases the lock.
unpublish: the dataset to trash, datasets.json rewritten (a takedown: no row needed; only a folder that
public/v1/tiles lists). clean: removes the trash
folders whose UTC stamp is keep-days or more back. stats: requests and bytes per day and dataset, refusals per day
and limit, client versions, from the server's log files (access-YYYY-MM-DD.log, one JSON object per line: t, s, b,
rt, ds, a, lim, v); its output never holds an address.

Output: the tool's own lines and counts only, paths relative to the master ("<mirror>/...") or to <root>; never
rclone's raw output, the remote's name or the master's place. A stop after a failed rclone step quotes rclone's own
last error lines, cut and masked (Remote.says: no address, account, port, server path outside <root> or place of the
PC). Exit code 0, 1 (refused or faults), 2 (usage).
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sources.readers.tilebases import MIRROR_ENV, grid_tile_name  # noqa: E402

RCLONE_ENV = "FINDALINE_RCLONE"
MIN_VERSION = (1, 76)
MARGIN_BYTES = 10 * 10 ** 9   # free space kept on <root> beyond what a publish needs (P27)
KEEP_DAYS = 7                 # trash kept by clean (P27)
# The tiles per block folder side: an index's "block" must be present and equal to it (tools/sk_tiles.py BLOCK, which
# tools/mirror_tiles.py reuses; the client reads the tile paths with the same size and refuses another)
BLOCK = 10
HASH_THREADS = 8              # verify on a folder: files hashed at a time
STAMP = "%Y%m%dT%H%M%SZ"      # the UTC stamp of a trash folder's name

STAGING, TRASH, TILES = "staging", "trash", "public/v1/tiles"
LOCK = "staging/.lock"
LIST, LIST_TMP = "public/v1/datasets.json", "public/v1/.datasets.json.new"
CARD = "README.md"
TILE_FILE = re.compile(r"^(-?\d+)_(-?\d+)\.tif$")
TILE_KEY = re.compile(r"^-?\d+_-?\d+$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
# A dataset's name: the served pattern's <dataset> (A.2); nothing else reaches a path on the server
DATASET_NAME = re.compile(r"^[a-z0-9_-]+$")
# --to / --from: an rclone remote, "name:path" with a name of two characters or more (one letter is a drive)
REMOTE_PLACE = re.compile(r"^([^:/\\]+):(.*)$", re.S)
LOG_FILE = re.compile(r"^access-(\d{4}-\d{2}-\d{2})\.log$")
# What stats prints of the log's free fields (a visitor sends them): a limit's word; a dataset only when it is one of
# PUBLISHABLE (or "-"); a client version (the rule the server's log map shares): two or three numbers of at most three
# digits joined by dots, then optionally one of the words a, b, rc, .dev, .post, whose number is dropped, as is any
# local label ("+..."): 0.2.0rc1 counts as "0.2.0rc", 0.1.0+local as "0.1.0"; at most three numbers are printed, so
# no written form of an IPv4 address fits; "unknown" stays (cache._version's fallback); anything else "other"
LIMIT_WORD = re.compile(r"^[a-z_]{1,32}$")
CLIENT_VERSION = re.compile(r"(\d{1,3}(?:\.\d{1,3}){1,2})(?:(a|b|rc|\.dev|\.post)\d{0,4})?(?:\+[A-Za-z0-9.]{1,32})?")


def client_version(value: str) -> str:
    """The client version stats prints for the log's `v` (CLIENT_VERSION's rule), else "other"."""
    if value == "unknown":
        return value
    found = CLIENT_VERSION.fullmatch(value)
    return found[1] + (found[2] or "") if found else "other"
# rclone's own detection never adds sha256 (it tries md5 and sha1 only): the remote names it by hand
NO_SHA256 = ("the remote reports no sha256 among its hashes: set in the remote's section of the rclone config "
             "`shell_type = unix`, `hashes = sha256` and `sha256sum_command = sha256sum` (the server's shell must "
             "have sha256sum); without a shell on the server, `shell_type = none` and --read-back, which reads the "
             "files back instead")
# rclone's own error lines quoted in a stop text (Remote.says): the last SAYS_LINES of its ERROR, NOTICE and
# CRITICAL lines, SAYS_CHARS characters each, with what could name the server or the PC masked
SAYS_LINES, SAYS_CHARS = 2, 240
RCLONE_LINE = re.compile(r"^(?:\d{4}/\d\d/\d\d \d\d:\d\d:\d\d )?(ERROR|NOTICE|CRITICAL)\s*:\s*(.*)$")
SAYS_MASKS = [
    (re.compile(r"\b[a-z][a-z0-9+.-]*://\S*?(?=:\s|\s|$)", re.I), "<remote path>"),  # sftp://user@host:port//path
    (re.compile(r"\S+@\S+"), "<user@host>"),
    (re.compile(r"\b(dial \w+|lookup|connect to) \S+?(?=:\s|\s|$)", re.I), r"\1 <host>"),  # host:port dialled
    (re.compile(r"\[?[0-9a-f]*:[0-9a-f:]*:[0-9a-f]+\]?(:\d+)?", re.I), "<address>"),  # IPv6
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b"), "<address>"),
    (re.compile(r"(\\\\\?\\|//\?/)?\b[A-Za-z]:[\\/][^\s\"':]*"), "<local path>"),  # a path of the PC (Windows)
    (re.compile(r"(?<![\w<>.~])/(?:[\w.~-]+/)*[\w.~-]+"), "<path>"),  # any other absolute path (not below <root>)
]
EXIT_MEANING = {1: "an error", 2: "a usage error", 3: "a folder not found", 4: "a file not found",
                5: "a temporary error", 6: "a less serious error", 7: "a fatal error", 8: "the transfer limit",
                9: "nothing transferred", 10: "the time limit"}

ROW_FIELDS = ("dataset", "source_id", "title", "basis_kind", "licence", "licence_url", "basis_url", "basis_quote",
              "basis_checked", "changes", "not_endorsed", "notes", "approved")
BASIS_KINDS = ("licence", "metadata statement", "written permission")

# One row per dataset that may be published (the specification's B, "PUBLISHABLE"). A field without a fact holds
# "none" (P23); a row with an empty field, or without `approved` (the user's word and its date), is refused. The
# attribution is not a field: it is the catalogue's Credit of source_id (P22). `changes`: per product folder.
# Facts from local/mirror-hosting-2026-11-15/w0-publish/quotes.md (read 2026-11-15; L1-L8 there).
PUBLISHABLE: Dict[str, Dict] = {
    "slovakia": dict(
        dataset="slovakia", source_id="slovakia",
        title="Slovakia: DMR 5.0 terrain and DMP 1.0 surface models, ALS 2017-2023, 1 m (ÚGKK SR), as 2 km tiles",
        basis_kind="licence", licence="CC BY 4.0", licence_url="https://creativecommons.org/licenses/by/4.0/",
        basis_url="https://www.skgeodesy.sk/files/geoportal/zbgis/licencie/licencne_podmienky_produkty_lls.pdf",
        basis_quote="Licenčné podmienky pre produkty leteckého laserového skenovania / Autor ÚGKK SR / "
                    "Licencia CC-BY 4.0",
        basis_checked="2026-11-15",
        changes={
            "dmr5/1m": "cut into 2 km x 2 km Cloud Optimized GeoTIFFs on the national pixel grid, LERC within 5 mm",
            "dmr5/2m": "the mean of the valid 1 m pixels of each 2 x 2 block, float32 without further loss",
            "dmr5/5m": "the mean of the valid 1 m pixels of each 5 x 5 block, float32 without further loss",
            "dmp1/1m": "cut into 2 km x 2 km Cloud Optimized GeoTIFFs on the national pixel grid, LERC within 5 mm",
            "dmp1/2m": "the mean of the valid 1 m pixels of each 2 x 2 block, float32 without further loss",
            "dmp1/5m": "the mean of the valid 1 m pixels of each 5 x 5 block, float32 without further loss"},
        not_endorsed="Made for Find-a-Line (a highline finder); not endorsed by ÚGKK SR.",
        notes="The credit as ÚGKK SR's provision page asks it: \"ÚGKK SR\" (https://www.skgeodesy.sk/geoportal/zbgis/"
              "lls/poskytovanie/). CC BY 4.0 2(a)(5)(B): no further terms or technological measures that restrict "
              "a recipient; 3(a)(3): the credit is removed if the licensor asks. ÚGKK SR's second cycle (DMR 6.0 / "
              "DMP 2.0, 0.5 m) would be a new dataset.",
        approved="a (approve), the user's word of 2026-11-16 (U31)"),
    "madeira": dict(
        dataset="madeira", source_id="madeira",
        title="Madeira island: MDT 2 m, photogrammetry 2018-2019 (DROTe, Região Autónoma da Madeira), as 2 km tiles",
        basis_kind="metadata statement", licence="none", licence_url="none",
        basis_url="https://snig.dgterritorio.gov.pt/rndg/srv/api/records/abba9a83-cb1c-4d2c-ad1d-ccb592247754/"
                  "formatters/xml",
        basis_quote="useLimitation: \"No conditions apply\"; otherConstraints: \"Acesso e uso sem condições\", "
                    "\"Acesso público sem restrições\"",
        basis_checked="2026-11-15",
        changes={"dtm/2m": "the BigTIFF cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own pixel grid, its "
                           "no-data values (-32768, -999) made no data, LERC within 5 mm"},
        not_endorsed="Made for Find-a-Line (a highline finder); not endorsed by DROTe.",
        notes="A weak basis (no licence document found). Against it, all in the regional Portaria 36/2022 "
              "(https://joram.madeira.gov.pt/joram/1serie/Ano%20de%202022/ISerie-022-2022-02-09.pdf): obtaining "
              "DROTe's products \"está sujeita ao pagamento do respetivo preço\" (Art. 3.º 1), its price table lists "
              "\"MDT 2 m (folha)\" at 42 EUR, the use licences of Art. 4 are to be published by DROTe (not found), "
              "commercial use is named only for the region's own services; whether today's free file is that priced "
              "product is not established. Art. 3.º 4: end users are told of every change (the card). An objection "
              "is answered with unpublish.",
        approved="publish, the user's word of 2026-11-15 (U11)"),
    "aosta": dict(
        dataset="aosta", source_id="aosta_valley",
        title="Valle d'Aosta: DTM 2005/2008 2 m (Regione Autonoma Valle d'Aosta), as 2 km tiles",
        basis_kind="licence", licence="CC BY 4.0",
        licence_url="https://metadati.partout.it/metadata_documents/CC_BY_DTM_v2.pdf",
        basis_url="https://metadati.partout.it/metadata_documents/CC_BY_DTM_v2.pdf",
        basis_quote="la Regione concede all'utente i dati del Modello Digitale del Terreno (DTM) con licenza Creative "
                    "Commons Attribuzione 4.0 Internazionale (CC BY 4.0). ... Condividere - riprodurre, distribuire, "
                    "comunicare al pubblico ... con qualsiasi mezzo e formato. Modificare - remixare, trasformare il "
                    "materiale e basarsi su di esso per le sue opere; per qualsiasi fine, anche commerciale.",
        basis_checked="2026-11-15",
        changes={"dtm/2m": "the ESRI ASCII grid cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own pixel grid, "
                           "its no-data value (-9999) made no data, LERC within 5 mm"},
        not_endorsed="Made for Find-a-Line (a highline finder); not endorsed by the Regione Autonoma Valle d'Aosta.",
        notes="The licence asks for its credit sentence word for word, a link to the licence and whether changes were "
              "made (the card). A second PDF on the same server (open_data_dtm.pdf) names CC BY 2.5 Italia and its "
              "own sentence does not name distributing. \"non per download massivi\" stands only in the catalogue's "
              "comment (sources/catalogue/italy.py), which credits it to the service's istruzioni.pdf; that PDF "
              "answered 404 on 2026-11-15 and the sentence was not seen there; as quoted it is about the download "
              "service, not about redistribution.",
        approved="publish, the user's word of 2026-11-15 (U12)"),
}


def cards() -> Dict[str, str]:
    """The dataset cards (README.md) the mirror serves, written by publish (P21): the texts of the tools that cut
    the datasets."""
    import sk_tiles
    import mirror_tiles
    found = {"slovakia": sk_tiles.CARD}
    for spec in mirror_tiles.DATASETS.values():
        found[spec["folder"]] = spec["card"]
    return found


def row_faults(row: Dict) -> List[str]:
    """What keeps a PUBLISHABLE row from being published: a field missing or empty (a fact that does not exist is
    "none"), an unknown basis kind, no `approved`."""
    faults = []
    for field in ROW_FIELDS:
        value = row.get(field)
        if not value or (isinstance(value, str) and not value.strip()) or \
                (isinstance(value, dict) and not all(str(v).strip() for v in value.values())):
            faults.append(f"{field} is empty" if field != "approved" else "not approved (no `approved`)")
    if row.get("basis_kind") and row["basis_kind"] not in BASIS_KINDS:
        faults.append(f"basis_kind {row['basis_kind']!r} is none of {', '.join(BASIS_KINDS)}")
    return faults


def source_of(source_id: str):
    from sources.catalogue import SOURCES
    return SOURCES[source_id]


def attribution(source_id: str) -> str:
    """The credit of a dataset: its catalogue source's (P22)."""
    return source_of(source_id).attribution


def required_folders(source_id: str) -> List[str]:
    """The mirror folders the catalogue reads for a source (<dataset>/<product>/<res>m): every GridTiles layer's
    native folder and each of its averaged resolutions (GridTiles(averaged=); P12)."""
    from sources.layers.gridtiles import GridTiles
    src = source_of(source_id)
    found = []
    for layer in (src.nmt, src.nmpt):
        if isinstance(layer, GridTiles):
            found += [reader.mirror for reader in layer.readers.values() if reader.mirror]
    return found


# Errors

class Refused(Exception):
    """Refused before anything was written."""


class Failed(Exception):
    """Stopped after the lock was taken; keep_lock: the lock is left (the server's state needs a look)."""

    def __init__(self, message: str, keep_lock: bool = False):
        super().__init__(message)
        self.keep_lock = keep_lock


class NoRclone(Failed):
    """rclone could not be started (it was there at the start)."""


class BadIndex(ValueError):
    """An index.json that is not what tools/sk_tiles.py writes."""


def check_dataset(name: str) -> str:
    """name when it is a dataset's name ([a-z0-9_-]+, the served pattern's); Refused before any request otherwise."""
    if not isinstance(name, str) or not DATASET_NAME.fullmatch(name):
        raise Refused(f"{name!r} is not a dataset's name (lower-case letters, digits, '_' and '-' only)")
    return name


def _meaning(code: int) -> str:
    return f"exit {code}: {EXIT_MEANING.get(code, 'an error')}"


# rclone

class Rclone:
    """rclone run with its output captured, never printed (a log file, --log, gets its messages); config: the
    rclone config file passed to every call (None: rclone's own default)."""

    def __init__(self, exe: str, config: Optional[str] = None, log: Optional[str] = None):
        self.exe, self.config, self.log = exe, config, log

    def run(self, *args: str, data: Optional[bytes] = None, progress: Optional[str] = None
            ) -> subprocess.CompletedProcess:
        argv = [self.exe] + (["--config", self.config] if self.config else []) + list(args)
        try:
            done = self._call(argv, data, progress)
        except OSError as e:
            raise NoRclone(f"rclone could not be started ({type(e).__name__})") from None
        if self.log and done.stderr:
            with open(self.log, "ab") as f:
                f.write(done.stderr)
        return done

    def _call(self, argv: List[str], data: Optional[bytes], progress: Optional[str]) -> subprocess.CompletedProcess:
        """One rclone process (tests patch this). progress: a label; rclone's one-line statistics are read from its
        messages every minute and printed as the tool's own line."""
        if progress is None:
            return subprocess.run(argv, input=data, capture_output=True)
        argv = argv + ["--stats", "60s", "--stats-one-line", "--stats-log-level", "NOTICE"]
        stats = re.compile(r"NOTICE:\s+([\d.]+ \S*B) / ([\d.]+ \S*B), (\d+|-)%, ([\d.]+ \S*B/s), ETA (\S+)")
        with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            err = []
            for line in proc.stderr:
                err.append(line)
                found = stats.search(line.decode("utf-8", "replace"))
                if found:
                    print(f"  {progress}: {found[1]} of {found[2]}, {found[3]} %, {found[4]}, ETA {found[5]}",
                          flush=True)
            out = proc.stdout.read()
            proc.wait()
        return subprocess.CompletedProcess(argv, proc.returncode, out, b"".join(err))

    def version(self) -> Tuple[int, ...]:
        done = self.run("version")
        found = re.match(rb"rclone v(\d+)\.(\d+)(?:\.(\d+))?", done.stdout.strip())
        if done.returncode or not found:
            raise Refused(f"rclone did not tell its version ({_meaning(done.returncode)})")
        return tuple(int(x or 0) for x in found.groups())


def find_rclone() -> str:
    exe = os.environ.get(RCLONE_ENV) or shutil.which("rclone")
    if not exe or not (os.path.isfile(exe) or shutil.which(exe)):
        raise Refused(f"rclone was not found: install rclone {'.'.join(map(str, MIN_VERSION))} or newer, or set "
                      f"{RCLONE_ENV} to its executable")
    return exe


def make_rclone(config: Optional[str] = None, log: Optional[str] = None) -> Rclone:
    """rclone found and of MIN_VERSION or newer (Refused otherwise)."""
    rc = Rclone(find_rclone(), config, log)
    version = rc.version()
    if version[:2] < MIN_VERSION:
        raise Refused(f"rclone {'.'.join(map(str, version))} is too old: {'.'.join(map(str, MIN_VERSION))} or newer "
                      "is needed")
    return rc


def parse_remote(text: str) -> str:
    """A --to / --from argument: an rclone remote, "name:path" with a name of two characters or more. A bare word
    or a local path is refused (it would publish into a folder of the PC), so is a one-letter name (rclone takes it
    for a drive letter on Windows)."""
    found = REMOTE_PLACE.fullmatch(text or "")
    if not found:
        raise Refused("--to and --from name an rclone remote: name:path (the remote of the server, from the rclone "
                      "config)")
    if len(found[1]) == 1:
        raise Refused("a remote's name of one letter is taken for a drive letter on Windows: rename the remote")
    return text


class Remote:
    """<root> on the server (or a folder), through rclone; every path given relative to it. local: folders of the PC
    (the master) masked like the remote's own places when rclone's error lines are quoted (says)."""

    def __init__(self, rc: Rclone, root: str):
        self.rc, self.root = rc, root
        self.local: List[str] = []
        self._places: Optional[List[Tuple[str, str]]] = None

    def _masks(self) -> List[Tuple[str, str]]:
        """(text, its stand-in) of the places rclone's lines may name: the remote's description and root as rclone
        resolves them (backend features: String, Root, in every spelling of the path), the remote's name, the
        master; asked once, nothing when rclone cannot answer."""
        if self._places is None:
            places: List[Tuple[str, str]] = []
            try:
                done = self.rc.run("backend", "features", self.path())
                info = json.loads(done.stdout) if done.returncode == 0 else {}
            except (Failed, ValueError):
                info = {}
            for key, stand_in in (("String", "<remote>"), ("Root", "<root>")):
                value = str(info.get(key) or "")
                for spelling in {value, value.replace("//?/", ""), value.replace("/", "\\"),
                                 value.replace("//?/", "").replace("/", "\\")}:
                    if len(spelling.strip("/\\")) > 1:
                        places.append((spelling, stand_in))
            for folder in self.local:
                for spelling in {folder, folder.replace("\\", "/"), os.path.abspath(folder)}:
                    places.append((spelling, "<mirror>"))
            name = REMOTE_PLACE.fullmatch(self.root)
            if name:
                places.append((name[1] + ":", "<remote>:"))
            self._places = sorted(set(places), key=lambda m: -len(m[0]))
        return self._places

    def says(self, done) -> str:
        """rclone's own last error lines of a call, for the stop text: at most SAYS_LINES lines of at most SAYS_CHARS
        characters each, its date and level dropped, every place masked (_masks), and every URL, user@host, address
        and host it dialled or looked up replaced, so neither the server's address and account nor a place of the
        PC is printed. rclone's lines hold the operation, the path and the error of the server or the system; they
        never hold the config's values or a key's content (rclone prints no config line in an error, and keeps
        passwords obscured)."""
        lines = []
        for raw in (done.stderr or b"").decode("utf-8", "replace").splitlines():
            found = RCLONE_LINE.match(raw)
            if not found or "host key validation" in found[2]:
                continue
            text = found[2]
            for place, stand_in in self._masks():
                text = text.replace(place, stand_in)
            for pattern, stand_in in SAYS_MASKS:
                text = pattern.sub(stand_in, text)
            text = text.strip()[:SAYS_CHARS]
            if text and text not in lines:
                lines.append(text)
        return " | ".join(lines[-SAYS_LINES:])

    def path(self, rel: str = "") -> str:
        if not rel:
            return self.root
        return self.root + rel if self.root.endswith((":", "/", "\\")) else f"{self.root}/{rel}"

    def _failed(self, what: str, rel: str, done) -> Failed:
        said = self.says(done)
        return Failed(f"rclone could not {what} {rel or '<root>'} ({_meaning(done.returncode)})"
                      + (f"; rclone: {said}" if said else ""))

    def exists(self, rel: str) -> bool:
        """Whether rel exists; any answer but "found" or "not found" stops the tool."""
        done = self.rc.run("lsjson", "--stat", "--no-mimetype", self.path(rel))
        if done.returncode == 0:
            return True
        if done.returncode in (3, 4):
            return False
        raise self._failed("read", rel, done)

    def listing(self, rel: str) -> Optional[Dict[str, int]]:
        """Every file below rel with its size ({path below rel: bytes}); None when rel does not exist."""
        done = self.rc.run("lsjson", "-R", "--files-only", "--no-mimetype", "--no-modtime", self.path(rel))
        if done.returncode in (3, 4):
            return None
        if done.returncode:
            raise self._failed("list", rel, done)
        return {e["Path"]: int(e["Size"]) for e in json.loads(done.stdout)}

    def folders(self, rel: str) -> List[str]:
        """The folders directly in rel ([] when rel does not exist)."""
        done = self.rc.run("lsjson", "--dirs-only", "--no-mimetype", "--no-modtime", self.path(rel))
        if done.returncode in (3, 4):
            return []
        if done.returncode:
            raise self._failed("list", rel, done)
        return sorted(e["Name"] for e in json.loads(done.stdout))

    def cat(self, rel: str) -> bytes:
        done = self.rc.run("cat", self.path(rel))
        if done.returncode:
            raise self._failed("read", rel, done)
        return done.stdout

    def write(self, rel: str, data: bytes):
        done = self.rc.run("rcat", self.path(rel), data=data)
        if done.returncode:
            raise self._failed("write", rel, done)

    def delete(self, rel: str):
        done = self.rc.run("deletefile", self.path(rel))
        if done.returncode:
            raise self._failed("delete", rel, done)

    def move(self, rel: str, to: str, keep_lock: bool = True):
        """rel renamed to `to` on the server (rclone moveto, no retry: a refused rename is not tried again file by
        file); `to` must not exist, as rclone would merge into it."""
        if self.exists(to):
            raise Failed(f"{to} exists: {rel} is not moved onto it", keep_lock)
        done = self.rc.run("moveto", "--retries", "1", self.path(rel), self.path(to))
        if done.returncode:
            said = self.says(done)
            source, target = rel.split("/")[0] + "/", to.split("/")[0] + "/"
            raise Failed(f"the server refused the move of {rel} to {to} ({_meaning(done.returncode)})"
                         + (f": {said}" if said else "") + f". Likely causes: the publishing account may not write "
                         f"{target} (its owner), or {source} and {target} are on different disks", keep_lock)

    def free(self) -> Optional[int]:
        """Free bytes of <root>'s disk (rclone about), None when the server does not tell."""
        done = self.rc.run("about", "--json", self.path())
        if done.returncode:
            return None
        try:
            free = json.loads(done.stdout).get("free")
        except ValueError:
            return None
        return int(free) if free is not None else None

    def hashes(self) -> List[str]:
        """The hash types the remote reports (rclone backend features)."""
        done = self.rc.run("backend", "features", self.path())
        if done.returncode:
            raise self._failed("read the features of", "", done)
        return [h.lower() for h in json.loads(done.stdout).get("Hashes") or []]

    def sha256_of(self, rel: str) -> Optional[str]:
        """The sha256 of one file as the server computes it (rclone hashsum sha256), None when it gives none."""
        done = self.rc.run("hashsum", "sha256", self.path(rel))
        first = done.stdout.split()[:1] if done.returncode == 0 else []
        digest = first[0].decode("ascii", "replace").lower() if first else ""
        return digest if DIGEST.fullmatch(digest) else None

    def checksum(self, sums: Dict[str, str], rel: str, read_back: bool) -> Dict[str, List[str]]:
        """rel's files against sums ({path below rel: sha256}) by rclone checksum (the server hashes; read_back:
        rclone reads the files back): {"=": same, "*": different, "+": missing, "-": not in sums, "!": unreadable}.
        """
        with tempfile.TemporaryDirectory(prefix="mirror-publish-") as tmp:
            sum_file, combined = os.path.join(tmp, "SUM"), os.path.join(tmp, "combined.txt")
            with open(sum_file, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(f"{digest}  {path}\n" for path, digest in sorted(sums.items()))
            done = self.rc.run("checksum", "sha256", sum_file, self.path(rel), "--combined", combined,
                               *(["--download"] if read_back else []))
            found: Dict[str, List[str]] = {mark: [] for mark in "=*+-!"}
            if os.path.exists(combined):
                with open(combined, encoding="utf-8") as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if len(line) > 2 and line[0] in found and line[1] == " ":
                            found[line[0]].append(line[2:])
        if done.returncode and not any(found[m] for m in "*+-!"):
            raise self._failed("check the hashes of", rel, done)
        return found


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# verify

def _index_tiles(index) -> Dict[str, str]:
    """{path below the product folder: sha256} of an index's tiles with data; BadIndex for an index that is not
    what the cutting tools write (a "tiles" object of <i>_<j> keys with 64 hex digits or null, "block" present
    and BLOCK)."""
    if not isinstance(index, dict) or not isinstance(index.get("tiles"), dict):
        raise BadIndex("no \"tiles\" object")
    block = index.get("block")
    if isinstance(block, bool) or not isinstance(block, int) or block != BLOCK:
        raise BadIndex(f"block {str(block)[:20]!r} is not {BLOCK} (the block size of the tile paths)")
    tiles = {}
    for key, digest in index["tiles"].items():
        if not TILE_KEY.fullmatch(key):
            raise BadIndex(f"key {key[:30]!r} is not a tile's <i>_<j>")
        if digest is None:
            continue
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise BadIndex(f"the sha256 of {key} is not 64 hex digits")
        tiles[grid_tile_name(*map(int, key.split("_")), block)] = digest
    return tiles


def _unindexed(paths: Iterable[str], indexed: set) -> List[str]:
    """The product folders (the folder above a tile's block folder) that hold tile files but no index.json, from
    paths below one root ("" for the root itself)."""
    found = set()
    for path in paths:
        parts = path.split("/")
        if TILE_FILE.fullmatch(parts[-1]):
            product = "/".join(parts[:-2])
            if product not in indexed:
                found.add(product)
    return sorted(found)


def read_master(folder: str, label: str) -> Tuple[List[str], Dict[str, Tuple[str, int]]]:
    """A mirror folder (a dataset's, or the whole mirror) verified by hashing every listed tile: (faults,
    {path below folder: (sha256, bytes)} of every listed tile and every index.json). label stands for folder in
    the faults."""
    faults: List[str] = []
    files: Dict[str, Tuple[str, int]] = {}
    jobs = []
    indexes = sorted(os.path.relpath(root, folder).replace("\\", "/")
                     for root, _, names in os.walk(folder) if "index.json" in names)
    if not indexes:
        return [f"{label}: no index.json below it"], files
    for rel in indexes:
        prefix = "" if rel == "." else rel + "/"
        here = os.path.join(folder, *prefix.split("/"))
        index_path = os.path.join(here, "index.json")
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
            tiles = _index_tiles(index)
        except BadIndex as e:
            faults.append(f"{label}/{prefix}index.json: malformed ({e})")
            continue
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            faults.append(f"{label}/{prefix}index.json: cannot be read ({type(e).__name__})")
            continue
        if index.get("partial"):
            faults.append(f"{label}/{prefix}index.json: partial (still being cut)")
        files[prefix + "index.json"] = (_sha256(index_path), os.path.getsize(index_path))
        for sub, _, names in os.walk(here):
            for name in names:
                if TILE_FILE.fullmatch(name):
                    path = os.path.relpath(os.path.join(sub, name), here).replace("\\", "/")
                    if path not in tiles:
                        faults.append(f"{label}/{prefix}{path}: not listed in its index")
        for path, digest in tiles.items():
            jobs.append((prefix + path, digest))
    every = (os.path.relpath(os.path.join(root, name), folder).replace("\\", "/")
             for root, _, names in os.walk(folder) for name in names)
    for product in _unindexed(every, {"" if rel == "." else rel for rel in indexes}):
        faults.append(f"{label}/{product + '/' if product else ''}: tiles without an index.json")
    start, last = time.time(), time.time()

    def check(job):
        path, digest = job
        full = os.path.join(folder, *path.split("/"))
        if not os.path.isfile(full):
            return path, digest, None, "missing"
        found = _sha256(full)
        return path, digest, os.path.getsize(full), None if found == digest else "sha256 differs from its index"

    with ThreadPoolExecutor(max_workers=HASH_THREADS) as pool:
        for n, (path, digest, size, fault) in enumerate(pool.map(check, jobs), 1):
            if fault:
                faults.append(f"{label}/{path}: {fault}")
            else:
                files[path] = (digest, size)
            if time.time() - last > 30:
                last = time.time()
                print(f"  {n}/{len(jobs)} tiles hashed, {(time.time() - start) / 60:.1f} min", flush=True)
    return faults, files


def verify_remote(remote: Remote, read_back: bool) -> Tuple[List[str], int]:
    """Every index.json below the remote path, checked by the server's hashes: (faults, tiles checked)."""
    listing = remote.listing("")
    if listing is None:
        return ["<path>: not found"], 0
    indexes = sorted(p for p in listing if p == "index.json" or p.endswith("/index.json"))
    if not indexes:
        return ["<path>: no index.json below it"], 0
    faults, checked = [], 0
    for product in _unindexed(listing, {p[:-len("index.json")].rstrip("/") for p in indexes}):
        faults.append(f"{product + '/' if product else ''}: tiles without an index.json")
    for index_rel in indexes:
        folder = index_rel[:-len("index.json")].rstrip("/")
        try:
            index = json.loads(remote.cat(index_rel))
            tiles = _index_tiles(index)
        except BadIndex as e:
            faults.append(f"{index_rel}: malformed ({e})")
            continue
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            faults.append(f"{index_rel}: cannot be read ({type(e).__name__})")
            continue
        if index.get("partial"):
            faults.append(f"{index_rel}: partial (still being cut)")
        found = remote.checksum(tiles, folder, read_back)
        prefix = folder + "/" if folder else ""
        faults += [f"{prefix}{p}: sha256 differs from its index" for p in found["*"]]
        faults += [f"{prefix}{p}: missing" for p in found["+"]]
        faults += [f"{prefix}{p}: could not be hashed" for p in found["!"]]
        faults += [f"{prefix}{p}: not listed in its index" for p in found["-"] if p != "index.json"]
        checked += len(tiles)
    return faults, checked


def verify(place: str, rc: Optional[Rclone], read_back: bool = False) -> int:
    if os.path.isdir(place):
        print("verify: <folder>", flush=True)
        faults, files = read_master(place, "<folder>")
        checked = sum(1 for p in files if not p.endswith("index.json"))
    else:
        rc = rc or make_rclone()
        remote = Remote(rc, parse_remote(place))
        if not read_back and "sha256" not in remote.hashes():
            raise Refused(NO_SHA256)
        print("verify: <remote>", flush=True)
        faults, checked = verify_remote(remote, read_back)
    for fault in faults:
        print(f"  fault: {fault}")
    print(f"{checked} tiles checked, {len(faults)} faults")
    return 1 if faults else 0


# publish

class LostLock(Failed):
    """The lock holds another run's token (or none) at a check point: this run stops and leaves that lock alone."""


class PartlyDone(Failed):
    """The work is done; only the lock could not be removed."""


class Lock:
    """staging/.lock: a JSON file naming the PC, the time, the command and a token of this run. Taken only when no
    lock is there (unless broken), then read back: the run goes on only with its own token in it, and reads it again
    (ensure) before every step that changes the server after the copy: the staged copy's deletes, each move,
    datasets.json, each removal of clean. A second run that got in, or --break-lock against a run that works, stops
    that run at its next check point; the seconds between a check and the rclone call after it cannot be closed over
    SFTP (no atomic test-and-set there). Released only by the run whose token it still holds; a staging/ folder the
    lock made on a fresh <root> is removed with it when empty. `hold`: once set (the first move started), every
    failure keeps the lock and the message names where the dataset is."""

    def __init__(self, remote: Remote, command: str, force: bool):
        self.remote, self.command, self.force = remote, command, force
        self.taken, self.token, self.text, self.hold, self.made_folder = False, None, b"", None, False

    def check(self):
        """Refused while another run's lock is there (its time and command are named, never its PC)."""
        if self.remote.exists(LOCK) and not self.force:
            try:
                held = json.loads(self.remote.cat(LOCK))
                since = f" since {held.get('time')} ({held.get('command')})"
            except (ValueError, Failed, AttributeError):
                since = ""
            raise Refused(f"the server is locked{since}: another run is going on, or one stopped; --break-lock "
                          "after a crash, once the server's state is understood")

    def _held(self) -> Optional[str]:
        """The token in the lock now (None: no lock, or not a lock of this tool)."""
        if not self.remote.exists(LOCK):
            return None
        try:
            return json.loads(self.remote.cat(LOCK)).get("token")
        except (ValueError, AttributeError):
            return None

    def take(self):
        self.check()
        token = secrets.token_hex(16)
        text = json.dumps({"pc": socket.gethostname(), "time": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "command": self.command, "token": token}).encode("utf-8")
        self.made_folder = not self.remote.exists(STAGING)
        self.token, self.text = token, text  # known before the write: an interruption during it can still release
        try:
            self.remote.write(LOCK, text)
        except Failed as e:
            # rclone checks an upload's hash when the remote claims one: on a server that cannot compute it the
            # write "fails" with the file written (seen over SFTP). Ours when it holds our token; the hash proof
            # then refuses and releases it
            self.taken, self.token, self.text = True, token, text
            if self._held() != token:
                self.taken = False
                raise Failed(f"{e}; a lock file may be left on the server: --break-lock once the server's state is "
                             "understood") from None
        self.taken, self.token, self.text = True, token, text
        if self._held() != token:
            self.taken = False  # another run's lock now: never touched
            raise Refused("another run took the lock at the same moment: nothing was done; run again later")

    def ensure(self, step: str):
        """The lock still holds this run's token before step; LostLock otherwise (nothing more is touched)."""
        if self._held() != self.token:
            self.taken = False
            raise LostLock(f"another run took the lock (or it was broken) before {step}: this run stopped without "
                           "touching anything more and left that lock alone")

    def prove_hashing(self):
        """U35: the server's sha256 of the lock file equals ours (its config may claim a hash it cannot compute)."""
        if self.remote.sha256_of(LOCK) != hashlib.sha256(self.text).hexdigest():
            self.ensure("the server's hash of the lock file is checked")  # another run's lock hashes otherwise
            raise Refused("the server could not hash the lock file: " + NO_SHA256)

    def release(self, written: bool = False) -> str:
        """The lock deleted when it still holds this run's token; left (and said so) when another run's is there.
        written: release also when take() was interrupted (the write may have reached the server). Returns
        "released", "foreign" (another run's lock left), "none" (no lock there) or "" (nothing of this run's)."""
        if not (self.taken or (written and self.token)):
            return ""
        self.taken = False
        held = self._held()
        if held == self.token:
            self.remote.delete(LOCK)
            if self.made_folder:
                try:  # only when empty (rclone rmdir); the lock is gone whatever happens here
                    self.remote.rc.run("rmdir", self.remote.path(STAGING))
                except Failed:
                    pass
            return "released"
        if held is not None or self.remote.exists(LOCK):
            print(f"  {LOCK} holds another run's lock now: left as it is", flush=True)
            return "foreign"
        return "none"


def locked(lock: Lock, work, done: str) -> None:
    """work() under the lock: taken first; released after it, and after a failure before lock.hold is set;
    kept after a failure once lock.hold names where the dataset is (the message then says so). rclone that cannot
    be started any more leaves the lock, and the message says so; a lock another run holds now is left alone. done:
    what a successful work() did, said when only the final release fails (PartlyDone). Ctrl+C or an unexpected error
    under the lock: released before the first move, kept after it, one line says which."""
    try:
        lock.take()
        work()
    except LostLock as e:
        where = f"; {lock.hold}" if lock.hold else ""
        raise Failed(f"{e}{where}", keep_lock=True) from None
    except NoRclone as e:
        if not lock.text:  # stopped before the lock was written
            raise
        raise Failed(f"{e}; the lock {LOCK} is left: --break-lock once the server's state is understood",
                      keep_lock=True) from None
    except (Failed, Refused) as e:
        if lock.hold is not None or getattr(e, "keep_lock", False):
            where = f"; {lock.hold}" if lock.hold and lock.hold not in str(e) else ""
            raise Failed(f"{e}{where} (the lock {LOCK} is kept: look at the server, then --break-lock)",
                         keep_lock=True) from None
        try:
            lock.release()
        except Failed:
            raise Failed(f"{e}; the lock {LOCK} could not be released: --break-lock") from None
        raise
    except BaseException as e:  # Ctrl+C, or an error the tool does not expect
        if lock.hold is None:
            try:
                note = {"released": "the lock was released; nothing public was touched",
                        "foreign": "nothing public was touched; another run's lock is there and was left",
                        "none": "nothing public was touched; no lock of this run is there",
                        "": "nothing public was touched; no lock was written"}[lock.release(written=True)]
            except BaseException:
                note = f"the lock {LOCK} may be left: --break-lock once the server's state is understood"
        else:
            note = f"the lock {LOCK} is kept: {lock.hold}; look at the server, then --break-lock"
        print(f"interrupted ({type(e).__name__}): {note}", flush=True)
        raise
    try:
        lock.release()
    except Failed as e:
        raise PartlyDone(f"{done}; only the lock {LOCK} could not be removed ({e}): --break-lock") from None


def _stamp() -> str:
    return _now().strftime(STAMP)


def _to_trash(remote: Remote, dataset: str):
    """public/v1/tiles/<dataset> moved to trash/<dataset>-<UTC>, checked."""
    source, trash = f"{TILES}/{dataset}", f"{TRASH}/{dataset}-{_stamp()}"
    before = remote.listing(source) or {}
    checked_move(remote, source, trash, set(before))


def checked_move(remote: Remote, source: str, target: str, expected: set):
    """source renamed to target (Remote.move), then checked: source gone, target holding exactly the expected files
    (a move that fell back to copying, or stopped in the middle, shows here). Failed with the lock kept otherwise,
    naming where the complete copy is."""
    remote.move(source, target)
    try:
        left, after = remote.listing(source), remote.listing(target) or {}
    except Failed as e:
        raise Failed(f"{e}: the move from {source} to {target} could not be checked; the complete copy is in one of "
                     "them", keep_lock=True) from None
    if left is None and set(after) == expected:
        print(f"  {source} moved to {target} ({len(after)} files)", flush=True)
        return
    where = (target if set(after) == expected else source if left is not None and set(left) == expected
             else f"neither ({source}: {len(left or {})} files, {target}: {len(after)} of {len(expected)})")
    raise Failed(f"after the move from {source} to {target} the source is {'left' if left is not None else 'gone'} "
                 f"and the target holds {len(after)} of {len(expected)} files: the complete copy is in {where}",
                 keep_lock=True)


def write_datasets(remote: Remote) -> Dict:
    """public/v1/datasets.json from the server's copy of every published dataset (through LIST_TMP and a rename);
    its content. A published folder without a row in PUBLISHABLE stops it (its credit would be lost)."""
    entries = []
    for dataset in remote.folders(TILES):
        row = PUBLISHABLE.get(dataset)
        if row is None:
            raise Failed(f"{TILES}/{dataset} has no row in PUBLISHABLE: datasets.json is not written", keep_lock=True)
        listing = remote.listing(f"{TILES}/{dataset}") or {}
        products = []
        for index_rel in sorted(p for p in listing if p.endswith("/index.json")):
            folder = index_rel[:-len("/index.json")]
            data = remote.cat(f"{TILES}/{dataset}/{index_rel}")
            tiles = {p: size for p, size in listing.items()
                     if p.startswith(folder + "/") and TILE_FILE.fullmatch(p.rsplit("/", 1)[-1])}
            products.append({"path": f"{dataset}/{folder}", "tiles": len(tiles),
                             "bytes": sum(tiles.values()) + listing[index_rel],
                             "index_sha256": hashlib.sha256(data).hexdigest()})
        entries.append({"id": dataset, "title": row["title"], "licence": row["licence"],
                        "attribution": attribution(row["source_id"]), "source": row["basis_url"],
                        "products": products})
    content = {"version": 1, "generated": _now().strftime("%Y-%m-%dT%H:%M:%SZ"), "datasets": entries}
    remote.write(LIST_TMP, json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8"))
    done = remote.rc.run("moveto", "--retries", "1", remote.path(LIST_TMP), remote.path(LIST))
    if done.returncode:
        said = remote.says(done)
        raise Failed(f"rclone could not rename {LIST_TMP} to {LIST} ({_meaning(done.returncode)})"
                     + (f"; rclone: {said}" if said else ""), keep_lock=True)
    print(f"  {LIST}: {len(entries)} datasets", flush=True)
    return content


def publish(dataset: str, to: str, rc: Rclone, mirror: Optional[str], same_values: bool = False,
            break_lock: bool = False, read_back: bool = False) -> int:
    check_dataset(dataset)
    row = PUBLISHABLE.get(dataset)
    if row is None:
        raise Refused(f"{dataset}: no row in PUBLISHABLE (only {', '.join(sorted(PUBLISHABLE))} may be published)")
    faults = row_faults(row)
    if faults:
        raise Refused(f"{dataset}: its PUBLISHABLE row is not complete: {'; '.join(faults)}")
    card = cards().get(dataset)
    if not card:
        raise Refused(f"{dataset}: no card text")
    remote = Remote(rc, parse_remote(to))
    mirror = mirror or os.environ.get(MIRROR_ENV)
    if mirror:
        remote.local.append(mirror)
    if not mirror or not os.path.isdir(mirror):
        raise Refused(f"no master: set {MIRROR_ENV} or --mirror to the mirror folder")
    folder = os.path.join(mirror, dataset)
    label = f"<mirror>/{dataset}"
    if not os.path.isdir(folder):
        raise Refused(f"{label} does not exist")
    for need in required_folders(row["source_id"]):
        if not os.path.isfile(os.path.join(mirror, *need.split("/"), "index.json")):
            raise Refused(f"<mirror>/{need}: no index.json, and the catalogue reads that resolution "
                          f"(source {row['source_id']})")
    print(f"publish {dataset}: verifying {label}", flush=True)
    faults, files = read_master(folder, label)
    if faults:
        for fault in faults:
            print(f"  fault: {fault}")
        raise Refused(f"{label} fails verify ({len(faults)} faults)")
    if not read_back and "sha256" not in remote.hashes():
        raise Refused(NO_SHA256)
    if not remote.exists(""):
        raise Refused("<root> does not exist on the server (the mirror stack's install makes it)")
    lock = Lock(remote, f"publish {dataset}", break_lock)
    lock.check()
    card_bytes = card.encode("utf-8")
    staging, target = f"{STAGING}/{dataset}", f"{TILES}/{dataset}"

    def work():
        if not read_back:
            lock.prove_hashing()
        published = remote.exists(target)  # read under the lock
        if published and not same_values:
            raise Refused(f"{dataset} is published already: a recut with other values is a new edition (a new "
                          "folder name); --same-values replaces it, a promise that the values are the same")
        staged = remote.listing(staging) or {}
        need = sum(size for path, (_, size) in files.items() if staged.get(path) != size) + len(card_bytes)
        free = remote.free()
        if free is None:
            raise Refused("the server does not tell its free space (rclone about)")
        if free < need + MARGIN_BYTES:
            raise Refused(f"<root> has {free / 1e9:.1f} GB free, {need / 1e9:.1f} GB to copy plus "
                          f"{MARGIN_BYTES / 1e9:.0f} GB to keep")
        tiles = sum(1 for p in files if not p.endswith("index.json"))
        print(f"  {tiles} tiles and {len(files) - tiles} indexes, {sum(s for _, s in files.values()) / 1e9:.2f} GB;"
              f" {need / 1e9:.2f} GB to copy", flush=True)
        # 2. the copy
        with tempfile.TemporaryDirectory(prefix="mirror-publish-") as tmp:
            names = os.path.join(tmp, "files.txt")
            with open(names, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(f"{path}\n" for path in sorted(files))
            done = rc.run("copy", "--files-from", names, folder, remote.path(staging), progress="copy")
        if done.returncode:
            said = remote.says(done)
            raise Failed(f"the copy into {staging} stopped ({_meaning(done.returncode)})"
                         + (f"; rclone: {said}" if said else "") + "; publish again: it resumes")
        remote.write(f"{staging}/{CARD}", card_bytes)
        # 3. the staged copy against the master
        sums = {path: digest for path, (digest, _) in files.items()}
        sums[CARD] = hashlib.sha256(card_bytes).hexdigest()
        found = remote.checksum(sums, staging, read_back)
        bad = [f"{p}: differs" for p in found["*"]] + [f"{p}: missing" for p in found["+"]] + \
              [f"{p}: not expected" for p in found["-"]] + [f"{p}: could not be hashed" for p in found["!"]]
        if bad:
            for fault in bad[:50]:
                print(f"  fault: {staging}/{fault}")
            lock.ensure("the staged copy's faults are deleted")
            for path in found["*"] + found["-"]:
                remote.delete(f"{staging}/{path}")
            raise Failed(f"the staged copy has {len(bad)} faults (the changed and unexpected files deleted from "
                         f"{staging}); publish again")
        print(f"  {staging}: {len(sums)} files verified on the server", flush=True)
        # 4. the moves: from here on every failure keeps the lock and names where the dataset is
        if published:
            lock.ensure(f"the move of {target} to {TRASH}/")
            lock.hold = (f"the dataset is complete in {target} or in {TRASH}/, the new copy in {staging} or "
                         f"{target}")
            _to_trash(remote, dataset)
        lock.ensure(f"the move of {staging} to {target}")
        lock.hold = f"the new copy is complete in {staging} or {target}"
        checked_move(remote, staging, target, set(sums))
        # 5. the list
        lock.ensure(f"{LIST} is written")
        lock.hold = f"the dataset is published in {target}; {LIST} is not rewritten yet"
        write_datasets(remote)

    locked(lock, work, f"{dataset} is published and {LIST} written")
    print(f"published {dataset}", flush=True)
    return 0


def unpublish(dataset: str, to: str, rc: Rclone, break_lock: bool = False) -> int:
    """A takedown (no row needed): only a folder that public/v1/tiles lists, moved to the trash, datasets.json
    rewritten."""
    check_dataset(dataset)
    remote = Remote(rc, parse_remote(to))
    lock = Lock(remote, f"unpublish {dataset}", break_lock)

    def work():
        if dataset not in remote.folders(TILES):
            raise Refused(f"{dataset} is not published (no folder {TILES}/{dataset}): nothing moved")
        lock.ensure(f"the move of {TILES}/{dataset} to {TRASH}/")
        lock.hold = f"the dataset is in {TILES}/{dataset} or {TRASH}/"
        _to_trash(remote, dataset)
        lock.ensure(f"{LIST} is written")
        lock.hold = f"the dataset is in {TRASH}/; {LIST} is not rewritten yet"
        write_datasets(remote)

    locked(lock, work, f"{dataset} is unpublished (in {TRASH}/) and {LIST} written")
    print(f"unpublished {dataset}", flush=True)
    return 0


def trash_age_days(name: str, now: datetime.datetime) -> Optional[float]:
    """The age in days of a trash folder <dataset>-<UTC stamp> (the stamp read from the right: a dataset's name may
    hold hyphens); None when the name has no stamp."""
    if "-" not in name:
        return None
    try:
        stamp = datetime.datetime.strptime(name.rsplit("-", 1)[1], STAMP).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    return (now - stamp).total_seconds() / 86400


def clean(to: str, rc: Rclone, keep_days: float = KEEP_DAYS, break_lock: bool = False) -> int:
    remote = Remote(rc, parse_remote(to))
    lock = Lock(remote, "clean", break_lock)
    counts = {"removed": 0, "kept": 0}

    def work():
        now = _now()
        for name in remote.folders(TRASH):
            age = trash_age_days(name, now)
            if age is None:
                print(f"  {TRASH}/{name}: no UTC stamp in its name, left")
                counts["kept"] += 1
            elif age >= keep_days:
                lock.ensure(f"{TRASH}/{name} is removed")
                done = rc.run("purge", remote.path(f"{TRASH}/{name}"))
                if done.returncode:
                    said = remote.says(done)
                    raise Failed(f"rclone could not remove {TRASH}/{name} ({_meaning(done.returncode)})"
                                 + (f"; rclone: {said}" if said else ""))
                print(f"  {TRASH}/{name}: removed ({age:.1f} days)")
                counts["removed"] += 1
            else:
                counts["kept"] += 1

    locked(lock, work, "the old trash is removed")
    print(f"clean: {counts['removed']} removed, {counts['kept']} kept")
    return 0


# stats

def _safe_fields(fields: Dict[str, str]) -> Dict[str, str]:
    """The log's free fields as stats may print them (a visitor sends them, and an address can be spelt many
    ways): a dataset only of PUBLISHABLE (or "-"), a limit's word of letters and underscores (or "-"), a client
    version by client_version; anything else "other"."""
    return {"ds": fields["ds"] if fields["ds"] == "-" or fields["ds"] in PUBLISHABLE else "other",
            "lim": fields["lim"] if fields["lim"] == "-" or LIMIT_WORD.fullmatch(fields["lim"]) else "other",
            "v": client_version(fields["v"])}


def stats(source: str, rc: Rclone) -> int:
    """Requests and bytes per day and dataset, refusals per day and limit, client versions, from the server's log
    files; no address, no raw line is printed (a line that is not a log record is counted, not shown)."""
    remote = Remote(rc, parse_remote(source))
    listing = remote.listing("")
    if listing is None:
        raise Refused("the log folder does not exist")
    days = sorted((m[1], p) for p in listing if (m := LOG_FILE.fullmatch(p)))
    if not days:
        print("no log files")
        return 0
    requests: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    refusals: Counter = Counter()
    versions: Counter = Counter()
    statuses: Counter = Counter()
    unreadable = 0
    for day, path in days:
        for line in remote.cat(path).splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                status, sent = int(record["s"]), int(record["b"])
                fields = {k: str(record.get(k, "")) for k in ("ds", "lim", "v")}
            except (ValueError, KeyError, TypeError, AttributeError):
                unreadable += 1
                continue
            fields = _safe_fields(fields)
            requests[day, fields["ds"]][0] += 1
            requests[day, fields["ds"]][1] += sent
            statuses[status // 100] += 1
            if fields["lim"] != "-":
                refusals[day, fields["lim"]] += 1
            versions[fields["v"]] += 1
    print("Requests per day and dataset (dataset '-': not a tile)")
    for (day, dataset), (n, sent) in sorted(requests.items()):
        print(f"  {day}  {dataset:<12} {n:>9} requests  {sent / 1e9:>10.3f} GB")
    print("Refused per day and limit")
    for (day, limit), n in sorted(refusals.items()):
        print(f"  {day}  {limit:<12} {n:>9}")
    if not refusals:
        print("  none")
    print("Status classes: " + ", ".join(f"{k}xx {n}" for k, n in sorted(statuses.items())))
    print("Client versions")
    for version, n in versions.most_common():
        print(f"  {version:<20} {n:>9}")
    if unreadable:
        print(f"{unreadable} lines that are not log records (not shown)")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="the rclone config file (rclone's own default when not given)")
    common.add_argument("--log", help="a file rclone's own messages are appended to (never printed)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", parents=[common], help="check a folder or a remote path against its indexes")
    p.add_argument("place", help="a folder, or remote:path")
    p.add_argument("--read-back", action="store_true", help="hash by reading the files back (no sha256 on the remote)")
    p = sub.add_parser("publish", parents=[common], help="copy a dataset to the server and swap it in")
    p.add_argument("dataset", help=f"the mirror's dataset folder ({', '.join(sorted(PUBLISHABLE))})")
    p.add_argument("--to", required=True, help="remote:root")
    p.add_argument("--mirror", help=f"the master mirror folder (default: the environment's {MIRROR_ENV})")
    p.add_argument("--same-values", action="store_true",
                   help="replace a published dataset: only for a re-encoding with the same values")
    p.add_argument("--break-lock", action="store_true", help="take the lock a stopped run left")
    p.add_argument("--read-back", action="store_true", help="hash by reading the files back (no sha256 on the remote)")
    p = sub.add_parser("unpublish", parents=[common], help="a dataset to trash, datasets.json rewritten")
    p.add_argument("dataset")
    p.add_argument("--to", required=True, help="remote:root")
    p.add_argument("--break-lock", action="store_true")
    p = sub.add_parser("clean", parents=[common], help="remove old trash")
    p.add_argument("--to", required=True, help="remote:root")
    p.add_argument("--keep-days", type=float, default=KEEP_DAYS, help=f"default {KEEP_DAYS}")
    p.add_argument("--break-lock", action="store_true")
    p = sub.add_parser("stats", parents=[common], help="summary of the server's request log")
    p.add_argument("--from", dest="source", required=True, help="remote:root/logs")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            rc = None if os.path.isdir(args.place) else make_rclone(args.config, args.log)
            return verify(args.place, rc, args.read_back)
        if args.command in ("publish", "unpublish"):
            check_dataset(args.dataset)  # before any request
        parse_remote(args.source if args.command == "stats" else args.to)
        rc = make_rclone(args.config, args.log)
        if args.command == "publish":
            return publish(args.dataset, args.to, rc, args.mirror, args.same_values, args.break_lock, args.read_back)
        if args.command == "unpublish":
            return unpublish(args.dataset, args.to, rc, args.break_lock)
        if args.command == "clean":
            return clean(args.to, rc, args.keep_days, args.break_lock)
        return stats(args.source, rc)
    except Refused as e:
        print(f"refused: {e}", flush=True)
        return 1
    except PartlyDone as e:
        print(f"done, but: {e}", flush=True)
        return 1
    except Failed as e:
        print(f"stopped: {e}", flush=True)
        return 1
    except KeyboardInterrupt:
        return 130  # the line saying what became of the lock is printed


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
