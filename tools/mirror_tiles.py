"""
Own copies of elevation models that cannot be read in parts from their provider, cut into 2 km tiles for the mirror
(run by hand, not by the app; on this PC or in a container of the project's image on another machine).

A dataset (`DATASETS`) is a folder of the mirror with one or more products, each at its own native resolution:
<mirror>/<dataset>/<product>/<res>m/<block>/<i>_<j>.tif (names in [a-z0-9_-]+, <res> as 0.5, 2, 5), and one dataset
card (README.md) generated from the dataset's record for every product it has (the provider, licence, attribution and
the changes made per product), written whole each time. A product has a list of inputs, each one of:
  Url(url, bytes)        a file the tool downloads into --work, one at a time (never two downloads at once: a lock in
                         --work), its declared size checked, resumed by a Range where the server allows it
                         (`resume_below`; a server answering 200 to a Range sends the whole file, written from zero),
                         at most ATTEMPTS tries; for small single files (Madeira's 5 m ZIP of 114 MB)
  Placed(pattern)        a file placed by hand (or by another tool) in --inputs, any name matching the pattern, its
                         size not known in advance; a .part, .crdownload or .tmp is never an input
  Folder(path, pattern)  a folder of many rasters in --inputs (Portugal's tens of thousands of 1 km GeoTIFFs), each file
                         checked against the sha256 of `done.jsonl` beside them; while a done.jsonl is there, a file it
                         does not name yet (being recorded or replaced) is no input in this run; complete once it holds
                         `expected` rasters (without `expected` the folder is never complete)
Patterns match letters in either case on every system (".tif" finds ".TIF"). A Url or a Placed file that is a ZIP
names its raster members (fnmatch patterns: Madeira's 5 m ZIP holds a raster per island); they are unpacked into
--work (zipfile for stored and Deflate, CRC checked; 7-Zip for Deflate64, found by FINDALINE_7ZIP or on PATH: the
project's image has none). An ESRI ASCII grid (Valle d'Aosta's, decimal commas) is read forwards only: it is copied into
a tiled GeoTIFF in --work first. So is a raster of full-width strips too wide for the memory bound (one row of 2 km
tiles across it would not fit in GDAL's cache). Every file the tool makes in --work is recorded with its source's stamp
(a member's CRC and size, a file's size and modification time: <work>/state/work-files.sqlite): a copy is used only
while its source is unchanged, and `clean` removes only these files, never an input.

The cut: every tile (i, j) of the product's extent (the rectangle of its rasters, on the tile grid through the
product's `origin`: tile (i, j) covers [origin_x + 2000 i, origin_x + 2000 (i + 1)) x [origin_y + 2000 j, ...)) is
assembled from the pixels of every raster that covers it, in the order of the inputs (a folder's files by name), where
two overlap by the product's rule: "first" (the first listed wins) or "agree" (they must agree within the 5 mm bound,
else an error naming the tile). Masks per product: the files' own nodata, the `nodata` values, the `sea` value (made no
data), an optional `floor` (every value below it) and NaN. The CRS is the product's, never the file's (a file's own
label, when another, is recorded in the index as `input_crs`). Tiles are written in tools/sk_tiles.py's encoding (COG
LERC_ZSTD within 5 mm, `sk_tiles._write`), row by row from the top, the index saved after each row (`tiles` with each
tile's sha256, null: no data). A partial product has no index.json: nothing reads or publishes it. While an input of a
product of many inputs is missing, its expected count not met or a tile left, its index is index.partial.json
(`partial`: true); index.json appears once the product is complete (the datasets of before, Madeira 2 m and Valle
d'Aosta, keep their index.json with "partial" while cut). The work's state (<work>/state/<dataset>.<product>.sqlite)
records which rasters fed each tile and their stamps. A listed tile is cut again only when every raster that fed it is
present and unchanged and a present raster covers it that did not; when a raster that fed it is missing then, or one
has changed at all, the cut stops (Stale) naming the tile and the rasters, before anything is written: fetch them
again, or cut the product into a fresh mirror folder. A listed tile without any record (cut without this work
folder's state) is final, never cut again. So fetched files may be deleted by hand once a product is cut. A tile no
present raster covers is left out of the index (not null) until every input is complete. Restartable at any point.

Memory: the cut works tile by tile, `--threads` writers and a GDAL cache within `--max-memory-gb`. The bound is an
estimate (GDAL's cache, TILE_BYTES_PER_PX for each tile in flight and the one being assembled, BASE_MB for the
process; GDAL's own buffers and the open files are not counted): the cut refuses a bound below one tile, and in a
container the container's memory limit is the guard.

    python tools/mirror_tiles.py download porto-santo --work W          # the declared files (resumed where allowed)
    python tools/mirror_tiles.py extract porto-santo --work W           # ZIP members, ASCII grids, wide strips
    python tools/mirror_tiles.py cut porto-santo --work W --out M       # tiles + index + card (resumable)
    python tools/mirror_tiles.py verify porto-santo --work W --out M    # tiles against the inputs, sha256, stray files
    python tools/mirror_tiles.py status [dataset] --work W --out M      # what is there and what is left
    python tools/mirror_tiles.py all porto-santo --inputs I --work W --out M   # download, extract, cut, verify, clean

--out is the mirror (default: the environment's FINDALINE_MIRROR); --inputs the folder of placed files and folders of
rasters (--work by default); --product one product only. One run at a time per --work and per product's mirror folder
(locks in --work and in <out>/.locks): a second run stops at once with Busy and a non-zero exit, touching nothing.
`all` skips a product that is complete and verified on its present index.json, and removes the product's unpacked and
copied rasters from --work once its verify passed. verify checks every listed tile's sha256, finds every file in the
product's folder the index does not list, and compares sampled tiles (`--samples`, by default 1 % of the tiles with
data, at least 8, at most 500; `--seed`, recorded) with the inputs, twice: re-assembled as the cut does, and POINTS
pixels each read straight from the input rasters through their own transforms with the masks applied apart. A tile
whose feeding rasters are gone or changed is counted as not checkable, never as a failure; a verify that finds
nothing checkable keeps an earlier passing verify.json of the same index.json. It writes verify.json beside the index.

In a container of the project's image (Linux). The image holds no tools/ (.dockerignore), so the clone's is mounted
too; the container runs as uid 10001 unless --user says otherwise, the mounted folders must be writable by that user,
and every run on one work folder must take the same user: the state another user wrote is read-only to the next:

    docker build -t findaline .
    docker run --rm --user "$(id -u):$(id -g)" --entrypoint python \\
        -v "$PWD/tools:/opt/findaline/tools:ro" -v "$PWD/downloads:/inputs:ro" \\
        -v "$PWD/work:/work" -v "$PWD/mirror:/mirror" \\
        findaline tools/mirror_tiles.py all porto-santo --inputs /inputs --work /work --out /mirror
    # one mount of a folder holding downloads/, work/ and mirror/ (and tools/ mounted as above) does the same:
    #   -v "$PWD:/srv" ... --inputs /srv/downloads --work /srv/work --out /srv/mirror

It makes no request but the declared downloads (cut, verify and status run with `--network none`).
"""

import argparse
import contextlib
import datetime
import fnmatch
import glob
import hashlib
import json
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import warnings
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import rasterio as rio
import requests
from rasterio.transform import from_origin
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cache  # noqa: E402
import servicecounts  # noqa: E402
from sources import net  # noqa: E402
from sources.readers.tilebases import MIRROR_ENV  # noqa: E402
import sk_tiles  # noqa: E402
from sk_tiles import TILE_M, BLOCK, MAX_Z_ERROR, tile_name, _sha256  # noqa: E402

ATTEMPTS = 3      # download attempts (the first and two more)
# Replacing a file on a network share (the mirror on Z:) is refused now and then for a moment (WinError 5 while
# the share or a scanner holds the old file): tried again for this long
REPLACE_SECONDS = 60
CHUNK = 8 << 20   # bytes per write of a download
# 7-Zip unpacks Deflate64 (ZIP method 9); zipfile only stored and Deflate (0, 8)
SEVEN_ZIP = os.environ.get("FINDALINE_7ZIP") or shutil.which("7z") or shutil.which("7za") or shutil.which("7zz") or \
    (r"C:\Program Files\7-Zip\7z.exe" if os.name == "nt" else "7z")
THREADS = 6            # tile writers (a small home server's cores)
MAX_MEMORY_GB = 8.0    # the cut's estimated bound, GDAL's cache included (see the module's docstring)
BASE_MB = 300          # Python, GDAL and the libraries before any tile
TILE_BYTES_PER_PX = 24  # a tile in flight: its float32 buffer, a float64 read window at worst, the masks, LERC's copy
POINTS = 300           # verify: pixels of each sampled tile also read straight from the inputs
VERIFY_EPS = MAX_Z_ERROR + 1e-4  # LERC's bound and float32 rounding at heights of a few thousand metres
NAME = re.compile(r"^[a-z0-9_-]+$")
NOT_INPUTS = (".part", ".crdownload", ".tmp", ".new")

MADEIRA_CARD = """# Madeira: DTM 2 m (DROTe, 2018-2019) as 2 km tiles

Tiles of the digital terrain model **MDT 2 m** of Madeira island by the **Direção Regional do Ordenamento do
Território (DROTe), Região Autónoma da Madeira**, photogrammetric (UltraCam flights 2018-2019, RMSEz 0.145 m),
from https://irig-storage.madeira.gov.pt/irig-catalogo/MDT_2m.zip (SNIG record abba9a83: "No conditions apply").
It covers Madeira island only (not Porto Santo, the Desertas or the Selvagens).

Changes made: the BigTIFF (PTRA08 / UTM zone 28N, EPSG:5016) was cut into 2 km x 2 km Cloud Optimized GeoTIFFs on
its own pixel grid (edges on odd metres: tile (i, j) starts at x = 2000 i + 1, y = 2000 j + 1), its two no-data
values (-32768, -999) made no data, stored with LERC compression with a maximum error of 5 mm. Values are not
otherwise changed.

Layout: `dtm/2m/<i//10>_<j//10>/<i>_<j>.tif`; `dtm/2m/index.json` lists every tile of the extent with its sha256
(null: no data). Made for Find-a-Line (a highline finder); not endorsed by DROTe.
"""

AOSTA_CARD = """# Valle d'Aosta: DTM 2005/2008 2 m as 2 km tiles

Dati estratti dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta.
Licence: CC BY 4.0 (http://metadati.partout.it/metadata_documents/CC_BY_DTM_v2.pdf). Source: the region's
DTM0508_002_UNICO (https://geoprodotti.regione.vda.it/download/DTM0508_002/DTM0508_002_UNICO.zip), lidar 2005 and
2008, 2 m, ED50 / UTM zone 32N (EPSG:23032), heights "quota ortometrica (geoidica)".

Changes made: the ESRI ASCII grid (decimal commas) was cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own
pixel grid (x edges on even, y edges on odd metres: tile (i, j) starts at x = 2000 i, y = 2000 j + 1), its no-data
value (-9999) made no data, stored with LERC compression with a maximum error of 5 mm. Values are not otherwise
changed. The DSM follows later.

Layout: `dtm/2m/<i//10>_<j//10>/<i>_<j>.tif`; `dtm/2m/index.json` lists every tile of the extent with its sha256
(null: no data). Made for Find-a-Line (a highline finder); not endorsed by the Regione Autonoma Valle d'Aosta.
"""


# The records

@dataclass(frozen=True)
class Url:
    """A file the tool downloads into --work (its size known); members: the ZIP's raster members (fnmatch patterns,
    () when the file is the raster); resume_below: a broken download resumes by a Range only below this byte (None:
    always)."""
    url: str
    bytes: int
    members: Tuple[str, ...] = ()
    resume_below: Optional[int] = None


