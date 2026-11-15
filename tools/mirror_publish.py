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
(rclone's own messages appended there; they are never printed: they may name the remote's host and user).

verify: for every index.json below the folder or remote path: every tile it lists with a sha256 is there with that
sha256, no tile file (<i>_<j>.tif) it does not list, the index not "partial". On a folder the tool hashes the files
itself (other files than tiles, a .part of a cut, are not looked at: they are never copied); on a remote the server
hashes them (rclone checksum sha256 against a SUM file made from the index), and every file of a product folder but
index.json must be a listed tile. --read-back hashes by reading the files back (rclone checksum --download) where the
remote has no sha256. Exit code 1 and the list of faults otherwise.

publish: refuses (before anything is written) a dataset without a complete, approved row in PUBLISHABLE, one whose
master fails verify, one lacking a folder of a resolution the catalogue declares for its source (GridTiles(averaged=)),
one already published unless --same-values (a re-encoding with the same values: a recut with other values is a new
edition, a new folder name), a server whose sha256 is not available (unless --read-back), a server locked by another
publish, and a <root> with less free space (rclone about) than the bytes not staged yet plus MARGIN_BYTES. Then:
1. takes the lock (staging/.lock: the PC and the time; --break-lock after a crash);
2. copies exactly the files the indexes list and the indexes into staging/<dataset>/ (rclone copy --files-from: a
   rerun skips what is there), and writes the dataset's card README.md there from CARDS;
3. verifies the staged copy on the server against the master's sha256 (every file, the card too; any other file is a
   fault). A changed or unlisted staged file is deleted, the lock released and the tool stops: run it again;
4. moves public/v1/tiles/<dataset> to trash/<dataset>-<UTC> when it exists, then staging/<dataset> to
   public/v1/tiles/<dataset> (rclone moveto: a rename on the server; a target that exists is never moved onto, since
   rclone would merge into it), and after each move checks that the source is gone and the target holds the files
   expected. A move that fails or checks wrong stops the tool with the lock kept and says where the dataset is
   complete;
5. writes public/v1/datasets.json from the server's copy of every published dataset (through
   public/v1/.datasets.json.new, a dot-file the server does not serve, and a rename), releases the lock.
unpublish: the dataset to trash, datasets.json rewritten (a takedown: no row needed). clean: removes the trash
folders whose UTC stamp is keep-days or more back. stats: requests and bytes per day and dataset, refusals per day
and limit, client versions, from the server's log files (access-YYYY-MM-DD.log, one JSON object per line: t, s, b,
rt, ds, a, lim, v); its output never holds an address.