@dataclass(frozen=True)
class Placed:
    """A file placed in --inputs by hand or by another tool: the one file matching pattern (a glob relative to
    --inputs); members as Url's."""
    pattern: str
    members: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Folder:
    """A folder of rasters in --inputs (path relative to it), the files matching pattern below it, in name order;
    done: a JSON-lines file of sha256 relative to the folder (each file read is checked against it when it lists the
    file); expected: the number of rasters of the complete folder (None: never complete, the index stays partial)."""
    path: str
    pattern: str = "**/*.tif"
    expected: Optional[int] = None
    done: Optional[str] = "done.jsonl"


Input = Union[Url, Placed, Folder]


@dataclass(frozen=True)
class Product:
    """One product of a dataset at its native resolution: its folder <product>/<res>m, its CRS (given by the dataset,
    never taken from the files), the tile grid's origin (the pixels' edges modulo 2 km), its inputs in the order of
    the overlap rule, the masks and the texts of the card and the index."""
    name: str
    res: float
    crs: str
    origin: Tuple[float, float]
    inputs: Tuple[Input, ...]
    title: str
    heights: str
    nodata: Tuple[float, ...] = ()   # values made no data besides each file's own
    sea: Optional[float] = None      # the value the provider wrote over the sea, made no data
    floor: Optional[float] = None    # every value below it made no data (a guessed threshold: measured first)
    overlap: str = "first"           # "first": the first listed wins; "agree": within MAX_Z_ERROR, else an error
    about: str = ""                  # the card's sentence on what the product is and where it comes from


@dataclass(frozen=True)
class Dataset:
    """A folder of the mirror: its record (title, provider, licence, attribution) and products; card: the published
    text of a dataset made before cards were generated (Madeira's, Valle d'Aosta's), used while it has the one
    product it describes."""
    name: str
    title: str
    provider: str
    licence: str
    attribution: str
    products: Tuple[Product, ...]
    record: str = ""      # the provider's page or record of the data
    not_endorsed: str = ""  # who has not endorsed the copy (the provider's short name)
    card: Optional[str] = None
    legacy: bool = False  # an index of before (no keys beyond those of 2026-11-15)
    key: str = ""         # a dataset of before: its name in DATASETS (the index's "dataset")


PORTO_SANTO_ZIP = Url("https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip", 114_126_877)
MADEIRA_5M_RECORD = ("https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/"
                     "abba9a83-cb1c-4d2c-ad1d-ccb592247754")
DROTE = "Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da Madeira"


def _island(name: str, island: str, member: str, crs: str, crs_name: str, nodata: Tuple[float, ...],
            sea: Optional[float], about: str, floor: Optional[float] = None) -> Dataset:
    """One island of Madeira's 5 m ZIP as a dataset of its own (the SNIG record abba9a83)."""
    product = Product("dtm", 5.0, crs, (2.5, 2.5), (replace(PORTO_SANTO_ZIP, members=(member,)),),
                      f"MDT 5 m, {island} (DROTe, photogrammetry 2018-2019)", "as published (metres)",
                      nodata=nodata, sea=sea, floor=floor,
                      about=f"{member} of {PORTO_SANTO_ZIP.url} ({crs_name}); {about}")
    return Dataset(name, f"{island}: DTM 5 m (DROTe, 2018-2019)", DROTE, "No conditions apply (SNIG record abba9a83)",
                   f"DTM 5 m: {DROTE}, 2018-2019", (product,), record=MADEIRA_5M_RECORD, not_endorsed="DROTe")


# Two shapes: a dict of before (one URL, one ZIP member, one product) or a Dataset. The CRS of every product is the
# dataset's (the tiles carry its EPSG code); `origin` the pixel edges modulo TILE_M; nodata the values that mean no
# data
DATASETS: Dict[str, Union[Dict, Dataset]] = {
    "madeira": dict(
        url="https://irig-storage.madeira.gov.pt/irig-catalogo/MDT_2m.zip", bytes=460_132_910,
        member="MDT_2m.tif", folder="madeira", product="dtm", crs="EPSG:5016", res=2.0, origin=(1.0, 1.0),
        nodata=(-32768.0, -999.0), resume_below=None,
        title="MDT 2 m, Madeira island (DROTe, photogrammetry 2018-2019)",
        heights="as published (metres, millimetre values)", licence="No conditions apply (SNIG abba9a83)",
        attribution="Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da Madeira",
        card=MADEIRA_CARD),
    "aosta": dict(
        url="https://geoprodotti.regione.vda.it/download/DTM0508_002/DTM0508_002_UNICO.zip", bytes=2_604_729_175,
        member="DTM0508_002_UNICO.ASC", folder="aosta", product="dtm", crs="EPSG:23032", res=2.0, origin=(0.0, 1.0),
        nodata=(-9999.0,), resume_below=100_000_000,
        title="DTM 2005/2008 2 m, Valle d'Aosta (Regione Autonoma Valle d'Aosta)",
        heights="quota ortometrica (geoidica)", licence="CC-BY-4.0",
        attribution="Dati estratti dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta.",
        card=AOSTA_CARD),
    # Madeira's 5 m ZIP: a raster per island (members of 2026-05-18). Porto Santo in Porto Santo 1995 / UTM 28N, its
    # sea written as 0 (its nodata tag); the Desertas labelled EPSG:3061 but in PTRA08 (their coast read as EPSG:5016
    # lies 6 m from OSM's and 10 m from the 2023 orthophoto's in the median, read as EPSG:3061 157 and 163 m:
    # 2026-11-15), the Selvagens in PTRA08; both with -32768 outside, -999 at the coast and about 1 700 and 300 coast
    # pixels averaged with -999 (-443 to -499 m): every value below -1 m is no data there (the user's decision of
    # 2026-11-15, the rule of IGN's overseas models); Porto Santo's lowest land is -0.84 m, no floor
    "porto-santo": _island("porto-santo", "Porto Santo", "PortoSanto_5m.tif", "EPSG:3061",
                           "Porto Santo 1995 / UTM zone 28N, EPSG:3061", (), 0.0,
                           "Porto Santo and its islets; the sea written as 0 there"),
    "desertas": _island("desertas", "Desertas", "Desertas_5m.tif", "EPSG:5016",
                        "PTRA08 / UTM zone 28N, EPSG:5016; the file is labelled EPSG:3061", (-32768.0, -999.0), None,
                        "Deserta Grande, Bugio and Ilhéu Chão", floor=-1.0),
    "selvagens": _island("selvagens", "Selvagens", "Selvagens_5m.tif", "EPSG:5016",
                         "PTRA08 / UTM zone 28N, EPSG:5016", (-32768.0, -999.0), None,
                         "Selvagem Grande, Selvagem Pequena and Ilhéu de Fora", floor=-1.0),
}


def dataset(name: str) -> Dataset:
    """The dataset of a name of DATASETS, a dict of before made a Dataset (its one product from its one URL)."""
    spec = DATASETS[name]
    if isinstance(spec, Dataset):
        return spec
    product = Product(spec["product"], float(spec["res"]), spec["crs"], tuple(spec["origin"]),
                      (Url(spec["url"], spec["bytes"], (spec["member"],), spec.get("resume_below")),),
                      spec["title"], spec["heights"], nodata=tuple(spec["nodata"]))
    return Dataset(spec["folder"], spec["title"], spec["attribution"], spec["licence"], spec["attribution"],
                   (product,), card=spec.get("card"), legacy=True, key=name)


def tile_folder(spec: Union[Dict, Dataset], product: Optional[Product] = None) -> str:
    """A product's folder below the mirror: <dataset>/<product>/<res>m (a dict of before: its one product)."""
    if isinstance(spec, dict):
        return f"{spec['folder']}/{spec['product']}/{spec['res']:g}m"
    product = product or spec.products[0]
    return f"{spec.name}/{product.name}/{product.res:g}m"


def check_names(ds: Dataset):
    """The folder names the hosted mirror serves: [a-z0-9_-]+ for the dataset and its products."""
    for name in [ds.name] + [p.name for p in ds.products]:
        if not NAME.match(name):
            raise ValueError(f"{name!r}: a dataset or product name must match {NAME.pattern}")
    if len({p.name for p in ds.products}) != len(ds.products):
        raise ValueError(f"{ds.name}: two products of one name")


class SizeChanged(RuntimeError):
    """The server's file is not of the dataset's size: never read beyond it."""


# Download

def zip_path(spec: Union[Dict, Url], work: str) -> str:
    return os.path.join(work, os.path.basename(spec["url"] if isinstance(spec, dict) else spec.url))


def _urls(ds: Dataset) -> List[Url]:
    found = []
    for product in ds.products:
        found += [i for i in product.inputs if isinstance(i, Url) and i not in found]
    return found


def download(name: str, work: str) -> List[str]:
    """Every Url input of the dataset in work, one after another (see the module's docstring); their paths."""
    return [download_url(url, work) for url in _urls(dataset(name))]


@contextlib.contextmanager
def _one_download(work: str):
    """Never two downloads at once, also from two processes on one work folder."""
    from filelock import FileLock
    os.makedirs(work, exist_ok=True)
    with FileLock(os.path.join(work, "download.lock")):
        yield


def download_url(spec: Url, work: str) -> str:
    """One declared file in work; its path."""
    url, total = spec.url, spec.bytes
    os.makedirs(work, exist_ok=True)
    path = zip_path(spec, work)
    part = path + ".part"
    if os.path.exists(path) and os.path.getsize(path) == total:
        print(f"{path}: complete ({total / 1e9:.2f} GB)")
        return path
    resume_below = spec.resume_below
    error = None
    with _one_download(work):
        for attempt in range(ATTEMPTS):
            done = os.path.getsize(part) if os.path.exists(part) else 0
            if done >= total or (done and resume_below is not None and done >= resume_below):
                print(f"  {done} bytes of before: the download starts again (no Range from there)", flush=True)
                _remove(part, work)
                done = 0
            try:
                done = _fetch(url, part, done, total)
                if done == total:
                    os.replace(part, path)
                    print(f"{path}: {total / 1e9:.2f} GB", flush=True)
                    return path
                error = f"cut short at {done} of {total} bytes"
            except SizeChanged:
                if os.path.exists(part):
                    _remove(part, work)
                raise
            except (requests.RequestException, RuntimeError, OSError) as e:
                error = cache.clean_error(e)
            print(f"  attempt {attempt + 1} of {ATTEMPTS}: {error}", flush=True)
            if attempt + 1 < ATTEMPTS:
                net._sleep(attempt)
    raise RuntimeError(f"Could not download {url} after {ATTEMPTS} attempts: {error}")


def _fetch(url: str, part: str, done: int, total: int) -> int:
    """One GET of url into part from byte done (a Range only when done > 0); the bytes in part after it."""
    headers = dict(cache.http_headers())
    if done:
        headers["Range"] = f"bytes={done}-"
    start, last, first = time.time(), time.time(), done
    net.rate_turn(url)
    with servicecounts.request(url) as counted, \
            net.session().get(url, headers=headers, stream=True, timeout=120, verify=net.verify(url)) as response:
        counted.got(response, read=False)
        if done and response.status_code == 206:
            expected = f"bytes {done}-{total - 1}/{total}"
            if response.headers.get("Content-Range", "").strip() != expected:
                raise SizeChanged(f"{url}: Content-Range {response.headers.get('Content-Range')!r}, "
                                  f"{expected!r} expected")
            mode = "ab"
        elif response.status_code == 200:
            if done:
                print("  the server ignored the Range: the whole file again", flush=True)
            done = first = 0
            mode = "wb"
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != total:
                raise SizeChanged(f"{url}: {length} bytes, {total} expected (the dataset has changed)")
        else:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300] if not done else ''}")
        with open(part, mode) as f:
            for chunk in response.iter_content(CHUNK):
                if done + len(chunk) > total:
                    raise SizeChanged(f"{url}: more than {total} bytes (the dataset has changed)")
                f.write(chunk)
                done += len(chunk)
                counted.add(len(chunk))
                if time.time() - last > 30:
                    last = time.time()
                    rate = (done - first) / max(time.time() - start, 1e-9) / 1e6
                    print(f"  {done / 1e9:.2f} of {total / 1e9:.2f} GB, {rate:.1f} MB/s", flush=True)
    return done