Output: the tool's own lines and counts only, paths relative to the master ("<mirror>/...") or to <root>; never
rclone's raw output, the remote's name or the master's place. Exit code 0, 1 (refused or faults), 2 (usage).
"""

import argparse
import datetime
import hashlib
import json
import os
import re
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
HASH_THREADS = 8              # verify on a folder: files hashed at a time
STAMP = "%Y%m%dT%H%M%SZ"      # the UTC stamp of a trash folder's name

STAGING, TRASH, TILES = "staging", "trash", "public/v1/tiles"
LOCK = "staging/.lock"
LIST, LIST_TMP = "public/v1/datasets.json", "public/v1/.datasets.json.new"
CARD = "README.md"
TILE_FILE = re.compile(r"^(-?\d+)_(-?\d+)\.tif$")
LOG_FILE = re.compile(r"^access-(\d{4}-\d{2}-\d{2})\.log$")
# What the server's log may hold in its free fields (a visitor sends them); anything else counts as "other"
SAFE = {"ds": re.compile(r"^(-|[a-z0-9_-]{1,64})$"), "lim": re.compile(r"^[a-z0-9_-]{1,32}$"),
        "v": re.compile(r"^[0-9A-Za-z.+_-]{1,32}$")}
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
              "own sentence does not name distributing. \"non per download massivi\" (the download service's manual) "
              "is about that service, not about redistribution.",
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
            raise Refused(f"rclone could not be started ({type(e).__name__})") from None
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


def parse_place(text: str) -> str:
    """A --to / --from / verify argument: an rclone remote ("name:path", the name two characters or more) or a
    local folder (an absolute or relative path). A one-letter name is refused: rclone takes it for a drive letter
    on Windows."""
    if not text:
        raise Refused("no place given")
    if os.path.isabs(text) or re.match(r"^[A-Za-z]:[\\/]", text):
        return text
    found = re.match(r"^([^:/\\]+):", text)
    if found and len(found[1]) == 1:
        raise Refused("a remote's name of one letter is taken for a drive letter on Windows: rename the remote")
    return text


class Remote:
    """<root> on the server (or a folder), through rclone; every path given relative to it."""

    def __init__(self, rc: Rclone, root: str):
        self.rc, self.root = rc, root

    def path(self, rel: str = "") -> str:
        if not rel:
            return self.root
        return self.root + rel if self.root.endswith((":", "/", "\\")) else f"{self.root}/{rel}"

    def _failed(self, what: str, rel: str, done) -> Failed:
        return Failed(f"rclone could not {what} {rel or '<root>'} ({_meaning(done.returncode)})")

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
            raise Failed(f"rclone could not move {rel} to {to} ({_meaning(done.returncode)}); the server may have "
                         "refused the rename (another disk?)", keep_lock)

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

def _index_tiles(index: Dict) -> Dict[str, str]:
    """{path below the product folder: sha256} of an index's tiles with data."""
    block = int(index.get("block", 10))
    return {grid_tile_name(*map(int, key.split("_")), block): digest
            for key, digest in index["tiles"].items() if digest is not None}


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
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            faults.append(f"{label}/{prefix}index.json: cannot be read ({type(e).__name__})")
            continue
        if index.get("partial"):
            faults.append(f"{label}/{prefix}index.json: partial (still being cut)")
        files[prefix + "index.json"] = (_sha256(index_path), os.path.getsize(index_path))
        for sub, _, names in os.walk(here):
            for name in names:
                if TILE_FILE.match(name):
                    path = os.path.relpath(os.path.join(sub, name), here).replace("\\", "/")
                    if path not in tiles:
                        faults.append(f"{label}/{prefix}{path}: not listed in its index")
        for path, digest in tiles.items():
            jobs.append((prefix + path, digest))
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
    for index_rel in indexes:
        folder = index_rel[:-len("index.json")].rstrip("/")
        try:
            index = json.loads(remote.cat(index_rel))
            tiles = _index_tiles(index)
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
        remote = Remote(rc, parse_place(place))
        if not read_back and "sha256" not in remote.hashes():
            raise Refused("the remote reports no sha256 among its hashes (the remote's hashes and "
                          "sha256sum_command); --read-back reads the files back instead")
        print("verify: <remote>", flush=True)
        faults, checked = verify_remote(remote, read_back)
    for fault in faults:
        print(f"  fault: {fault}")
    print(f"{checked} tiles checked, {len(faults)} faults")
    return 1 if faults else 0


# publish

def _lock_text(command: str) -> bytes:
    return json.dumps({"pc": socket.gethostname(), "time": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "command": command}).encode("utf-8")


class Lock:
    """staging/.lock taken (refused while another holds it, unless broken) and released only by the run that took
    it."""

    def __init__(self, remote: Remote, command: str, force: bool):
        self.remote, self.command, self.force, self.taken = remote, command, force, False

    def check(self):
        if self.remote.exists(LOCK) and not self.force:
            try:
                held = json.loads(self.remote.cat(LOCK))
                who = f" by {held.get('pc')} since {held.get('time')} ({held.get('command')})"
            except (ValueError, Failed, AttributeError):
                who = ""
            raise Refused(f"the server is locked{who}: another publish runs, or one stopped; --break-lock after a "
                          "crash, once the server's state is understood")

    def take(self):
        self.check()
        self.remote.write(LOCK, _lock_text(self.command))
        self.taken = True

    def release(self):
        if self.taken:
            self.remote.delete(LOCK)
            self.taken = False