# Locks and removals

class Busy(RuntimeError):
    """Another run of this tool holds the work folder or the product's mirror folder."""


_HELD: Dict[str, int] = {}  # the locks this process holds (a step inside `all` takes them again)
_HELD_LOCK = threading.Lock()


@contextlib.contextmanager
def _locked(path: str, what: str):
    """One run at a time on what path guards: a second process gets Busy at once, touching nothing."""
    from filelock import FileLock, Timeout
    key = os.path.normcase(os.path.abspath(path))
    with _HELD_LOCK:
        if _HELD.get(key):
            _HELD[key] += 1
            held = None
        else:
            os.makedirs(os.path.dirname(key), exist_ok=True)
            held = FileLock(key)
            try:
                held.acquire(timeout=0)
            except Timeout:
                raise Busy(f"{what} is in use by another run of tools/mirror_tiles.py ({path}): wait for it to end")
            _HELD[key] = 1
    try:
        yield
    finally:
        with _HELD_LOCK:
            _HELD[key] -= 1
            if not _HELD[key]:
                del _HELD[key]
                held.release()


def _work_lock(work: str):
    return _locked(os.path.join(work, "mirror_tiles.lock"), f"the work folder {work}")


def _product_lock(out: str, ds: "Dataset", product: "Product"):
    """The product's mirror folder, by a lock file in <out>/.locks (never inside a dataset's folder)."""
    return _locked(os.path.join(out, ".locks", f"{ds.name}.{product.name}.{product.res:g}m.lock"),
                   f"the mirror folder {tile_folder(ds, product)}")


def _remove(path: str, *roots: str):
    """os.remove of a file the tool made: refused (ValueError) unless it lies below one of roots (--work, a
    product's mirror folder). An input is never removed."""
    real = os.path.normcase(os.path.realpath(path))
    for root in roots:
        top = os.path.normcase(os.path.realpath(root))
        if real != top and os.path.commonpath([real, top]) == top:
            os.remove(path)
            return
    raise ValueError(f"{path}: not below {', '.join(roots)}: the tool removes only files it made there")


# Inputs: what each declared input stands for on disk

def _is_input_name(path: str) -> bool:
    return not path.lower().endswith(NOT_INPUTS)


def _any_case(pattern: str) -> str:
    """A glob pattern matching its letters in either case outside [...] (".tif" also finds ".TIF" on Linux, as on
    Windows)."""
    out, inside = [], False
    for ch in pattern:
        if ch == "[":
            inside = True
        elif ch == "]":
            inside = False
        out.append(f"[{ch.lower()}{ch.upper()}]" if ch.isalpha() and not inside and ch.lower() != ch.upper() else ch)
    return "".join(out)


def placed_path(spec: Placed, inputs: Optional[str]) -> Optional[str]:
    """The file placed for spec in inputs (None while there is none); ValueError for two candidates."""
    if inputs is None:
        raise ValueError(f"{spec.pattern}: a placed input needs --inputs")
    found = sorted(p for p in glob.glob(os.path.join(inputs, _any_case(spec.pattern)), recursive=True)
                   if os.path.isfile(p) and _is_input_name(p))
    if len(found) > 1:
        raise ValueError(f"{spec.pattern}: {len(found)} files match in {inputs}, one expected: {found[:5]}")
    return found[0] if found else None


def folder_files(spec: Folder, inputs: Optional[str]) -> List[str]:
    """The rasters of a folder input, in name order (relative paths below --inputs)."""
    if inputs is None:
        raise ValueError(f"{spec.path}: a folder input needs --inputs")
    root = os.path.join(inputs, spec.path)
    found = [p for p in glob.glob(os.path.join(root, _any_case(spec.pattern)), recursive=True)
             if os.path.isfile(p) and _is_input_name(p)]
    return sorted(os.path.relpath(p, inputs).replace(os.sep, "/") for p in found)


DONE_KEYS = ("path", "file", "name", "item", "item_id", "id")  # what names a file in a done.jsonl line


def done_digests(path: str) -> Dict[str, str]:
    """The sha256 of the fetched files in a done.jsonl (the fetch tool, tools/cdd_fetch.py, writes one line per
    accepted file): {name: sha256}, a line's file named by "path" or "file" (a path relative to the folder, or a bare
    name) and also by "item"/"item_id"/"id" (the file's name without .tif). A line without a sha256 is skipped; a line
    that is not JSON (a fetch stopped while writing it) is skipped with one log line (its number, never its text)."""
    digests: Dict[str, str] = {}
    if not os.path.exists(path):
        return digests
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                print(f"{path}: line {n} is not JSON (a fetch stopped while writing it?): skipped", flush=True)
                continue
            digest = row.get("sha256") if isinstance(row, dict) else None
            if not digest:
                continue
            if not any(row.get(key) for key in DONE_KEYS):
                raise ValueError(f"{path}: line {n} has a sha256 but none of the keys {', '.join(DONE_KEYS)}: "
                                 "done_digests must read the fetch tool's keys")
            for key in ("path", "file", "name"):
                if row.get(key):
                    digests[str(row[key]).replace("\\", "/")] = digest
                    digests[os.path.basename(str(row[key]))] = digest
            for key in ("item", "item_id", "id"):
                if row.get(key):
                    digests[f"{row[key]}.tif"] = digest
    return digests


def _member_names(archive: zipfile.ZipFile, patterns: Sequence[str]) -> List[str]:
    """The members matching the patterns, in the patterns' order (each pattern's matches by name, either case);
    ValueError when a pattern matches nothing."""
    names = [i.filename for i in archive.infolist() if not i.is_dir()]
    found = []
    for pattern in patterns:
        p = pattern.lower()
        matched = sorted(n for n in names if fnmatch.fnmatchcase(n.lower(), p) or fnmatch.fnmatchcase(
            os.path.basename(n).lower(), p))
        if not matched:
            raise ValueError(f"{archive.filename}: no member matches {pattern!r}")
        found += [n for n in matched if n not in found]
    return found


def member_path(work: str, archive_path: str, member: str, single: bool) -> str:
    """Where a ZIP member is unpacked in work: as its own name when the input names one member (as before), else in
    a folder of the ZIP's name."""
    if single:
        return os.path.join(work, os.path.basename(member))
    stem = os.path.splitext(os.path.basename(archive_path))[0]
    return os.path.join(work, stem, *member.split("/"))


def _single(members: Sequence[str]) -> bool:
    return len(members) == 1 and not any(c in members[0] for c in "*?[")


def file_stamp(path: str) -> str:
    """A file's size and modification time: what tells that it changed."""
    st = os.stat(path)
    return f"{st.st_size}:{st.st_mtime_ns}"


def member_stamp(info: zipfile.ZipInfo) -> str:
    """A ZIP member's content by its CRC and size (the same member unpacked again is the same raster)."""
    return f"crc:{info.CRC:08x}:{info.file_size}"


class WorkFiles:
    """The files the tool itself made in --work (unpacked ZIP members, tiled copies), each with its source and the
    source's stamp (<work>/state/work-files.sqlite): a copy is used only while its record matches its source, a copy
    without a record is made again, and clean removes only these files."""

    def __init__(self, work: str):
        folder = os.path.join(work, "state")
        os.makedirs(folder, exist_ok=True)
        self.work = work
        self.db = sqlite3.connect(os.path.join(folder, "work-files.sqlite"))
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, kind TEXT, source TEXT, "
                            "stamp TEXT)")

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def valid(self, path: str, stamp: Optional[str]) -> bool:
        """Whether path is a copy the tool made of a source of this stamp (None: any stamp), and still there."""
        row = self.db.execute("SELECT stamp FROM files WHERE path = ?", (self._key(path),)).fetchone()
        return bool(row) and (stamp is None or row[0] == stamp) and os.path.exists(path)

    def record(self, path: str, kind: str, source: str, stamp: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO files (path, kind, source, stamp) VALUES (?, ?, ?, ?)",
                            (self._key(path), kind, source, stamp))

    def made(self, path: str) -> bool:
        return self.db.execute("SELECT 1 FROM files WHERE path = ?", (self._key(path),)).fetchone() is not None

    def forget(self, path: str):
        with self.db:
            self.db.execute("DELETE FROM files WHERE path = ?", (self._key(path),))

    def close(self):
        self.db.close()


@dataclass
class Raster:
    """One raster of a product: id (stable: a file's path below --inputs or a ZIP member's), the file the tool reads
    (path: the input itself, or a member it unpacked into --work), its stamp (what tells it changed: a member's CRC,
    a folder file's sha256 of done.jsonl, else the file's size and time), the expected sha256 of a folder's file."""
    id: str
    path: str
    stamp: str
    sha256: Optional[str] = None


@dataclass
class Resolved:
    """A product's rasters as found now, and whether every input is complete (then nothing more will come)."""
    rasters: List[Raster] = field(default_factory=list)
    complete: bool = True
    missing: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)  # how many of a folder's files done.jsonl names
    counts: List[str] = field(default_factory=list)   # per folder: "<present> of <expected>"


def resolve(product: Product, work: str, inputs: Optional[str], files: Optional[WorkFiles] = None) -> Resolved:
    """The product's rasters on disk now (ZIP members unpacked by extract), in the order of its inputs; complete when
    every input is there whole. A folder's file that a present done.jsonl does not name yet (the fetch renames, then
    records it; a file being replaced) is no input in this run: counted in `checks`."""
    own = files is None
    files = files or WorkFiles(work)
    out = Resolved()
    try:
        for spec in product.inputs:
            if isinstance(spec, Folder):
                _resolve_folder(spec, inputs, out)
                continue
            path = zip_path(spec, work) if isinstance(spec, Url) else placed_path(spec, inputs)
            if isinstance(spec, Url) and not os.path.exists(path):  # a download is renamed only when whole
                target = member_path(work, path, spec.members[0], True) if _single(spec.members) else None
                if target and files.valid(target, None):  # the ZIP removed after its one member was unpacked
                    row = files.db.execute("SELECT stamp FROM files WHERE path = ?", (files._key(target),)).fetchone()
                    out.rasters.append(Raster(f"{os.path.basename(path)}!{spec.members[0]}", target, row[0]))
                    continue
                path = None
            if path is None:
                out.complete = False
                out.missing.append(spec.url if isinstance(spec, Url) else spec.pattern)
                continue
            if not spec.members:
                out.rasters.append(Raster(os.path.basename(path), path, file_stamp(path)))
                continue
            with zipfile.ZipFile(path) as archive:
                for member in _member_names(archive, spec.members):
                    target = member_path(work, path, member, _single(spec.members))
                    rid = f"{os.path.basename(path)}!{member}"
                    stamp = member_stamp(archive.getinfo(member))
                    if not files.valid(target, stamp):
                        out.complete = False
                        out.missing.append(f"{rid} (not unpacked: extract)")
                        continue
                    out.rasters.append(Raster(rid, target, stamp))
    finally:
        if own:
            files.close()
    return out