def _stamp() -> str:
    return _now().strftime(STAMP)


def _to_trash(remote: Remote, dataset: str):
    """public/v1/tiles/<dataset> moved to trash/<dataset>-<UTC>, checked."""
    source, trash = f"{TILES}/{dataset}", f"{TRASH}/{dataset}-{_stamp()}"
    before = remote.listing(source) or {}
    remote.move(source, trash)
    after = remote.listing(trash) or {}
    if remote.exists(source) or len(after) != len(before):
        raise Failed(f"after the move {source} still exists or {trash} holds {len(after)} of {len(before)} files: "
                     f"the dataset's complete copy is {'in ' + trash if len(after) == len(before) else 'unclear'}",
                     keep_lock=True)
    print(f"  {source} moved to {trash} ({len(after)} files)", flush=True)


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
                     if p.startswith(folder + "/") and TILE_FILE.match(p.rsplit("/", 1)[-1])}
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
        raise Failed(f"rclone could not rename {LIST_TMP} to {LIST} ({_meaning(done.returncode)})", keep_lock=True)
    print(f"  {LIST}: {len(entries)} datasets", flush=True)
    return content


def publish(dataset: str, to: str, rc: Rclone, mirror: Optional[str], same_values: bool = False,
            break_lock: bool = False, read_back: bool = False) -> int:
    row = PUBLISHABLE.get(dataset)
    if row is None:
        raise Refused(f"{dataset}: no row in PUBLISHABLE (only {', '.join(sorted(PUBLISHABLE))} may be published)")
    faults = row_faults(row)
    if faults:
        raise Refused(f"{dataset}: its PUBLISHABLE row is not complete: {'; '.join(faults)}")
    card = cards().get(dataset)
    if not card:
        raise Refused(f"{dataset}: no card text")
    mirror = mirror or os.environ.get(MIRROR_ENV)
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
    remote = Remote(rc, parse_place(to))
    if not read_back and "sha256" not in remote.hashes():
        raise Refused("the remote reports no sha256 among its hashes (set its hashes and sha256sum_command); "
                      "--read-back reads the files back instead")
    lock = Lock(remote, f"publish {dataset}", break_lock)
    lock.check()
    published = remote.exists(f"{TILES}/{dataset}")
    if published and not same_values:
        raise Refused(f"{dataset} is published already: a recut with other values is a new edition (a new folder "
                      "name); --same-values replaces it, a promise that the values are the same")
    card_bytes = card.encode("utf-8")
    staging = f"{STAGING}/{dataset}"
    staged = remote.listing(staging) or {}
    need = sum(size for path, (_, size) in files.items() if staged.get(path) != size) + len(card_bytes)
    free = remote.free()
    if free is None:
        raise Refused("the server does not tell its free space (rclone about)")
    if free < need + MARGIN_BYTES:
        raise Refused(f"<root> has {free / 1e9:.1f} GB free, {need / 1e9:.1f} GB to copy plus "
                      f"{MARGIN_BYTES / 1e9:.0f} GB to keep")
    tiles = sum(1 for p in files if not p.endswith("index.json"))
    print(f"  {tiles} tiles and {len(files) - tiles} indexes, {sum(s for _, s in files.values()) / 1e9:.2f} GB; "
          f"{need / 1e9:.2f} GB to copy", flush=True)
    lock.take()
    try:
        # 2. the copy
        with tempfile.TemporaryDirectory(prefix="mirror-publish-") as tmp:
            names = os.path.join(tmp, "files.txt")
            with open(names, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(f"{path}\n" for path in sorted(files))
            done = rc.run("copy", "--files-from", names, folder, remote.path(staging), progress="copy")
        if done.returncode:
            raise Failed(f"the copy into {staging} stopped ({_meaning(done.returncode)}); publish again: it resumes")
        remote.write(f"{staging}/{CARD}", card_bytes)
        # 3. the staged copy against the master
        sums = {path: digest for path, (digest, _) in files.items()}
        sums[CARD] = hashlib.sha256(card_bytes).hexdigest()
        found = remote.checksum(sums, staging, read_back)
        wrong = found["*"] + found["-"]
        bad = [f"{p}: differs" for p in found["*"]] + [f"{p}: missing" for p in found["+"]] + \
              [f"{p}: not expected" for p in found["-"]] + [f"{p}: could not be hashed" for p in found["!"]]
        if bad:
            for fault in bad[:50]:
                print(f"  fault: {staging}/{fault}")
            for path in wrong:
                remote.delete(f"{staging}/{path}")
            raise Failed(f"the staged copy has {len(bad)} faults (the changed and unexpected files deleted from "
                         f"{staging}); publish again")
        print(f"  {staging}: {len(sums)} files verified on the server", flush=True)
        # 4. the moves
        target = f"{TILES}/{dataset}"
        if published:
            _to_trash(remote, dataset)
        remote.move(staging, target)
        after = remote.listing(target) or {}
        if remote.exists(staging) or set(after) != set(sums):
            raise Failed(f"after the move {staging} still exists or {target} holds {len(after)} of {len(sums)} "
                         f"files: the complete copy is {'in ' + target if set(after) == set(sums) else 'unclear'}",
                         keep_lock=True)
        print(f"  {staging} moved to {target}", flush=True)
        # 5. the list
        write_datasets(remote)
    except Failed as e:
        if not e.keep_lock:
            lock.release()
        else:
            e.args = (e.args[0] + f" (the lock {LOCK} is kept: look at the server, then --break-lock)",)
        raise
    except Refused:  # rclone could not be started any more: nothing public was touched by this run's last step
        lock.release()
        raise
    lock.release()
    print(f"published {dataset}", flush=True)
    return 0


def unpublish(dataset: str, to: str, rc: Rclone, break_lock: bool = False) -> int:
    remote = Remote(rc, parse_place(to))
    lock = Lock(remote, f"unpublish {dataset}", break_lock)
    lock.take()
    try:
        if remote.exists(f"{TILES}/{dataset}"):
            _to_trash(remote, dataset)
        else:
            print(f"  {TILES}/{dataset} is not published", flush=True)
        write_datasets(remote)
    except Failed as e:
        if not e.keep_lock:
            lock.release()
        raise
    lock.release()
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
    remote = Remote(rc, parse_place(to))
    lock = Lock(remote, "clean", break_lock)
    lock.take()
    removed = kept = 0
    try:
        now = _now()
        for name in remote.folders(TRASH):
            age = trash_age_days(name, now)
            if age is None:
                print(f"  {TRASH}/{name}: no UTC stamp in its name, left")
                kept += 1
            elif age >= keep_days:
                done = rc.run("purge", remote.path(f"{TRASH}/{name}"))
                if done.returncode:
                    raise Failed(f"rclone could not remove {TRASH}/{name} ({_meaning(done.returncode)})")
                print(f"  {TRASH}/{name}: removed ({age:.1f} days)")
                removed += 1
            else:
                kept += 1
    except Failed:
        lock.release()
        raise
    lock.release()
    print(f"clean: {removed} removed, {kept} kept")
    return 0


# stats

def stats(source: str, rc: Rclone) -> int:
    """Requests and bytes per day and dataset, refusals per day and limit, client versions, from the server's log
    files; no address, no raw line is printed (a line that is not a log record is counted, not shown)."""
    remote = Remote(rc, parse_place(source))
    listing = remote.listing("")
    if listing is None:
        raise Refused("the log folder does not exist")
    days = sorted((m[1], p) for p in listing if (m := LOG_FILE.match(p)))
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
                fields = {k: str(record.get(k, "")) for k in SAFE}
            except (ValueError, KeyError, TypeError, AttributeError):
                unreadable += 1
                continue
            fields = {k: v if SAFE[k].match(v) else "other" for k, v in fields.items()}
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
    except Failed as e:
        print(f"stopped: {e}", flush=True)
        return 1


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