def _resolve_folder(spec: Folder, inputs: Optional[str], out: Resolved):
    files = folder_files(spec, inputs)
    done = os.path.join(inputs, spec.path, spec.done) if spec.done else None
    has_done = bool(done) and os.path.exists(done)
    digests = done_digests(done) if has_done else {}
    named, waiting = 0, 0
    for rel in files:
        below = os.path.relpath(rel, spec.path.replace("\\", "/")).replace(os.sep, "/")
        digest = digests.get(below) or digests.get(os.path.basename(rel))
        if has_done and digest is None:
            waiting += 1  # not recorded yet: no input in this run
            continue
        named += digest is not None
        path = os.path.join(inputs, rel)
        out.rasters.append(Raster(rel, path, f"sha256:{digest}" if digest else file_stamp(path), digest))
    if has_done and files and not named and digests:
        raise ValueError(f"{done}: names none of the {len(files)} files of {spec.path} (its keys do not match, or "
                         "every file is being recorded: run again): done_digests reads the fetch tool's keys")
    if has_done:
        out.checks.append(f"{spec.path}: {named} of {len(files)} files named in {spec.done}"
                          + (f"; {waiting} not named yet: no inputs in this run" if waiting else ""))
    elif done:
        out.checks.append(f"{spec.path}: no {spec.done}, the files not checked")
    present = len(files) - waiting
    out.counts.append(f"{spec.path}: {present} of {spec.expected if spec.expected is not None else '?'}")
    if spec.expected is None or present < spec.expected:
        out.complete = False
        out.missing.append(f"{spec.path}: {present} of {spec.expected or '?'} rasters")
    elif present > spec.expected:
        raise ValueError(f"{spec.path}: {present} rasters, {spec.expected} declared")


# Extract

def extracted(spec: Dict, work: str) -> str:
    """The unpacked member of a dataset of before."""
    return os.path.join(work, os.path.basename(spec["member"]))


def extract(name: str, work: str, inputs: Optional[str] = None, product: Optional[str] = None,
            max_memory_gb: float = MAX_MEMORY_GB) -> List[str]:
    """Every ZIP member of the dataset's inputs unpacked into work (through a .part, removed when the unpacking
    fails), an ASCII grid and a raster of strips too wide for the bound copied into a tiled GeoTIFF beside it; the
    paths of the members. A member or copy is made again when its source changed (WorkFiles)."""
    ds = dataset(name)
    paths = []
    with _work_lock(work):
        files = WorkFiles(work)
        try:
            for prod in _products(ds, product):
                for spec in prod.inputs:
                    if isinstance(spec, Folder) or not spec.members:
                        continue
                    path = zip_path(spec, work) if isinstance(spec, Url) else placed_path(spec, inputs)
                    if path is None or not os.path.exists(path):
                        raise ValueError(f"{spec.url if isinstance(spec, Url) else spec.pattern}: not there yet "
                                         "(download it or place it first)")
                    with zipfile.ZipFile(path) as archive:
                        for member in _member_names(archive, spec.members):
                            paths.append(_unpack(archive, path, member,
                                                 member_path(work, path, member, _single(spec.members)), work, files))
                for raster in resolve(prod, work, inputs, files).rasters:
                    readable(raster, work, prod.res, max_memory_gb, files)
        finally:
            files.close()
    return paths


def _unpack(archive: zipfile.ZipFile, archive_path: str, member: str, path: str, work: str, files: WorkFiles) -> str:
    """member unpacked to path: zipfile for stored and Deflate members (its CRC checked), 7-Zip for the others
    (Deflate64; 7-Zip checks the CRC); kept while its record names the member's CRC and size."""
    info = archive.getinfo(member)
    stamp = member_stamp(info)
    if files.valid(path, stamp):
        print(f"{path}: already extracted ({info.file_size / 1e9:.2f} GB)")
        return path
    made = None
    if not os.path.isdir(os.path.dirname(path)):
        made = os.path.dirname(path)
        os.makedirs(made)
    start, part = time.time(), path + ".part"
    try:
        if info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with archive.open(info) as src, open(part, "wb") as dst:
                shutil.copyfileobj(src, dst, 64 << 20)
        else:
            _seven_zip(archive_path, member, part)
        if os.path.getsize(part) != info.file_size:
            raise RuntimeError(f"{part}: {os.path.getsize(part)} bytes, {info.file_size} expected")
    except BaseException:
        if os.path.exists(part):
            _remove(part, work)
        if made and not os.listdir(made):
            os.rmdir(made)
        raise
    os.replace(part, path)
    files.record(path, "member", f"{archive_path}!{member}", stamp)
    print(f"{path}: {info.file_size / 1e9:.2f} GB in {(time.time() - start) / 60:.1f} min", flush=True)
    return path


def _seven_zip(archive: str, member: str, out: str):
    """member of archive written to out by 7-Zip (its standard output); RuntimeError if 7-Zip fails (a CRC error
    too)."""
    if not os.path.exists(SEVEN_ZIP) and not shutil.which(SEVEN_ZIP):
        raise RuntimeError(f"7-Zip is needed for this archive (Deflate64): not found at {SEVEN_ZIP} "
                           "(set FINDALINE_7ZIP to its 7z executable)")
    with open(out, "wb") as f:
        result = subprocess.run([SEVEN_ZIP, "e", "-so", "-bd", archive, member], stdout=f, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"7-Zip failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace')[-500:]}")


# Reading an ESRI ASCII grid (forwards only)

class AscBands:
    """An ESRI ASCII grid read line by line (decimal points or commas, LF or CRLF; a row may run over several
    lines): the header (ncols, nrows, xllcorner or xllcenter, yllcorner or yllcenter, cellsize, NODATA_value), then
    nrows rows of ncols values from the top. A row of another number of values, or a value that is not a number,
    raises ValueError. rows(r0, r1) gives rows r0 to r1 as float32 with NaN for every no-data value (rows asked in
    increasing order)."""

    KEYS = ("ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "nodata_value")

    def __init__(self, path: str, nodata: Tuple[float, ...]):
        self.f = open(path, "rb")
        header, self._pending = {}, None
        while True:
            line = self.f.readline()
            if not line:
                raise ValueError(f"{path}: no data after the header")
            parts = line.split()
            if not parts:
                continue
            key = parts[0].decode("ascii", "replace").lower()
            if key not in self.KEYS:
                self._pending = line  # the first row of values
                break
            header[key] = float(parts[1].replace(b",", b"."))
        missing = {"ncols", "nrows", "cellsize"} - set(header)
        if missing or not ({"xllcorner", "xllcenter"} & set(header)) or not ({"yllcorner", "yllcenter"} & set(header)):
            raise ValueError(f"{path}: incomplete header {header}")
        self.nodata = tuple(nodata) + ((header["nodata_value"],) if "nodata_value" in header else ())
        self.file_nodata = header.get("nodata_value")
        self.width, self.height, self.res = int(header["ncols"]), int(header["nrows"]), header["cellsize"]
        half = self.res / 2
        self.left = header["xllcorner"] if "xllcorner" in header else header["xllcenter"] - half
        bottom = header["yllcorner"] if "yllcorner" in header else header["yllcenter"] - half
        self.top = bottom + self.height * self.res
        self.crs = None
        self.row = 0  # the next row to read

    def _masked(self, values: np.ndarray) -> np.ndarray:
        values = values.astype(np.float32, copy=False)
        for value in self.nodata:
            values[values == np.float32(value)] = np.nan
        return values

    def _line(self) -> bytes:
        if self._pending is not None:
            line, self._pending = self._pending, None
            return line
        line = self.f.readline()
        if not line:
            raise ValueError(f"the grid ends at row {self.row} of {self.height}")
        return line

    def _values(self) -> np.ndarray:
        found, n = [], 0
        while n < self.width:
            line = self._line().replace(b",", b".")
            if not line.strip():
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # numpy warns (or raises) on a value it cannot read
                values = np.fromstring(line, dtype=np.float32, sep=" ")
            found.append(values)
            n += values.size
        if n != self.width:
            raise ValueError(f"row {self.row}: {n} values, {self.width} expected")
        self.row += 1
        return found[0] if len(found) == 1 else np.concatenate(found)

    def raw_rows(self, r0: int, r1: int) -> np.ndarray:
        """Rows r0 to r1 as written (float32, no-data values kept)."""
        if r0 < self.row:
            raise ValueError(f"rows are read from the top: row {r0} asked after row {self.row}")
        while self.row < r0:
            self._values()
        out = np.empty((r1 - r0, self.width), dtype=np.float32)
        for k in range(r1 - r0):
            out[k] = self._values()
        return out

    def rows(self, r0: int, r1: int) -> np.ndarray:
        return self._masked(self.raw_rows(r0, r1))

    def close(self):
        self.f.close()


# Rasters readable by windows

def _budget(max_memory_gb: float) -> Tuple[int, int]:
    """(GDAL's cache, what is left for the tiles in flight), in bytes, within the bound."""
    total = int(max_memory_gb * 1e9) - BASE_MB * 1_000_000
    cache_bytes = max(64 << 20, min(total // 4, 2 << 30))
    return cache_bytes, total - cache_bytes


def tile_px(res: float) -> int:
    px = round(TILE_M / res)
    if not math.isclose(px * res, TILE_M):
        raise ValueError(f"{res} m pixels do not divide {TILE_M} m tiles")
    return px


def readable(raster: Raster, work: str, res: float, max_memory_gb: float = MAX_MEMORY_GB,
             files: Optional[WorkFiles] = None, product: Optional["Product"] = None):
    """The file to read a raster's windows from: its own, or a tiled GeoTIFF copy in work (an ASCII grid; a raster
    of strips whose one row of tiles would not fit in GDAL's cache within the bound), made when missing or when its
    record does not name the raster's present stamp. With a product: (that file, its Footprint), the file opened
    once (a first scan of many files)."""
    own = files is None
    files = files or WorkFiles(work)
    try:
        path, copy = raster.path, _copy_path(raster.path, work)
        if files.valid(copy, raster.stamp):
            found = copy
        elif path.lower().endswith(".asc"):
            found = _record(files, _asc_copy(path, copy, max_memory_gb), path, raster.stamp)
        else:
            with rio.open(path) as src:
                block_h, block_w = src.block_shapes[0]
                cache_bytes, _ = _budget(max_memory_gb)
                band = tile_px(res) * src.width * np.dtype(src.dtypes[0]).itemsize  # one row of tiles' strips
                if block_w < src.width or band <= cache_bytes // 2:
                    return path if product is None else (path, _footprint_of(src, product, path))
            found = _record(files, _strip_copy(path, copy, max_memory_gb), path, raster.stamp)
        return found if product is None else (found, footprint(found, product))
    finally:
        if own:
            files.close()


def _record(files: WorkFiles, copy: str, source: str, stamp: str) -> str:
    files.record(copy, "copy", source, stamp)
    return copy


def _copy_path(path: str, work: str) -> str:
    digest = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:10]
    return os.path.join(work, "tiled", f"{os.path.splitext(os.path.basename(path))[0]}-{digest}.tif")


COPY_PROFILE = dict(driver="GTiff", tiled=True, blockxsize=512, blockysize=512, compress="ZSTD", zstd_level=1,
                    BIGTIFF="IF_SAFER")


def _rows_per_chunk(width: int, itemsize: int, max_memory_gb: float) -> int:
    _, left = _budget(max_memory_gb)
    rows = left // max(1, width * itemsize * 3)
    if rows < 1:
        raise ValueError(f"one row of {width} px does not fit in {max_memory_gb:g} GB")
    return int(rows // 512 * 512 if rows >= 512 else rows)


def _asc_copy(path: str, copy: str, max_memory_gb: float) -> str:
    """An ASCII grid copied into a tiled GeoTIFF of float32 (its values as read, its NODATA_value as the tag),
    in chunks of rows within the bound."""
    bands = AscBands(path, ())
    try:
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        rows = _rows_per_chunk(bands.width, 4, max_memory_gb)
        start, part = time.time(), copy + ".part"
        with rio.Env(GDAL_CACHEMAX=_budget(max_memory_gb)[0] >> 20), \
                rio.open(part, "w", width=bands.width, height=bands.height, count=1, dtype="float32",
                         transform=from_origin(bands.left, bands.top, bands.res, bands.res),
                         nodata=bands.file_nodata, **COPY_PROFILE) as dst:
            for r0 in range(0, bands.height, rows):
                r1 = min(r0 + rows, bands.height)
                dst.write(bands.raw_rows(r0, r1), 1, window=Window(0, r0, bands.width, r1 - r0))
        _replace(part, copy)
        print(f"{copy}: the ASCII grid as a tiled GeoTIFF in {(time.time() - start) / 60:.1f} min", flush=True)
        return copy
    finally:
        bands.close()


def _strip_copy(path: str, copy: str, max_memory_gb: float) -> str:
    """A raster of full-width strips copied into a tiled GeoTIFF (lossless, its own type and tags), in chunks of
    rows within the bound."""
    os.makedirs(os.path.dirname(copy), exist_ok=True)
    start, part = time.time(), copy + ".part"
    with rio.Env(GDAL_CACHEMAX=_budget(max_memory_gb)[0] >> 20), rio.open(path) as src:
        rows = _rows_per_chunk(src.width, np.dtype(src.dtypes[0]).itemsize, max_memory_gb)
        profile = dict(width=src.width, height=src.height, count=1, dtype=src.dtypes[0], crs=src.crs,
                       transform=src.transform, nodata=src.nodata, **COPY_PROFILE)
        if np.dtype(src.dtypes[0]).kind == "f":
            profile["predictor"] = 3
        with rio.open(part, "w", **profile) as dst:
            for r0 in range(0, src.height, rows):
                r1 = min(r0 + rows, src.height)
                window = Window(0, r0, src.width, r1 - r0)
                dst.write(src.read(1, window=window), 1, window=window)
    _replace(part, copy)
    print(f"{copy}: {path} as a tiled GeoTIFF (strips {src.width} px wide) in {(time.time() - start) / 60:.1f} min",
          flush=True)
    return copy


@dataclass
class Footprint:
    """A raster's place on the product's grid: its left and top edges (snapped onto the grid), size in pixels, its
    own nodata and CRS label, the file to read."""
    left: float
    top: float
    width: int
    height: int
    nodata: Optional[float]
    crs_label: Optional[str]
    path: str


def _on_grid(value: float, origin: float, res: float, what: str) -> float:
    """value moved onto the pixel grid through origin (within 1 mm: ASCII headers carry such noise); ValueError when
    it is not on it."""
    snapped = origin + round((value - origin) / res) * res
    if abs(snapped - value) > 1e-3:
        raise ValueError(f"the raster's {what} {value} is not on the grid of {res} m pixels through {origin} "
                         "(the dataset's origin is wrong)")
    return snapped


def footprint(path: str, product: Product) -> Footprint:
    """Where a raster file lies on the product's grid (its header only); ValueError when it is not on it."""
    with rio.open(path) as src:
        return _footprint_of(src, product, path)


def _footprint_of(src, product: Product, path: str) -> Footprint:
    res, (ox, oy) = product.res, product.origin
    if src.count != 1 or src.transform.b or src.transform.d or src.transform.e >= 0:
        raise ValueError(f"{path}: one band, north up, without rotation expected")
    if not (math.isclose(src.res[0], res, rel_tol=1e-9) and math.isclose(src.res[1], res, rel_tol=1e-9)):
        raise ValueError(f"{path}: {src.res} m pixels, {res} m expected")
    label = None
    if src.crs is not None:
        epsg = src.crs.to_epsg()
        label = f"EPSG:{epsg}" if epsg else src.crs.to_string()
    return Footprint(_on_grid(src.transform.c, ox, res, "left edge"),
                     _on_grid(src.transform.f, oy, res, "top edge"), src.width, src.height, src.nodata, label, path)


def tiles_of(fp: Footprint, product: Product) -> Tuple[range, range]:
    """The rows (from the top) and columns of tiles a footprint touches."""
    (ox, oy), res = product.origin, product.res
    right, bottom = fp.left + fp.width * res, fp.top - fp.height * res
    rows = range(math.ceil((fp.top - oy) / TILE_M) - 1, math.floor((bottom - oy) / TILE_M) - 1, -1)
    cols = range(math.floor((fp.left - ox) / TILE_M), math.ceil((right - ox) / TILE_M))
    return rows, cols


# The work's state: which rasters fed each tile, footprints and checked files

STATE_BATCH = 1000  # rasters written to the state per transaction (a first scan of 180 000 files)


class State:
    """<work>/state/<dataset>.<product>.sqlite: footprints of the rasters (by id, stamp and grid), the files checked
    against their sha256, and for each tile cut the rasters that fed it with their stamps ({id: stamp})."""

    def __init__(self, work: str, ds: Dataset, product: Product):
        folder = os.path.join(work, "state")
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, f"{ds.name}.{product.name}.sqlite")
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        self.pending: List[tuple] = []
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS rasters (id TEXT PRIMARY KEY, stamp TEXT, footprint TEXT, "
                            "checked INTEGER DEFAULT 0)")
            self.db.execute("CREATE TABLE IF NOT EXISTS tiles (key TEXT PRIMARY KEY, fed TEXT)")
        self.known = {rid: (stamp, fp, checked) for rid, stamp, fp, checked in
                      self.db.execute("SELECT id, stamp, footprint, checked FROM rasters")}

    @staticmethod
    def _stamp(raster: Raster, product: Product) -> str:
        # the file's size and time, and the grid it was placed on (another origin is checked again)
        return f"{file_stamp(raster.path)}:{product.res:g}:{product.origin[0]:g}:{product.origin[1]:g}"

    def footprint(self, raster: Raster, product: Product, read_path) -> Footprint:
        """The raster's footprint: kept from before while the file's size and time and the grid are the same and
        the file it is read from is there, else read (read_path(): (the file to read, made when missing, and its
        footprint))."""
        stamp = self._stamp(raster, product)
        row = self.known.get(raster.id)
        if row and row[0] == stamp:
            fp = Footprint(**json.loads(row[1]))
            if os.path.exists(fp.path):
                return fp
        fp = read_path()[1]
        self.known[raster.id] = (stamp, json.dumps(fp.__dict__), 0)
        self.pending.append((raster.id, stamp, json.dumps(fp.__dict__)))
        if len(self.pending) >= STATE_BATCH:
            self.flush()
        return fp

    def flush(self):
        with self.lock, self.db:
            self.db.executemany("INSERT OR REPLACE INTO rasters (id, stamp, footprint, checked) VALUES (?, ?, ?, 0)",
                                self.pending)
        self.pending = []

    def check(self, raster: Raster, product: Product):
        """A file of a folder against its sha256 of done.jsonl, once (the result kept with its size and time)."""
        if raster.sha256 is None:
            return
        stamp = self._stamp(raster, product)
        row = self.known.get(raster.id)
        if row and row[0] == stamp and row[2]:
            return
        if _sha256(raster.path) != raster.sha256:
            raise ValueError(f"{raster.path}: its sha256 is not the one in done.jsonl (fetch it again)")
        self.flush()
        with self.lock, self.db:
            self.db.execute("UPDATE rasters SET checked = 1 WHERE id = ? AND stamp = ?", (raster.id, stamp))
        if row is not None or raster.id in self.known:
            self.known[raster.id] = (self.known[raster.id][0], self.known[raster.id][1], 1)

    def fed(self) -> Dict[str, Dict[str, Optional[str]]]:
        """For each tile cut, the rasters that fed it and their stamps (None: a state of before without stamps)."""
        found = {}
        with self.lock:
            for key, value in self.db.execute("SELECT key, fed FROM tiles"):
                fed = json.loads(value)
                found[key] = fed if isinstance(fed, dict) else {rid: None for rid in fed}
        return found

    def set_fed(self, rows: Dict[str, Dict[str, str]]):
        self.flush()
        with self.lock, self.db:
            self.db.executemany("INSERT OR REPLACE INTO tiles (key, fed) VALUES (?, ?)",
                                [(k, json.dumps(v)) for k, v in rows.items()])

    def close(self):
        if self.pending:
            self.flush()
        self.db.close()


# Cut

def _replace(tmp: str, path: str):
    """os.replace, tried again for REPLACE_SECONDS while Windows refuses it (PermissionError)."""
    deadline = time.monotonic() + REPLACE_SECONDS
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def _save_index(index: Dict, path: str):
    """index.json written atomically (sk_tiles._save_index's way, the replace tried again)."""
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(index, f)
    _replace(path + ".part", path)


def _write(path: str, tile: np.ndarray, crs: str, transform):
    """A tile in the mirror's profile (sk_tiles._write, into <path>.new), then put in place."""
    sk_tiles._write(path + ".new", tile, crs, transform)
    _replace(path + ".new", path)


def mask(values: np.ndarray, product: Product, file_nodata: Optional[float]) -> np.ndarray:
    """values as float32 with NaN for every no-data value: the file's own, the product's nodata and sea values, every
    value below its floor (compared as float32, as the values are kept)."""
    values = values.astype(np.float32, copy=False)
    for value in tuple(product.nodata) + ((file_nodata,) if file_nodata is not None else ()) + \
            ((product.sea,) if product.sea is not None else ()):
        if not np.isnan(value):
            values[values == np.float32(value)] = np.nan
    if product.floor is not None:
        with np.errstate(invalid="ignore"):
            values[values < np.float32(product.floor)] = np.nan
    return values


class Overlap(ValueError):
    """Two inputs disagree beyond the 5 mm bound where they overlap (overlap="agree")."""


class Stale(ValueError):
    """A listed tile cannot be cut again as it was: a raster that fed it is missing or has changed."""


def assemble(key: Tuple[int, int], product: Product, footprints: Sequence[Tuple[str, Footprint]],
             handles: Dict[str, "rio.DatasetReader"]) -> np.ndarray:
    """Tile (i, j) from every footprint covering it, in their order, by the product's overlap rule; NaN for no data."""
    i, j = key
    res, (ox, oy) = product.res, product.origin
    px = tile_px(res)
    tile = np.full((px, px), np.nan, dtype=np.float32)
    tile_left, tile_top = ox + i * TILE_M, oy + (j + 1) * TILE_M
    for rid, fp in footprints:
        c0 = round((tile_left - fp.left) / res)
        r0 = round((fp.top - tile_top) / res)
        r_in, r_end = max(r0, 0), min(r0 + px, fp.height)
        c_in, c_end = max(c0, 0), min(c0 + px, fp.width)
        if r_in >= r_end or c_in >= c_end:
            continue
        values = mask(handles[fp.path].read(1, window=Window(c_in, r_in, c_end - c_in, r_end - r_in)), product,
                      fp.nodata)
        target = tile[r_in - r0:r_end - r0, c_in - c0:c_end - c0]
        have, new = np.isfinite(target), np.isfinite(values)
        if product.overlap == "agree":
            both = have & new
            if both.any():
                worst = float(np.max(np.abs(target[both] - values[both])))
                if worst > MAX_Z_ERROR:
                    raise Overlap(f"tile {i}_{j}: {rid} differs by {worst:.3f} m from the inputs before it "
                                  f"(overlap must agree within {MAX_Z_ERROR} m)")
        elif product.overlap != "first":
            raise ValueError(f"overlap {product.overlap!r}: 'first' or 'agree'")
        fill = new & ~have
        target[fill] = values[fill]
    return tile


@dataclass
class Plan:
    """A product's rasters on the tile grid: the footprints in input order, the rows and columns of its extent, the
    raster ids covering each tile, and the rasters as resolved (one scan per run)."""
    footprints: List[Tuple[str, Footprint]]
    rows: range
    cols: range
    covering: Dict[Tuple[int, int], List[int]]
    complete: bool
    missing: List[str]
    input_crs: Dict[str, List[str]]
    rasters: Dict[str, Raster] = field(default_factory=dict)
    counts: List[str] = field(default_factory=list)


def plan(ds: Dataset, product: Product, work: str, inputs: Optional[str], state: State,
         max_memory_gb: float = MAX_MEMORY_GB, files: Optional[WorkFiles] = None) -> Plan:
    """Where the product's rasters lie (every file found now; the folder's checked against done.jsonl as they are
    read, in cut)."""
    own = files is None
    files = files or WorkFiles(work)
    try:
        resolved = resolve(product, work, inputs, files)
        footprints, input_crs = [], {}
        for raster in resolved.rasters:
            fp = state.footprint(raster, product,
                                 lambda r=raster: readable(r, work, product.res, max_memory_gb, files, product))
            footprints.append((raster.id, fp))
            if fp.crs_label is not None and not _same_crs(fp.crs_label, product.crs):
                input_crs.setdefault(fp.crs_label, []).append(raster.id)
        state.flush()
    finally:
        if own:
            files.close()
    covering: Dict[Tuple[int, int], List[int]] = {}
    top = bottom = left = right = None
    for n, (_, fp) in enumerate(footprints):
        rows, cols = tiles_of(fp, product)
        for j in rows:
            for i in cols:
                covering.setdefault((i, j), []).append(n)
        top = rows[0] if top is None else max(top, rows[0])
        bottom = rows[-1] if bottom is None else min(bottom, rows[-1])
        left = cols[0] if left is None else min(left, cols[0])
        right = cols[-1] if right is None else max(right, cols[-1])
    for line in resolved.checks:
        print(f"  {line}", flush=True)
    rasters = {r.id: r for r in resolved.rasters}
    if not footprints:
        return Plan([], range(0), range(0), {}, resolved.complete, resolved.missing, input_crs, rasters,
                    resolved.counts)
    return Plan(footprints, range(top, bottom - 1, -1), range(left, right + 1), covering, resolved.complete,
                resolved.missing, input_crs, rasters, resolved.counts)


def _same_crs(label: str, crs: str) -> bool:
    if label == crs:
        return True
    from rasterio.crs import CRS
    try:
        return CRS.from_user_input(label) == CRS.from_user_input(crs)
    except Exception:
        return False


def _products(ds: Dataset, product: Optional[str]) -> List[Product]:
    if product is None:
        return list(ds.products)
    found = [p for p in ds.products if p.name == product]
    if not found:
        raise ValueError(f"{ds.name} has no product {product!r}: {', '.join(p.name for p in ds.products)}")
    return found


PARTIAL_INDEX = "index.partial.json"


def _folder(out: str, ds: Dataset, product: Product) -> str:
    return os.path.join(out, *tile_folder(ds, product).split("/"))


def _load_index(path: str) -> Dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"tiles": {}}


def product_index(folder: str) -> Tuple[Dict, bool]:
    """A product's index and whether it is final: index.json, else the index.partial.json of a product of many
    inputs still being cut ({"tiles": {}} when neither is there)."""
    final = os.path.join(folder, "index.json")
    if os.path.exists(final):
        return _load_index(final), True
    return _load_index(os.path.join(folder, PARTIAL_INDEX)), False


def _workers(product: Product, threads: int, max_memory_gb: float) -> Tuple[int, int]:
    """(tiles written at once, GDAL's cache in MB) within the bound; ValueError when not one tile fits."""
    cache_bytes, left = _budget(max_memory_gb)
    per_tile = tile_px(product.res) ** 2 * TILE_BYTES_PER_PX
    workers = min(max(1, threads), left // per_tile - 1)  # one more tile is being assembled
    if workers < 1:
        raise ValueError(f"--max-memory-gb {max_memory_gb:g}: too little for one tile of {product.res:g} m "
                         f"({2 * per_tile / 1e9:.2f} GB beside GDAL's cache of {cache_bytes / 1e9:.2f} GB and "
                         f"{BASE_MB} MB of base)")
    return int(workers), cache_bytes >> 20


def cut(name: str, work: str, out: str, rows_limit: Optional[int] = None, inputs: Optional[str] = None,
        product: Optional[str] = None, threads: int = THREADS, max_memory_gb: float = MAX_MEMORY_GB) -> Dict:
    """Cut every product of the dataset (or the one named) into 2 km tiles under out, resuming (see the module's
    docstring); rows_limit stops after that many rows of tiles to cut (a trial). The index of the last product."""
    ds = dataset(name)
    check_names(ds)
    index = {}
    with _work_lock(work):
        for prod in _products(ds, product):
            with _product_lock(out, ds, prod):
                index = _cut_product(ds, prod, work, out, rows_limit, inputs, threads, max_memory_gb)
        write_card(ds, out)
    return index


def _clean_strays(folder: str):
    """Files a stopped cut left (a tile's .new or .part, the index's .part): removed before cutting again."""
    if not os.path.isdir(folder):
        return
    for root, _, names in os.walk(folder):
        for name in names:
            if name.endswith((".new", ".part")):
                _remove(os.path.join(root, name), folder)


def _todo(index: Dict, p: Plan, fed_before: Dict[str, Dict[str, Optional[str]]]) -> Tuple[Dict, int]:
    """The tiles to cut now, {(i, j): the ids covering it}, and how many listed tiles have no record of what fed
    them (final: never cut again). Stale when a listed tile would be cut again while a raster that fed it is missing,
    or when a raster that fed it changed: nothing is cut then."""
    ids = [rid for rid, _ in p.footprints]
    stamps = {rid: p.rasters[rid].stamp for rid in ids}
    todo, unrecorded = {}, 0
    for j in p.rows:
        for i in p.cols:
            key = f"{i}_{j}"
            cover = [ids[n] for n in p.covering.get((i, j), [])]
            record = fed_before.get(key)
            if key in index["tiles"]:
                if record is None:
                    unrecorded += 1  # cut by a run without the state: final
                    continue
                changed = [r for r, s in record.items() if r in stamps and s is not None and s != stamps[r]]
                if changed:
                    raise Stale(f"tile {key}: {len(changed)} raster(s) that fed it changed since it was cut "
                                f"({', '.join(changed[:5])}): put back the files it was cut from, or cut this product "
                                "into a fresh mirror folder (--out)")
                added = [r for r in cover if r not in record]
                if not added:
                    continue
                gone = [r for r in record if r not in stamps]
                if gone:
                    raise Stale(f"tile {key}: {len(added)} new raster(s) cover it ({', '.join(added[:3])}), but "
                                f"{len(gone)} that fed it are missing ({', '.join(gone[:5])}): fetch them again, or "
                                "cut this product into a fresh mirror folder (--out)")
                todo[(i, j)] = cover
            elif cover:
                # no data from the same rasters before: listed (null) only once every input is complete
                if record is not None and set(cover) <= set(record) and not p.complete:
                    continue
                todo[(i, j)] = cover
            elif p.complete:
                todo[(i, j)] = []
    return todo, unrecorded


def _cut_product(ds: Dataset, product: Product, work: str, out: str, rows_limit: Optional[int],
                 inputs: Optional[str], threads: int, max_memory_gb: float) -> Dict:
    folder = _folder(out, ds, product)
    final_path, partial_path = os.path.join(folder, "index.json"), os.path.join(folder, PARTIAL_INDEX)
    if ds.legacy:
        index, was_complete = _load_index(final_path), False
        was_complete = bool(index["tiles"]) and not index.get("partial")
    else:
        index, was_complete = product_index(folder)
    _clean_strays(folder)
    workers, cache_mb = _workers(product, threads, max_memory_gb)
    state, files = State(work, ds, product), WorkFiles(work)
    start, cut_rows = time.time(), 0

    def save():
        os.makedirs(folder, exist_ok=True)
        finished = _finished(index, p, was_complete)
        if ds.legacy:
            sk_tiles._mark_partial(index, not finished)
            _save_index(index, final_path)
        elif finished:
            index.pop("partial", None)
            _save_index(index, final_path)
            if os.path.exists(partial_path):
                _remove(partial_path, folder)
        else:
            index["partial"] = True
            _save_index(index, partial_path)

    try:
        with rio.Env(GDAL_CACHEMAX=cache_mb, GDAL_NUM_THREADS=str(max(1, threads))):
            p = plan(ds, product, work, inputs, state, max_memory_gb, files)
            if not p.footprints:
                print(f"{tile_folder(ds, product)}: no raster yet ({'; '.join(p.missing)})", flush=True)
                return index
            todo, unrecorded = _todo(index, p, state.fed())
            px = tile_px(product.res)
            print(f"{tile_folder(ds, product)}: {len(p.footprints)} raster(s), {len(p.rows)} x {len(p.cols)} tiles of "
                  f"{px} px, {len(todo)} to cut, {workers} at a time, GDAL's cache {cache_mb} MB"
                  + ("" if p.complete else f"; not complete: {'; '.join(p.missing[:3])}"), flush=True)
            if unrecorded:
                print(f"  {unrecorded} listed tile(s) without a record of what fed them (cut without this work "
                      "folder's state): final, never cut again", flush=True)
            for label, which in p.input_crs.items():
                print(f"  {len(which)} raster(s) labelled {label}: read as {product.crs}", flush=True)

            # each raster's last row of tiles (rows go down): its file is closed once that row is cut
            last_row: Dict[str, int] = {}
            for _, fp in p.footprints:
                last_row[fp.path] = min(last_row.get(fp.path, 1 << 30), tiles_of(fp, product)[0][-1])
            handles: Dict[str, "rio.DatasetReader"] = {}
            checked = set()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                try:
                    for n, j in enumerate(p.rows):
                        row = [(i, todo[(i, j)]) for i in p.cols if (i, j) in todo]
                        if not row:
                            continue
                        if rows_limit is not None and cut_rows >= rows_limit:
                            break
                        cut_rows += 1
                        pending, results = deque(), {}
                        for i, cover in row:
                            fps = [p.footprints[k] for k in p.covering.get((i, j), [])]
                            for rid, fp in fps:
                                if rid not in checked:
                                    state.check(p.rasters[rid], product)
                                    checked.add(rid)
                                if fp.path not in handles:
                                    handles[fp.path] = rio.open(fp.path)
                            tile = assemble((i, j), product, fps, handles) if fps else None
                            pending.append((i, cover, pool.submit(_save_tile, folder, product, i, j, tile)))
                            while len(pending) > workers:
                                ii, cc, fut = pending.popleft()
                                results[ii] = (cc, fut.result())
                        while pending:
                            ii, cc, fut = pending.popleft()
                            results[ii] = (cc, fut.result())
                        fed = {}
                        for i in sorted(results):
                            cover, digest = results[i]
                            key = f"{i}_{j}"
                            fed[key] = {rid: p.rasters[rid].stamp for rid in cover}
                            if digest is None and not p.complete:
                                index["tiles"].pop(key, None)  # no data from what is there: listed once complete
                                continue
                            index["tiles"][key] = digest
                        _update_index(index, ds, product, p)
                        save()
                        state.set_fed(fed)
                        for path in [path for path in handles if last_row[path] >= j]:
                            handles.pop(path).close()
                        done = sum(v is not None for v in index["tiles"].values())
                        print(f"  row {n + 1}/{len(p.rows)}: {done} tiles with data, "
                              f"{(time.time() - start) / 60:.1f} min", flush=True)
                finally:
                    for h in handles.values():
                        h.close()
            if index["tiles"]:
                on_disk = os.path.exists(final_path) if not ds.legacy else not _load_index(final_path).get("partial")
                if on_disk != _finished(index, p, was_complete) or (not ds.legacy and not os.path.exists(
                        final_path) and not os.path.exists(partial_path)):
                    _update_index(index, ds, product, p)
                    save()
    finally:
        state.close()
        files.close()
    tiles = [k for k, v in index["tiles"].items() if v]
    size = sum(os.path.getsize(os.path.join(folder, *tile_name(*map(int, k.split("_"))).split("/"))) for k in tiles)
    partial = not _finished(index, p, was_complete)
    print(f"{folder}: {len(tiles)} tiles with data of {len(index['tiles'])}, {size / 1e9:.2f} GB, "
          f"{(time.time() - start) / 60:.1f} min" + (" (partial: no index.json yet)" if partial and not ds.legacy
                                                     else " (partial)" if partial else ""), flush=True)
    return index


def _save_tile(folder: str, product: Product, i: int, j: int, tile: Optional[np.ndarray]) -> Optional[str]:
    """A tile written (its sha256), or None when it holds no data."""
    if tile is None or not np.isfinite(tile).any():
        return None
    (ox, oy), res = product.origin, product.res
    path = os.path.join(folder, *tile_name(i, j).split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, np.ascontiguousarray(tile), product.crs, from_origin(ox + i * TILE_M, oy + (j + 1) * TILE_M, res, res))
    return _sha256(path)


def _finished(index: Dict, p: Plan, was_complete: bool = False) -> bool:
    """Every input complete and every tile of the extent in the index; an index complete before stays complete
    when inputs went away since (every tile their rasters still cover in it)."""
    if p.complete:
        return all(f"{i}_{j}" in index["tiles"] for j in p.rows for i in p.cols)
    return was_complete and all(f"{i}_{j}" in index["tiles"] for (i, j) in p.covering)


def _update_index(index: Dict, ds: Dataset, product: Product, p: Plan):
    """The index's keys besides the tiles (those of 2026-11-15 in their order; a newer dataset's additions after
    them)."""
    urls = [spec.url for spec in product.inputs if isinstance(spec, Url)]
    source = urls[0] if ds.legacy else "; ".join(
        spec.url if isinstance(spec, Url) else spec.pattern if isinstance(spec, Placed)
        else f"{spec.path}/{spec.pattern}"
        for spec in product.inputs)
    index.update(dataset=ds.key if ds.legacy else ds.name, product=product.name,
                 title=product.title, source=source, crs=product.crs, heights=product.heights, tile_m=TILE_M,
                 resolution=product.res, origin=list(product.origin), block=BLOCK,
                 encoding=f"COG LERC_ZSTD, max_z_error {MAX_Z_ERROR} m", licence=ds.licence,
                 attribution=ds.attribution, created=datetime.date.today().isoformat())
    if ds.legacy:
        return
    masks = {"nodata": list(product.nodata) + ["the files' own"]}
    if product.sea is not None:
        masks["sea"] = product.sea
    if product.floor is not None:
        masks["below"] = product.floor
    index.update(inputs=len(p.footprints), overlap=product.overlap, masks=masks)
    if p.input_crs:
        index["input_crs"] = {label: (ids if len(ids) <= 20 else ids[:20] + [f"... {len(ids) - 20} more"])
                              for label, ids in p.input_crs.items()}
    else:
        index.pop("input_crs", None)


# The dataset card

def card_text(ds: Dataset) -> str:
    """The dataset card: a dataset's published text of before while it has its one product, else made from its
    record, every product with the changes made to it."""
    if ds.card is not None:
        if len(ds.products) != 1:
            raise ValueError(f"{ds.name}: a fixed card describes one product; with more the card is generated "
                             "(remove card=)")
        return ds.card
    lines = [f"# {ds.title} as 2 km tiles", ""]
    lines += [f"Made from the data of **{ds.provider}**" + (f" ({ds.record})" if ds.record else "") + ".",
              f"Licence: {ds.licence}. Attribution: {ds.attribution}.", ""]
    for product in ds.products:
        folder = f"{product.name}/{product.res:g}m"
        ox, oy = product.origin
        masks = ["the files' own no-data value"]
        if product.nodata:
            masks.append("the values " + ", ".join(f"{v:g}" for v in product.nodata))
        if product.sea is not None:
            masks.append(f"the sea's value {product.sea:g}")
        if product.floor is not None:
            masks.append(f"every value below {product.floor:g} m")
        joined = len(product.inputs) > 1 or any(isinstance(s, Folder) or len(s.members) > 1 for s in product.inputs)
        rule = ("the first listed wins where they overlap" if product.overlap == "first" else
                "where they overlap they agree within 5 mm")
        lines += [f"## `{folder}`: {product.title}", ""]
        if product.about:
            lines += [f"Source: {product.about}.", ""]
        lines += [f"Changes made: cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own {product.res:g} m pixel "
                  f"grid in {product.crs} (tile (i, j) starts at x = 2000 i + {ox:g}, y = 2000 j + {oy:g})"
                  + (f", the inputs joined where they meet ({rule})" if joined else "")
                  + f"; {', '.join(masks[:-1]) + ' and ' + masks[-1] if len(masks) > 1 else masks[0]} made no "
                  "data; stored with LERC compression with a maximum error of "
                  f"5 mm. Heights {product.heights}; values are not otherwise changed.", ""]
    lines += [f"Layout: `<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif`; `<product>/<res>m/index.json` lists every "
              "tile of the extent with its sha256 (null: no data). Made for Find-a-Line (a highline finder); not "
              f"endorsed by {ds.not_endorsed or ds.provider}.", ""]
    return "\n".join(lines)


def write_card(ds: Dataset, out: str):
    """README.md beside the products, written whole."""
    root = os.path.join(out, ds.name)
    os.makedirs(root, exist_ok=True)
    text = card_text(ds)
    path = os.path.join(root, "README.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    with open(path + ".part", "w", encoding="utf-8") as f:
        f.write(text)
    _replace(path + ".part", path)


# Verify

def default_samples(tiles: int) -> int:
    """Tiles with data compared with the inputs: 1 % of them, at least 8 and at most 500."""
    return max(8, min(500, tiles // 100))


def verify(name: str, work: str, out: str, inputs: Optional[str] = None, product: Optional[str] = None,
           samples: Optional[int] = None, seed: int = 0, max_memory_gb: float = MAX_MEMORY_GB,
           points: int = POINTS) -> Dict:
    """Each product's tiles against its inputs (see the module's docstring): {product: result}; each result written
    to verify.json beside the index. ok False on any failure."""
    ds = dataset(name)
    results = {}
    with _work_lock(work):
        for prod in _products(ds, product):
            with _product_lock(out, ds, prod):
                results[prod.name] = _verify_product(ds, prod, work, out, inputs, samples, seed, max_memory_gb,
                                                     points)
    return results


def _checkable(record: Optional[Dict[str, Optional[str]]], p: Plan) -> bool:
    """Whether a tile can be compared with its inputs: every raster that fed it present and unchanged (a tile
    without a record, cut without this work folder's state: only while every input of the product is complete)."""
    if record is None:
        return p.complete
    return all(r in p.rasters and (s is None or s == p.rasters[r].stamp) for r, s in record.items())


def _point_problems(key: str, got: np.ndarray, product: Product, p: Plan, rng: random.Random, n: int,
                    handles: Dict[str, "rio.DatasetReader"]) -> Tuple[List[str], int]:
    """A check apart from the cut's own reading: n random pixels of a tile, their centres' coordinates in the
    dataset's CRS read straight from the input rasters through each raster's own transform, masked by these few lines
    (not mask()), the first raster with a value taken; compared with the tile within 5 mm and for no data. The
    problems found and the pixels compared."""
    i, j = map(int, key.split("_"))
    px, res, (ox, oy) = got.shape[0], product.res, product.origin
    rows = np.array([rng.randrange(px) for _ in range(n)])
    cols = np.array([rng.randrange(px) for _ in range(n)])
    xs = ox + i * TILE_M + (cols + 0.5) * res
    ys = oy + (j + 1) * TILE_M - (rows + 0.5) * res
    found = np.full(n, np.nan)
    left, right, bottom, top = ox + i * TILE_M, ox + (i + 1) * TILE_M, oy + j * TILE_M, oy + (j + 1) * TILE_M
    for rid, fp in p.footprints:
        src = handles.get(fp.path) or handles.setdefault(fp.path, rio.open(fp.path))
        b = src.bounds
        if b.right <= left or b.left >= right or b.top <= bottom or b.bottom >= top:
            continue
        inv = ~src.transform
        cc = np.floor(inv.a * xs + inv.b * ys + inv.c).astype(int)
        rr = np.floor(inv.d * xs + inv.e * ys + inv.f).astype(int)
        inside = (rr >= 0) & (rr < src.height) & (cc >= 0) & (cc < src.width) & np.isnan(found)
        if not inside.any():
            continue
        r0, r1, c0, c1 = rr[inside].min(), rr[inside].max() + 1, cc[inside].min(), cc[inside].max() + 1
        block = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float64)
        v = block[rr[inside] - r0, cc[inside] - c0]
        bad = ~np.isfinite(v)
        for value in list(product.nodata) + [src.nodata, product.sea]:
            if value is not None and not np.isnan(value):
                bad |= v.astype(np.float32) == np.float32(value)
        if product.floor is not None:
            bad |= v < product.floor
        v[bad] = np.nan
        slots = np.flatnonzero(inside)
        found[slots[~np.isnan(v)]] = v[~np.isnan(v)]
    tile_values = got[rows, cols].astype(np.float64)
    problems = []
    nodata = np.isnan(tile_values) != np.isnan(found)
    if nodata.any():
        problems.append(f"{key}: {int(nodata.sum())} of {n} pixels read straight from the inputs differ in no data")
    both = ~np.isnan(tile_values) & ~np.isnan(found)
    if both.any():
        worst = float(np.max(np.abs(tile_values[both] - found[both])))
        if worst > VERIFY_EPS:
            problems.append(f"{key}: pixels read straight from the inputs differ by up to {worst:.4f} m")
    return problems, n


def _verify_product(ds: Dataset, product: Product, work: str, out: str, inputs: Optional[str],
                    samples: Optional[int], seed: int, max_memory_gb: float, points: int = 300) -> Dict:
    folder = _folder(out, ds, product)
    final_path = os.path.join(folder, "index.json")
    index, final = (_load_index(final_path), True) if ds.legacy else product_index(folder)
    index_sha = _sha256(final_path) if os.path.exists(final_path) else None
    problems: List[str] = []
    listed = {os.path.normcase(os.path.join(folder, *tile_name(*map(int, k.split("_"))).split("/"))): k
              for k, v in index["tiles"].items() if v}
    for key, digest in index["tiles"].items():
        path = os.path.join(folder, *tile_name(*map(int, key.split("_"))).split("/"))
        if digest is None:
            if os.path.exists(path):
                problems.append(f"{key}: listed as without data, but its file exists")
        elif not os.path.exists(path):
            problems.append(f"{key}: its file is missing")
        elif _sha256(path) != digest:
            problems.append(f"{key}: the file does not match its sha256")
    unlisted = []
    for root, _, names in os.walk(folder):
        for n in names:
            path = os.path.join(root, n)
            if os.path.normcase(path) not in listed and n not in ("index.json", PARTIAL_INDEX, "verify.json"):
                unlisted.append(os.path.relpath(path, folder).replace(os.sep, "/"))
    if unlisted:
        problems.append(f"{len(unlisted)} file(s) the index does not list: {unlisted[:5]}")
    if index.get("partial") or not final:
        problems.append("the product is partial (no index.json yet)" if not ds.legacy else "the index is partial")
    keys = [k for k, v in index["tiles"].items() if v]
    nulls = [k for k, v in index["tiles"].items() if v is None]
    samples = default_samples(len(keys)) if samples is None else samples
    compared, removed, pixels = [], [], 0
    state, files = State(work, ds, product), WorkFiles(work)
    handles: Dict[str, "rio.DatasetReader"] = {}
    try:
        _, cache_mb = _workers(product, 1, max_memory_gb)
        with rio.Env(GDAL_CACHEMAX=cache_mb):
            p = plan(ds, product, work, inputs, state, max_memory_gb, files)
            fed = state.fed()
            checkable = [k for k in keys if _checkable(fed.get(k), p)]
            checkable_nulls = [k for k in nulls if _checkable(fed.get(k), p)]
            removed = sorted(set(keys) - set(checkable)) + sorted(set(nulls) - set(checkable_nulls))
            rng = random.Random(f"{ds.name}/{product.name}/{seed}")
            chosen = sorted(rng.sample(checkable, min(samples, len(checkable))))
            chosen_nulls = sorted(rng.sample(checkable_nulls, min(2, len(checkable_nulls))))
            px = tile_px(product.res)
            ox, oy = product.origin
            for key in chosen + chosen_nulls:
                i, j = map(int, key.split("_"))
                fps = [p.footprints[k] for k in p.covering.get((i, j), [])]
                for _, fp in fps:
                    if fp.path not in handles:
                        handles[fp.path] = rio.open(fp.path)
                expected = assemble((i, j), product, fps, handles) if fps else np.full((px, px), np.nan, np.float32)
                if index["tiles"][key] is None:
                    if np.isfinite(expected).any():
                        problems.append(f"{key}: listed as without data, but the inputs have data there")
                    compared.append({"tile": key, "data": False})
                    continue
                try:
                    with rio.open(os.path.join(folder, *tile_name(i, j).split("/"))) as t:
                        got = t.read(1)
                        grid = from_origin(ox + i * TILE_M, oy + (j + 1) * TILE_M, product.res, product.res)
                        if t.transform != grid or t.shape != (px, px) or not _same_crs(t.crs.to_string(), product.crs):
                            problems.append(f"{key}: not on the product's grid or CRS ({t.crs}, {t.transform})")
                except rio.errors.RasterioError as e:
                    problems.append(f"{key}: unreadable ({e})")
                    continue
                same_nodata = bool(np.array_equal(np.isnan(got), np.isnan(expected)))
                both = np.isfinite(got) & np.isfinite(expected)
                worst = float(np.max(np.abs(got[both] - expected[both]))) if both.any() else 0.0
                if not same_nodata:
                    problems.append(f"{key}: no data differs from the inputs' "
                                    f"({int(np.sum(np.isnan(got) != np.isnan(expected)))} px)")
                if worst > VERIFY_EPS:
                    problems.append(f"{key}: differs from the inputs by {worst:.4f} m")
                found, n = _point_problems(key, got, product, p, rng, points, handles)
                problems += found
                pixels += n
                compared.append({"tile": key, "data": True, "max_diff_m": round(worst, 5),
                                 "valid_px": int(both.sum())})
    finally:
        for h in handles.values():
            h.close()
        state.close()
        files.close()
    result = {"dataset": ds.name, "product": product.name, "checked": datetime.datetime.now().isoformat(
        timespec="seconds"), "index_sha256": index_sha, "seed": seed, "samples_asked": samples,
        "tiles": len(index["tiles"]), "with_data": len(keys), "sha256_checked": len(keys), "samples": compared,
        "points_compared": pixels, "not_checkable": len(removed), "not_checkable_tiles": removed[:100],
        "unlisted": unlisted[:100], "problems": problems, "ok": not problems}
    verify_path = os.path.join(folder, "verify.json")
    before = _load_index(verify_path) if os.path.exists(verify_path) else None
    if before and not compared and not problems and before.get("ok") and before.get("index_sha256") == index_sha:
        print(f"{tile_folder(ds, product)}: verify: nothing checkable ({len(removed)} tiles: inputs removed); the "
              f"passing verify of {before.get('checked')} of this index kept", flush=True)
        return {**before, "kept": True}
    if os.path.isdir(folder):
        with open(verify_path + ".part", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        _replace(verify_path + ".part", verify_path)
    print(f"{tile_folder(ds, product)}: verify {'ok' if not problems else 'FAILED'}: {len(keys)} tiles' sha256, "
          f"{len(compared)} compared with the inputs ({pixels} pixels also read straight from them)"
          + (f", {len(removed)} tiles: inputs removed" if removed else "")
          + "".join(f"\n  {x}" for x in problems[:20]), flush=True)
    return result


def verified(ds: Dataset, product: Product, out: str) -> Optional[str]:
    """When a product is complete and its verify.json passed on this very index.json: the verify's date, else
    None."""
    folder = _folder(out, ds, product)
    final, verify_path = os.path.join(folder, "index.json"), os.path.join(folder, "verify.json")
    if not (os.path.exists(final) and os.path.exists(verify_path)):
        return None
    if ds.legacy and _load_index(final).get("partial"):
        return None
    result = _load_index(verify_path)
    return result.get("checked") if result.get("ok") and result.get("index_sha256") == _sha256(final) else None


# Status and clean

def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, n)) for r, _, ns in os.walk(path) for n in ns)


def status(names: Sequence[str], work: str, out: Optional[str], inputs: Optional[str]) -> List[str]:
    """Lines a person can read: per dataset and product, the inputs there and missing, the tiles cut (a partial
    product: why), the verify result, the work files left."""
    lines = []
    for name in names:
        ds = dataset(name)
        lines.append(f"{name}: {ds.title}")
        for product in ds.products:
            try:
                r = resolve(product, work, inputs)
            except ValueError as e:
                lines.append(f"  {product.name}/{product.res:g}m: {e}")
                continue
            lines.append(f"  {product.name}/{product.res:g}m: {len(r.rasters)} raster(s) ready"
                         + (f" ({'; '.join(r.counts)})" if r.counts else "")
                         + ("" if r.complete else f"; waiting for {', '.join(r.missing[:4])}"
                            + (f" and {len(r.missing) - 4} more" if len(r.missing) > 4 else "")))
            if out:
                folder = _folder(out, ds, product)
                index, final = product_index(folder)
                if index["tiles"]:
                    with_data = sum(v is not None for v in index["tiles"].values())
                    state = ("complete" if final and not index.get("partial") else
                             "partial (no index.json: nothing reads or publishes it)" if not final else "partial")
                    lines.append(f"    tiles: {len(index['tiles'])} listed, {with_data} with data, {state}")
                v = os.path.join(folder, "verify.json")
                if os.path.exists(v):
                    result = _load_index(v)
                    lines.append(f"    verify {result['checked']}: " + ("ok" if result["ok"] else
                                                                       "FAILED: " + "; ".join(result["problems"][:3]))
                                 + (f"; {result['not_checkable']} tiles: inputs removed"
                                    if result.get("not_checkable") else ""))
        for url in _urls(ds):
            path = zip_path(url, work)
            if os.path.exists(path):
                lines.append(f"  work: {path} ({_size(path) / 1e6:.0f} MB)")
            elif os.path.exists(path + ".part"):
                lines.append(f"  work: {path}.part, {_size(path + '.part')} of {url.bytes} bytes")
    if os.path.isdir(os.path.join(work, "tiled")):
        lines.append(f"work: tiled copies {_size(os.path.join(work, 'tiled')) / 1e9:.2f} GB")
    return lines


def clean(name: str, work: str, inputs: Optional[str] = None, product: Optional[str] = None) -> List[str]:
    """The product's unpacked members and tiled copies removed from work: only files the tool recorded as made by it
    (WorkFiles), never an input, never a downloaded file; what is left in work, as lines."""
    ds = dataset(name)
    removed = 0
    with _work_lock(work):
        files = WorkFiles(work)
        try:
            for prod in _products(ds, product):
                for raster in resolve(prod, work, inputs, files).rasters:
                    for path in (_copy_path(raster.path, work), raster.path):
                        if files.made(path) and os.path.exists(path):
                            removed += _size(path)
                            _remove(path, work)
                            files.forget(path)
        finally:
            files.close()
    left = []
    for root, _, names in os.walk(work):
        for n in names:
            left.append(f"{os.path.relpath(os.path.join(root, n), work)} ({_size(os.path.join(root, n)) / 1e6:.1f} MB)")
    print(f"{work}: {removed / 1e9:.2f} GB of unpacked and copied rasters removed; left: "
          + (", ".join(left[:10]) + (f" and {len(left) - 10} more" if len(left) > 10 else "") if left else "nothing"),
          flush=True)
    return left


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["download", "extract", "cut", "verify", "status", "clean", "all"])
    parser.add_argument("dataset", nargs="?", choices=sorted(DATASETS))
    parser.add_argument("--work", required=True, help="the tool's own files: downloads, unpacked rasters, state")
    parser.add_argument("--inputs", help="placed files and folders of rasters (default: --work)")
    parser.add_argument("--out", help=f"the mirror (default: the environment's {MIRROR_ENV})")
    parser.add_argument("--product", help="one product of the dataset")
    parser.add_argument("--rows", type=int, help="cut: stop after this many rows of tiles (a trial)")
    parser.add_argument("--threads", type=int, default=THREADS, help=f"tiles written at once (default {THREADS})")
    parser.add_argument("--max-memory-gb", type=float, default=MAX_MEMORY_GB,
                        help=f"the cut's estimated bound, GDAL's cache included (default {MAX_MEMORY_GB:g})")
    parser.add_argument("--samples", type=int, help="verify: tiles compared (default 1 %%, at least 8, at most 500)")
    parser.add_argument("--seed", type=int, default=0, help="verify: the sample's seed (default 0)")
    args = parser.parse_args()
    out = args.out or os.environ.get(MIRROR_ENV)
    inputs = args.inputs or args.work
    if args.step != "status" and not args.dataset:
        sys.exit("a dataset is needed")
    if args.step in ("cut", "verify", "all") and not out:
        sys.exit(f"--out or {MIRROR_ENV} is needed")
    if args.step == "status":
        print("\n".join(status([args.dataset] if args.dataset else sorted(DATASETS), args.work, out, inputs)))
        return
    try:
        ds = dataset(args.dataset)
        products = [prod.name for prod in _products(ds, args.product)]
        if args.step == "all":
            with _work_lock(args.work):
                todo = []
                for prod in _products(ds, args.product):
                    when = verified(ds, prod, out)
                    if when:
                        print(f"{tile_folder(ds, prod)}: complete and verified on {when}: skipped", flush=True)
                    else:
                        todo.append(prod.name)
                if not todo:
                    return
                download(args.dataset, args.work)
                for name in todo:
                    extract(args.dataset, args.work, inputs, name, args.max_memory_gb)
                    cut(args.dataset, args.work, out, args.rows, inputs, name, args.threads, args.max_memory_gb)
                    results = verify(args.dataset, args.work, out, inputs, name, args.samples, args.seed,
                                     args.max_memory_gb)
                    if not all(r["ok"] for r in results.values()):
                        sys.exit(1)
                    clean(args.dataset, args.work, inputs, name)
            return
        if args.step == "download":
            download(args.dataset, args.work)
        elif args.step == "extract":
            extract(args.dataset, args.work, inputs, args.product, args.max_memory_gb)
        elif args.step == "cut":
            cut(args.dataset, args.work, out, args.rows, inputs, args.product, args.threads, args.max_memory_gb)
        elif args.step == "verify":
            results = verify(args.dataset, args.work, out, inputs, args.product, args.samples, args.seed,
                             args.max_memory_gb)
            if not all(r["ok"] for r in results.values()):
                sys.exit(1)
        elif args.step == "clean":
            for name in products:
                clean(args.dataset, args.work, inputs, name)
    except (Busy, Stale) as e:
        sys.exit(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
