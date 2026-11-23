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
  Fetched(area, ...)     the files tools/cdd_fetch.py fetched into --inputs/<area>: the fetch tool's own files decide
                         what the product holds (every row of manifest.jsonl of a `collection`, or every file of a
                         fetch-list's `group` as status.json counts them); a file is an input when done.jsonl records
                         it and it is on disk with the recorded size; its sha256 is checked when it is read (a
                         mismatch is an error naming the file: the fetch's to fetch again); a file not recorded yet
                         is no input
Patterns match letters in either case on every system (".tif" finds ".TIF"). A Url, Placed or fetched file that is a
ZIP names its raster members (fnmatch patterns: Madeira's 5 m ZIP holds a raster per island); they are unpacked into
--work (zipfile for stored and Deflate, CRC checked; 7-Zip for Deflate64, found by FINDALINE_7ZIP or on PATH: the
project's image has none). An ESRI ASCII grid (Valle d'Aosta's, decimal commas) is read forwards only: it is copied into
a tiled GeoTIFF in --work first. So is a raster of full-width strips too wide for the memory bound. Every file the tool
makes in --work is recorded with its source's stamp (<work>/state/work-files.sqlite, a cache): a copy is used only
while its source is unchanged, and `clean` removes only these files. --work, --inputs and --out are kept apart (none
is or lies inside another, but --out beside --work): the inputs are never written or removed.

A product is cut once, when it is complete, and is final after that:
1. It is cut only when every input is there (every Url downloaded, every Placed pattern matched, every item of a
   Fetched area recorded and whole). Until then `cut` says what is missing (counts, the first 20 ids) and does
   nothing; `all` goes on to the next product (exit 0, a line "waiting: <product>: N of M"). Sheets the provider never
   delivers: `--without <id> ...` (or --without-file) makes the product complete without exactly those ids, named in
   index.json (`missing_inputs`) and in the card; an id that is present is an error.
2. While it is cut it lives in a staging folder, never in the mirror: <work>/staging/<dataset>/<product>/<res>m/ when
   a folder renames from --work into --out (tried at the start with an empty folder), else <out>/.staging/... (another
   filesystem, or another mount in a container). Nothing unfinished is ever at <out>/<dataset>/<product>/<res>m/:
   sources.GridTiles takes a dataset as there once that folder exists.
3. Every doubt before it is final is resolved by cutting again, never by stopping. The journal
   (<work>/journals/<dataset>.<product>.<res>m-<mirror>.jsonl, append-only) gets one line per finished tile (its
   key, sha256, the ids and stamps of the rasters that fed it in their order, the product's rule with CUT_VERSION)
   after the tile's file is in place and synced; a torn last line is ignored. A restart keeps a tile whose file's
   sha256 is its journal line's and whose rasters and rule are the same; every other tile of the staging folder is
   cut again, and every other file there removed. Not detected: a placed file replaced by one of the same size and
   modification time (start with a fresh --work then). A raster's id is its path below --inputs (a ZIP member's:
   <the ZIP's path>!<member>), one per product.
4. When every tile is cut, index.json is written into the staging folder, the folder is synced and renamed into the
   mirror in one step (os.replace of the folder), then the dataset's card is written whole. inputs.jsonl beside it
   records the rasters the cut read (ids and stamps; not for the datasets of before). After that nothing is cut for
   the product again: `cut` says "final"; changed, added or removed inputs are a new edition (a fresh --out or a new
   dataset name). A final product needs no state: the work folder may be deleted. A rename that crosses
   filesystems (a dataset folder linked elsewhere) stops in one sentence, the staging folder kept. `status` lists
   every staging folder; `clean` removes one whose product is final, or with --staging one no run cuts now.
A product's fetched files stay until that product is final and verified (then the user may delete them by hand).

The cut: every tile (i, j) of the product's extent (the rectangle of its rasters, on the tile grid through the
product's `origin`: tile (i, j) covers [origin_x + 2000 i, origin_x + 2000 (i + 1)) x [origin_y + 2000 j, ...)) is
assembled from the pixels of every raster that covers it, in the order of the inputs, where two overlap by the
product's rule: "first" (the first listed wins) or "agree" (within the 5 mm bound, else an error naming the tile).
Masks per product: the files' own nodata, the `nodata` values, the `sea` value, an optional `floor` (every value
below it) and NaN. The CRS is the product's, never the file's (a file's own label, when another, is recorded in the
index as `input_crs`). A product may be cut at a whole multiple of its inputs' pixel (`average`: Wallonia's 0.5 m
rasters at 1 m): the footprints, the masks and the overlap rule work on the inputs' pixels, then each pixel is the
mean of the valid input pixels of its average x average block, in float64 (sources.readers.download._block_means,
the rule of tools/sk_tiles.py average; a block without one is no data; 2 km tiles hold whole blocks); its index names
`average` and `input_resolution`, its journal rule the factor, and verify compares a sampled pixel with the mean of its
block read straight from the inputs. Tiles are written in tools/sk_tiles.py's encoding (COG LERC_ZSTD within 5 mm,
`sk_tiles._write`); index.json lists every tile of the extent with its sha256 (null: no data). The datasets of
before (Madeira 2 m, Valle d'Aosta) go the same way and keep their index keys and published cards; a folder an
earlier version of this tool left unfinished (an index saying "partial") is left alone: move it away to cut again.

Memory: the cut works tile by tile, `--threads` writers and a GDAL cache within `--max-memory-gb`. The bound is an
estimate (GDAL's cache, TILE_BYTES_PER_PX for each tile in flight and the one being assembled, BASE_MB for the
process; GDAL's own buffers and the open files are not counted; the tile being assembled of an averaged product holds
its input pixels, TILE_BYTES_PER_PX + AVERAGE_BYTES_PER_PX each): the cut refuses a bound below one tile, and in a
container the container's memory limit is the guard.

    python tools/mirror_tiles.py download porto-santo --work W          # the declared files (resumed where allowed)
    python tools/mirror_tiles.py extract porto-santo --work W           # ZIP members, ASCII grids, wide strips
    python tools/mirror_tiles.py cut porto-santo --work W --out M       # staging, tiles, then final (resumable)
    python tools/mirror_tiles.py verify porto-santo --work W --out M    # a final product against its inputs
    python tools/mirror_tiles.py status [dataset] --work W --out M      # final / cutting / ready / waiting
    python tools/mirror_tiles.py all porto-santo --inputs I --work W --out M   # download, cut, verify, clean

--out is the mirror (default: the environment's FINDALINE_MIRROR); --inputs the folder of placed files and of the
fetch tool's areas; --product one product only. One run at a time per --work and per product (locks in --work and in
<out>/.locks): a second run stops at once with Busy and a non-zero exit, touching nothing. `all` skips a product that
is final and verified on its index.json, cuts every product that is complete, and removes a product's unpacked and
copied rasters from --work once its verify passed. verify (of a final product only) checks every listed tile's
sha256, finds every file in the folder the index does not list, compares the tiles the inputs' own bounds touch with
the index's keys and the inputs with the journal's feeders, and compares sampled tiles (`--samples`, by default 1 %
of the tiles with data, at least 8, at most 500; `--seed`, recorded) with the inputs twice: re-assembled from
footprints read again, and POINTS pixels each read straight from the input rasters through their own transforms with
the masks applied apart (an averaged product's also up to EDGE_BLOCKS partly valid blocks and as many on a seam per
tile, found from the inputs; verify.json counts them). It judges against the inputs the cut read (inputs.jsonl): an
input that came later is no part of the edition (one line), a tile whose inputs are gone or changed is not checkable, never a failure. A verify
that compares no tile with data is "not checkable" (ok null; status: final, not verified), and keeps an earlier
passing verify.json of the same index.json. It writes verify.json beside the index.

In a container of the project's image (Linux). The image holds no tools/ (.dockerignore), so the clone's is mounted
too; the container runs as uid 10001 unless --user says otherwise, the mounted folders must be writable by that user,
and every run on one work folder must take the same user: the files another user wrote are read-only to the next:

    docker build -t findaline .
    docker run --rm --user "$(id -u):$(id -g)" --entrypoint python \\\\
        -v "$PWD/tools:/opt/findaline/tools:ro" -v "$PWD/downloads:/inputs:ro" \\\\
        -v "$PWD/work:/work" -v "$PWD/mirror:/mirror" \\\\
        findaline tools/mirror_tiles.py all porto-santo --inputs /inputs --work /work --out /mirror
    # one mount of a folder holding downloads/, work/ and mirror/ (and tools/ mounted as above) does the same:
    #   -v "$PWD:/srv" ... --inputs /srv/downloads --work /srv/work --out /srv/mirror
    # (with separate mounts the staging folder is <out>/.staging: a folder does not rename across mounts)

It makes no request but the declared downloads (cut, verify and status run with `--network none`).
"""

import argparse
import contextlib
import datetime
import errno
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
AVERAGE_BYTES_PER_PX = 24  # an averaged tile being assembled, per input pixel besides those: the float64 copy, the
                           # float64 values with 0 where invalid and the validity mask of _block_means
# A fetched file whose bytes are not those the fetch recorded
SHA_MISMATCH = ("its sha256 is not the one done.jsonl records: remove the file and its line from done.jsonl, then run "
                "the fetch tool (tools/cdd_fetch.py) again")
# Raised by hand whenever a change of this tool could change a cut's output: a tile journaled by another version is
# cut again (product_rule)
CUT_VERSION = 1
POINTS = 300           # verify: pixels of each sampled tile also read straight from the inputs
EDGE_BLOCKS = 50       # ... and of an averaged product at most so many partly valid blocks and so many on a seam
VERIFY_EPS = MAX_Z_ERROR + 1e-4  # LERC's bound and float32 rounding at heights of a few thousand metres
NAME = re.compile(r"^[a-z0-9_-]+$")
NOT_INPUTS = (".part", ".crdownload", ".tmp", ".new")

MADEIRA_CARD = """# Madeira: DTM 2 m (DROTe, 2018-2019) as 2 km tiles

Tiles of the digital terrain model **MDT 2 m** of Madeira island by the **Direção Regional do Ordenamento do
Território (DROTe), Região Autónoma da Madeira**, photogrammetric (UltraCam flights 2018-2019, RMSEz 0.145 m),
from https://irig-storage.madeira.gov.pt/irig-catalogo/MDT_2m.zip (SNIG record abba9a83: "No conditions apply",
https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/abba9a83-cb1c-4d2c-ad1d-ccb592247754).
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
Licence: CC BY 4.0 (https://metadati.partout.it/metadata_documents/CC_BY_DTM_v2.pdf). Source: the region's
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
class Fetched:
    """The files tools/cdd_fetch.py fetched into the folder `area` below --inputs (portugal, wallonia), the fetch
    tool's own files deciding what the product holds: with `collection`, every row of manifest.jsonl of that
    collection (Portugal); with `group`, every file of a fetch-list's group as status.json counts them (Wallonia's
    MNT or MNS). A file is an input when done.jsonl records it and it is on disk with the recorded size; its sha256
    is checked against done.jsonl when it is read. members: the raster members of each fetched file that is a ZIP."""
    area: str
    collection: Optional[str] = None
    group: Optional[str] = None
    members: Tuple[str, ...] = ()


Input = Union[Url, Placed, Fetched]


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
    card_changes: str = ""           # a change the card names besides the cut's own (a label replaced, a type)
    average: int = 1                 # the inputs' pixel is res / average; above 1 each pixel is the mean of the valid
                                     # input pixels of its average x average block (Wallonia: 0.5 m inputs, 1 m tiles)


def input_res(product: Product) -> float:
    """The inputs' pixel size: the product's own, or res / average for a product averaged from finer inputs (whose
    blocks never straddle two tiles: TILE_M is a whole number of output pixels from the origin)."""
    if not isinstance(product.average, int) or isinstance(product.average, bool) or product.average < 1:
        raise ValueError(f"{product.name}: average {product.average!r} is not a whole number of 1 or more")
    if product.average == 1:
        return product.res
    res = product.res / product.average
    if tile_px(res) != tile_px(product.res) * product.average:
        raise ValueError(f"{product.name}: {res:g} m input pixels do not make whole {product.res:g} m blocks of a tile")
    return res


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
    heading: str = ""     # the card's first line when it is not "<title> as 2 km tiles" (an approved row's title)


PORTO_SANTO_ZIP = Url("https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip", 114_126_877)
MADEIRA_5M_RECORD = ("https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/"
                     "abba9a83-cb1c-4d2c-ad1d-ccb592247754")
DROTE = "Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da Madeira"


def _island(name: str, island: str, member: str, crs: str, crs_name: str, nodata: Tuple[float, ...],
            sea: Optional[float], about: str, floor: Optional[float] = None, card_changes: str = "") -> Dataset:
    """One island of Madeira's 5 m ZIP as a dataset of its own (the SNIG record abba9a83)."""
    product = Product("dtm", 5.0, crs, (2.5, 2.5), (replace(PORTO_SANTO_ZIP, members=(member,)),),
                      f"MDT 5 m, {island} (DROTe, photogrammetry 2018-2019)", "as published (metres)",
                      nodata=nodata, sea=sea, floor=floor, card_changes=card_changes,
                      about=f"{member} of {PORTO_SANTO_ZIP.url} ({crs_name}); {about}")
    return Dataset(name, f"{island}: DTM 5 m (DROTe, 2018-2019)", DROTE, "No conditions apply (SNIG record abba9a83)",
                   f"DTM 5 m: {DROTE}, 2018-2019", (product,), record=MADEIRA_5M_RECORD, not_endorsed="DROTe")


# Wallonia: SPW's "Relief de la Wallonie" MNT and MNS 2021-2022 (lidar of 19/02/2021 to 05/03/2022, 0.5 m), five
# province ZIPs per model in EPSG:3812 fetched by tools/cdd_fetch.py fetch-list wallonia (the groups MNT and MNS).
# Inspected 2026-11-21: Deflate; one raster per ZIP (RELIEF_WALLONIE_MN{T,S}_50CM_2021_2022.tif), float32 in LZW
# full-width strips (a tiled copy in --work), AREA_OR_POINT=Point; pixel edges on whole half-metres (origin (0, 0));
# nodata -9999; the provinces are rectangles whose boxes overlap, nodata outside the province, their shared pixels
# equal (MNS Brabant wallon and Hainaut: 104 507 pixels valid in both, all identical), hence "agree". Cut at 1 m only,
# each pixel the mean of the valid 0.5 m pixels of its 2 x 2 block (the user's decision of 2026-11-22: "cut it to 1m
# resolution", "1 m only"). Licence CC BY 4.0; the credits verbatim from the records (2026-11-15; the MNS's also in
# its ATOM feed of 2026-11-21); the MNT's record asks the changes to be named ("mention explicite des modifications
# apportées à la donnée"): the card names every one
SPW = "Service public de Wallonie (SPW)"
WALLONIA_MNT_RECORD = "https://geoportail.wallonie.be/catalogue/a004e570-99d6-4fe5-b83d-49b774409278.html"
WALLONIA_MNS_RECORD = "https://geoportail.wallonie.be/catalogue/5a4c28fe-d30c-493e-861e-a80ebc703b64.html"
WALLONIA_CREDITS = (
    "Source : Service public de Wallonie (SPW) - Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022 "
    "(2024-01-23) https://geodata.wallonie.be/id/a004e570-99d6-4fe5-b83d-49b774409278",
    "Source : Service public de Wallonie (SPW) - Relief de la Wallonie - Modèle Numérique de Surface (MNS) 2021-2022 "
    "(2024-01-23) https://geodata.wallonie.be/id/5a4c28fe-d30c-493e-861e-a80ebc703b64")


def _wallonia(name: str, group: str, model: str, record: str) -> Product:
    """One model of SPW's 2021-2022 lidar: its five province ZIPs (0.5 m) averaged to 1 m."""
    return Product(name, 1.0, "EPSG:3812", (0.0, 0.0), (Fetched("wallonia", group=group, members=("*.tif",)),),
                   f"{model} 2021-2022 (SPW, lidar 2021-2022, 0.5 m), averaged to 1 m",
                   "Deuxième Nivellement Général (EPSG:5710)", nodata=(-9999.0,), overlap="agree", average=2,
                   about=f"the five province ZIPs of SPW's \"Relief de la Wallonie - {model} 2021-2022\" (record "
                         f"{record}), each one raster RELIEF_WALLONIE_{group}_50CM_2021_2022.tif of 0.5 m pixels in "
                         "ETRS89 / Belgian Lambert 2008 (EPSG:3812), lidar of 19/02/2021 to 05/03/2022")


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
                           "Porto Santo and its islets; the sea written as 0 there",
                           card_changes="the values, float64 in the file, stored as float32 (within those 5 mm)"),
    "desertas": _island("desertas", "Desertas", "Desertas_5m.tif", "EPSG:5016",
                        "PTRA08 / UTM zone 28N, EPSG:5016; the file is labelled EPSG:3061", (-32768.0, -999.0), None,
                        "Deserta Grande, Bugio and Ilhéu Chão", floor=-1.0,
                        card_changes="the file's reference-system label replaced: it is labelled EPSG:3061, its "
                                     "coordinates are in EPSG:5016 (PTRA08 / UTM zone 28N); nothing reprojected"),
    "selvagens": _island("selvagens", "Selvagens", "Selvagens_5m.tif", "EPSG:5016",
                         "PTRA08 / UTM zone 28N, EPSG:5016", (-32768.0, -999.0), None,
                         "Selvagem Grande, Selvagem Pequena and Ilhéu de Fora", floor=-1.0),
    "wallonia": Dataset(
        "wallonia", "Wallonia: MNT and MNS 2021-2022, lidar 2021-2022, 0.5 m (SPW), averaged to 1 m", SPW,
        "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)", "; ".join(WALLONIA_CREDITS),
        (_wallonia("dtm", "MNT", "Modèle Numérique de Terrain (MNT)", WALLONIA_MNT_RECORD),
         _wallonia("dsm", "MNS", "Modèle Numérique de Surface (MNS)", WALLONIA_MNS_RECORD)),
        record=WALLONIA_MNT_RECORD, not_endorsed="the Service public de Wallonie (SPW)",
        # the publishing row's title and not-endorsed sentence (the user's approval of 2026-11-22)
        heading="Wallonia: MNT and MNS 2021-2022, lidar 2021-2022, 0.5 m (SPW), averaged to 1 m, as 2 km tiles"),
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


def _on_wait(path: str):
    """Called when a download waits for another's lock (tests)."""


@contextlib.contextmanager
def _one_download(work: str):
    """Never two downloads at once, also from two processes on one work folder: the second waits."""
    from filelock import FileLock, Timeout
    os.makedirs(work, exist_ok=True)
    lock = FileLock(os.path.join(work, "download.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(f"waiting for another download in {work}", flush=True)
        _on_wait(lock.lock_file)
        lock.acquire()
    try:
        yield
    finally:
        lock.release()


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


# Write sites: every place the tool writes a file a stop could leave half done calls _site with its name, so a test
# can stop the run there (HOOK raises or ends the process) and check that the next run ends where an uninterrupted
# one does. A new write site gets a name here (tests/test_mirror_tiles.py runs every one)

WRITE_SITES = (
    "member.before_replace", "member.after_replace",     # a ZIP member unpacked into --work
    "copy.before_replace", "copy.after_replace",         # a tiled copy of an ASCII grid or of wide strips
    "tile.before_replace", "tile.after_replace",         # a tile in the staging folder
    "journal.before_line", "journal.after_line",         # the journal's line of a finished tile
    "inputs.before_replace", "inputs.after_replace",     # inputs.jsonl in the staging folder (the cut's inputs)
    "index.before_replace", "index.after_replace",       # index.json in the staging folder
    "rename.before", "rename.after",                     # the staging folder renamed into the mirror
    "card.before_replace", "card.after_replace",         # the dataset's card
    "verify.before_replace", "verify.after_replace",     # verify.json in a final product's folder
)
HOOK = None  # tests: a function of the site's name


def _site(name: str):
    assert name in WRITE_SITES, name
    if HOOK is not None:
        HOOK(name)


# Locks, folders and removals

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


def _below(path: str, root: str) -> bool:
    """Whether path is root or lies below it (symbolic links resolved)."""
    real, top = (os.path.normcase(os.path.realpath(p)) for p in (path, root))
    try:
        return real == top or os.path.commonpath([real, top]) == top
    except ValueError:  # another drive (Windows): not below
        return False


def check_folders(work: str, inputs: Optional[str], out: Optional[str]):
    """The tool's own files live only under --work (and <out>/.staging): --work may not be the inputs folder or lie
    inside it or inside --out, nor the inputs inside --work or --out, nor --out inside the inputs (ValueError)."""
    pairs = [("--work", work, "--out", out)]
    if inputs is not None:
        pairs += [("--work", work, "--inputs", inputs), ("--inputs", inputs, "--work", work),
                  ("--inputs", inputs, "--out", out), ("--out", out, "--inputs", inputs)]
    for a, path, b, root in pairs:
        if path is not None and root is not None and _below(path, root):
            raise ValueError(f"{a} {path} is or lies inside {b} {root}: keep the inputs, the work folder and the "
                             "mirror apart (the tool writes and removes files only in --work and the mirror)")


def _remove(path: str, *roots: str):
    """os.remove of a file the tool made: refused (ValueError) unless it lies below one of roots (--work, a
    staging folder). An input is never removed."""
    for root in roots:
        if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.realpath(root)) and \
                _below(path, root):
            os.remove(path)
            return
    raise ValueError(f"{path}: not below {', '.join(roots)}: the tool removes only files it made there")


def _drop_link(path: str, work: str):
    """A symbolic link someone put where the tool writes in --work: the link itself removed (never what it points
    to), so the tool's file takes its place."""
    if os.path.islink(path) and _below(os.path.dirname(os.path.abspath(path)), work):
        os.unlink(path)


def _fsync(path: str):
    with open(path, "rb+") as f:
        os.fsync(f.fileno())


def _fsync_dir(path: str):
    """A folder's entries to disk where the system allows it (not on Windows)."""
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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


_JSONL: Dict[str, Tuple[str, List[Dict]]] = {}  # read_jsonl's parsed files by path: (size and time, rows)


def read_jsonl(path: str) -> List[Dict]:
    """The JSON objects of a file of lines (none if it is missing); a line that is not UTF-8 or JSON (one torn by a
    stopped writer) is skipped with one log line naming its number, never its text. Parsed once while the file's
    size and time stay the same (a run reads the fetch tool's files several times)."""
    rows = []
    if not os.path.exists(path):
        return rows
    key, stamp = os.path.abspath(path), file_stamp(path)
    if _JSONL.get(key, (None,))[0] == stamp:
        return _JSONL[key][1]
    _JSONL[key] = (stamp, rows)
    with open(path, "rb") as f:
        for n, raw in enumerate(f, 1):
            try:
                line = raw.decode("utf-8").strip()
                if line:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
            except ValueError:
                print(f"{path}: line {n} is not UTF-8 or JSON (a writer stopped while writing it?): skipped",
                      flush=True)
    return rows


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
    """A cache of the files the tool itself made in --work (unpacked ZIP members, tiled copies), each with its source's
    stamp (<work>/state/work-files.sqlite): a copy is used only while its record matches its source, a copy without
    a record is made again, and clean removes only these files. Losing it only costs time."""

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

    def stamp(self, path: str) -> Optional[str]:
        row = self.db.execute("SELECT stamp FROM files WHERE path = ?", (self._key(path),)).fetchone()
        return row[0] if row else None

    def valid(self, path: str, stamp: Optional[str]) -> bool:
        """Whether path is a copy the tool made of a source of this stamp (None: any stamp), and still there."""
        found = self.stamp(path)
        return (found is not None and (stamp is None or found == stamp) and os.path.exists(path)
                and not os.path.islink(path))

    def record(self, path: str, kind: str, source: str, stamp: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO files (path, kind, source, stamp) VALUES (?, ?, ?, ?)",
                            (self._key(path), kind, source, stamp))

    def made(self, path: str) -> bool:
        row = self.db.execute("SELECT kind FROM files WHERE path = ?", (self._key(path),)).fetchone()
        return row is not None and row[0] != "checked"

    def check_archive(self, path: str, sha: str):
        """A fetched ZIP against its sha256 of done.jsonl, once per path, size and time (kept here as a checked
        file, kind "checked", which clean never removes)."""
        stamp = f"{file_stamp(path)}:{sha}"
        row = self.db.execute("SELECT stamp FROM files WHERE path = ? AND kind = 'checked'",
                              (self._key(path),)).fetchone()
        if row and row[0] == stamp:
            return
        if _sha256(path) != sha:
            raise ValueError(f"{path}: {SHA_MISMATCH}")
        self.record(path, "checked", path, stamp)

    def forget(self, path: str):
        with self.db:
            self.db.execute("DELETE FROM files WHERE path = ?", (self._key(path),))

    def close(self):
        self.db.close()


@dataclass
class Raster:
    """One raster of a product: id (stable: a file's path below --inputs or a ZIP member's), the file the tool reads
    (path: the input itself, or a member it unpacked into --work), its stamp (a member's CRC, a fetched file's
    sha256 of done.jsonl, else the file's size and time), the expected sha256 of a fetched file."""
    id: str
    path: str
    stamp: str
    sha256: Optional[str] = None


@dataclass
class Resolved:
    """A product's inputs as found now: the rasters ready to read, whether every input is there (then nothing more
    will come), what is missing (ids or patterns), counts per input for a person, and the archives whose members are
    still to be unpacked."""
    rasters: List[Raster] = field(default_factory=list)
    complete: bool = True
    missing: List[str] = field(default_factory=list)
    counts: List[str] = field(default_factory=list)
    unpack: List[Tuple[str, Tuple[str, ...]]] = field(default_factory=list)
    without: List[str] = field(default_factory=list)


def resolve(product: Product, work: str, inputs: Optional[str], files: Optional[WorkFiles] = None,
            without: Sequence[str] = ()) -> Resolved:
    """The product's inputs on disk now, in the order of its inputs. Complete when every input is there whole: every
    Url downloaded, every Placed pattern matched, every item of a Fetched area recorded and on disk with its size,
    but the ids `without` names (sheets the provider never delivered: each must be an item of the area and absent,
    else ValueError, so a typing mistake never drops data). Unpacked members are taken while their record matches."""
    own = files is None
    files = files or WorkFiles(work)
    out = Resolved()
    left = set(without)
    try:
        for spec in product.inputs:
            if isinstance(spec, Fetched):
                for path, rid, sha in _resolve_fetched(spec, inputs, out, left):
                    _add_file(out, files, work, spec.members, path, rid, f"sha256:{sha}", sha)
                continue
            path = zip_path(spec, work) if isinstance(spec, Url) else placed_path(spec, inputs)
            if isinstance(spec, Url) and not os.path.exists(path):  # a download is renamed only when whole
                target = member_path(work, path, spec.members[0], True) if _single(spec.members) else None
                if target and files.valid(target, None):  # the ZIP removed after its one member was unpacked
                    out.rasters.append(Raster(f"{os.path.basename(path)}!{spec.members[0]}", target,
                                              files.stamp(target)))
                    continue
                path = None
            if path is None:
                out.complete = False
                out.missing.append(spec.url if isinstance(spec, Url) else spec.pattern)
                continue
            rid = os.path.basename(path) if isinstance(spec, Url) else \
                os.path.relpath(path, inputs).replace(os.sep, "/")  # the path below --inputs (--work for a Url)
            _add_file(out, files, work, spec.members, path, rid, file_stamp(path), None)
    finally:
        if own:
            files.close()
    if left:
        raise ValueError(f"--without {' '.join(sorted(left))}: not an item of the product's fetched inputs")
    seen: Dict[str, str] = {}
    for raster in out.rasters:
        if raster.id in seen:
            raise ValueError(f"two rasters of one id {raster.id!r}: {seen[raster.id]} and {raster.path} (name the "
                             "inputs so each has its own path below --inputs)")
        seen[raster.id] = raster.path
    return out


def _add_file(out: Resolved, files: WorkFiles, work: str, members: Sequence[str], path: str, rid: str, stamp: str,
              sha: Optional[str]):
    """An input file as rasters: itself, or its ZIP members (taken while their unpacked copies match)."""
    if not members:
        out.rasters.append(Raster(rid, path, stamp, sha))
        return
    if sha is not None:
        files.check_archive(path, sha)
    with zipfile.ZipFile(path) as archive:
        pending = False
        for member in _member_names(archive, members):
            target = member_path(work, path, member, _single(members))
            mstamp = member_stamp(archive.getinfo(member))
            if files.valid(target, mstamp):
                out.rasters.append(Raster(f"{rid}!{member}", target, mstamp))
            else:
                pending = True
        if pending:
            out.unpack.append((path, tuple(members)))


def _resolve_fetched(spec: Fetched, inputs: Optional[str], out: Resolved, without: set):
    """(path, id, sha256) of every item of a fetch area that is there whole; what is missing into out."""
    if inputs is None:
        raise ValueError(f"{spec.area}: a fetched input needs --inputs")
    area = os.path.join(inputs, spec.area)
    done = {}
    for row in read_jsonl(os.path.join(area, "done.jsonl")):
        if row.get("id") and row.get("path") and row.get("sha256"):
            done[str(row["id"])] = row
    if spec.collection is not None:
        manifest = os.path.join(area, "manifest.jsonl")
        if not os.path.exists(manifest):
            out.complete = False
            out.missing.append(f"{spec.area}/manifest.jsonl (run the fetch tool's plan)")
            return []
        expected = [(str(r["id"]), f"{spec.collection}/{r.get('folder')}/{r['id']}.tif", r.get("size"),
                     r.get("version")) for r in read_jsonl(manifest) if r.get("collection") == spec.collection
                    and r.get("id")]
        total = len(expected)
    else:
        status_path = os.path.join(area, "status.json")
        groups = _load_json(status_path).get("groups", {}) if os.path.exists(status_path) else {}
        total = (groups.get(spec.group) or {}).get("files")
        expected = [(rid, row["path"], row.get("size"), None) for rid, row in done.items()
                    if row.get("group") == spec.group]
        if total is None:
            out.complete = False
            out.missing.append(f"{spec.area}/status.json names no group {spec.group} (run the fetch tool)")
            return []
    found, missing = [], []
    for rid, rel, size, version in expected:
        row = done.get(rid)
        path = os.path.join(area, *rel.split("/"))
        why = None  # why a recorded item is no input yet
        if row is not None:
            if version is not None and row.get("version") is not None and version != row.get("version"):
                why = "a newer version in the manifest"
            elif not os.path.isfile(path):
                why = "recorded, but its file is gone"
            elif os.path.getsize(path) != row.get("size") or (size is not None and size != row.get("size")):
                why = "size differs"
        whole = row is not None and why is None
        if rid in without:
            if whole:
                raise ValueError(f"--without {rid}: it is present in {spec.area} (a typing mistake must not drop "
                                 "data)")
            without.discard(rid)
            out.without.append(rid)
            continue
        if whole:
            found.append((path, f"{spec.area}/{rel}", row["sha256"]))
        else:
            missing.append(f"{rid} ({why})" if why else rid)
    if spec.collection is None:  # a list: the files not done yet have no id here, only a count
        short = total - len(found) - len(out.without)
        missing += [f"({short} more of the list not fetched yet)"] if short > 0 else []
    out.counts.append(f"{spec.area}/{spec.collection or spec.group}: {len(found)} of {total}"
                      + (f" ({len(out.without)} without)" if out.without else ""))
    if missing:
        out.complete = False
        out.missing += missing
    return found


def _load_json(path: str) -> Dict:
    with open(path, encoding="utf-8") as f:
        found = json.load(f)
    return found if isinstance(found, dict) else {}


# Extract

def extract(name: str, work: str, inputs: Optional[str] = None, product: Optional[str] = None,
            max_memory_gb: float = MAX_MEMORY_GB, without: Sequence[str] = ()) -> List[str]:
    """Every ZIP member of the dataset's inputs unpacked into work (through a .part), an ASCII grid and a raster of
    strips too wide for the bound copied into a tiled GeoTIFF; a member or copy is made again when its source changed
    (WorkFiles). The paths of the members."""
    ds = dataset(name)
    check_folders(work, inputs, None)
    paths = []
    with _work_lock(work):
        files = WorkFiles(work)
        try:
            for prod in _products(ds, product):
                paths += _extract_product(ds, prod, work, inputs, files, max_memory_gb, without)
        finally:
            files.close()
    return paths


def _extract_product(ds: "Dataset", prod: "Product", work: str, inputs: Optional[str], files: WorkFiles,
                     max_memory_gb: float, without: Sequence[str] = ()) -> List[str]:
    """The product's members unpacked and its copies made; its footprints scanned into the cache (each file opened
    once, then never again while it is unchanged)."""
    paths = []
    for spec in prod.inputs:
        if isinstance(spec, Fetched) or not spec.members:
            continue
        path = zip_path(spec, work) if isinstance(spec, Url) else placed_path(spec, inputs)
        if path is None or not os.path.exists(path):
            raise ValueError(f"{spec.url if isinstance(spec, Url) else spec.pattern}: not there yet (download it or "
                             "place it first)")
        with zipfile.ZipFile(path) as archive:
            for member in _member_names(archive, spec.members):
                paths.append(_unpack(archive, path, member, member_path(work, path, member, _single(spec.members)),
                                     work, files))
    for path, members in resolve(prod, work, inputs, files, without).unpack:  # fetched ZIPs
        with zipfile.ZipFile(path) as archive:
            for member in _member_names(archive, members):
                paths.append(_unpack(archive, path, member, member_path(work, path, member, _single(members)),
                                     work, files))
    r = resolve(prod, work, inputs, files, without)
    state = State(work, ds, prod)
    try:
        for raster in r.rasters:
            state.footprint(raster, prod, lambda r_=raster: readable(r_, work, input_res(prod), max_memory_gb, files,
                                                                     prod))
    finally:
        state.close()
    return paths


def _unpack(archive: zipfile.ZipFile, archive_path: str, member: str, path: str, work: str, files: WorkFiles) -> str:
    """member unpacked to path: zipfile for stored and Deflate members (its CRC checked), 7-Zip for the others
    (Deflate64; 7-Zip checks the CRC); kept while its record names the member's CRC and size."""
    info = archive.getinfo(member)
    stamp = member_stamp(info)
    if files.valid(path, stamp):
        print(f"{path}: already extracted ({info.file_size / 1e9:.2f} GB)")
        return path
    _drop_link(path, work)
    if not _below(path, work):
        raise ValueError(f"{path}: not below the work folder {work}: not written")
    made = None
    if not os.path.isdir(os.path.dirname(path)):
        made = os.path.dirname(path)
        os.makedirs(made)
    start, part = time.time(), path + ".part"
    _drop_link(part, work)
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
    _fsync(part)
    files.forget(path)
    _site("member.before_replace")
    os.replace(part, path)
    _site("member.after_replace")
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
    once."""
    own = files is None
    files = files or WorkFiles(work)
    try:
        path, copy = raster.path, _copy_path(raster.path, work)
        if files.valid(copy, raster.stamp):
            found = copy
        elif path.lower().endswith(".asc"):
            found = _record(files, _asc_copy(path, copy, max_memory_gb, work), path, raster.stamp)
        else:
            with rio.open(path) as src:
                block_h, block_w = src.block_shapes[0]
                cache_bytes, _ = _budget(max_memory_gb)
                band = tile_px(res) * src.width * np.dtype(src.dtypes[0]).itemsize  # one row of tiles' strips
                if block_w < src.width or band <= cache_bytes // 2:
                    return path if product is None else (path, _footprint_of(src, product, path))
            found = _record(files, _strip_copy(path, copy, max_memory_gb, work), path, raster.stamp)
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


def _put_copy(part: str, copy: str, work: str):
    """A finished copy put in place (its record follows)."""
    _fsync(part)
    _drop_link(copy, work)
    _site("copy.before_replace")
    _replace(part, copy)
    _site("copy.after_replace")


def _asc_copy(path: str, copy: str, max_memory_gb: float, work: str) -> str:
    """An ASCII grid copied into a tiled GeoTIFF of float32 (its values as read, its NODATA_value as the tag),
    in chunks of rows within the bound."""
    bands = AscBands(path, ())
    try:
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        rows = _rows_per_chunk(bands.width, 4, max_memory_gb)
        start, part = time.time(), copy + ".part"
        _drop_link(part, work)
        with rio.Env(GDAL_CACHEMAX=_budget(max_memory_gb)[0] >> 20), \
                rio.open(part, "w", width=bands.width, height=bands.height, count=1, dtype="float32",
                         transform=from_origin(bands.left, bands.top, bands.res, bands.res),
                         nodata=bands.file_nodata, **COPY_PROFILE) as dst:
            for r0 in range(0, bands.height, rows):
                r1 = min(r0 + rows, bands.height)
                dst.write(bands.raw_rows(r0, r1), 1, window=Window(0, r0, bands.width, r1 - r0))
        _put_copy(part, copy, work)
        print(f"{copy}: the ASCII grid as a tiled GeoTIFF in {(time.time() - start) / 60:.1f} min", flush=True)
        return copy
    finally:
        bands.close()


def _strip_copy(path: str, copy: str, max_memory_gb: float, work: str) -> str:
    """A raster of full-width strips copied into a tiled GeoTIFF (lossless, its own type and tags), in chunks of
    rows within the bound."""
    os.makedirs(os.path.dirname(copy), exist_ok=True)
    start, part = time.time(), copy + ".part"
    _drop_link(part, work)
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
    _put_copy(part, copy, work)
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
    res, (ox, oy) = input_res(product), product.origin
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
    (ox, oy), res = product.origin, input_res(product)
    right, bottom = fp.left + fp.width * res, fp.top - fp.height * res
    rows = range(math.ceil((fp.top - oy) / TILE_M) - 1, math.floor((bottom - oy) / TILE_M) - 1, -1)
    cols = range(math.floor((fp.left - ox) / TILE_M), math.ceil((right - ox) / TILE_M))
    return rows, cols


# A cache of the rasters' footprints and checked files

STATE_BATCH = 1000  # rasters written to the cache per transaction (a first scan of 180 000 files)


class State:
    """<work>/state/<dataset>.<product>.sqlite, a cache: each raster's footprint (by id, stamp and grid) and whether
    its sha256 was checked. Losing it only costs time (every file opened again)."""

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
        self.known = {rid: (stamp, fp, checked) for rid, stamp, fp, checked in
                      self.db.execute("SELECT id, stamp, footprint, checked FROM rasters")}

    @staticmethod
    def _stamp(raster: Raster, product: Product) -> str:
        # the file's size and time, and the grid it was placed on (another origin is checked again; an averaged
        # product's footprints are on its inputs' pixels)
        return f"{file_stamp(raster.path)}:{product.res:g}:{product.origin[0]:g}:{product.origin[1]:g}" + \
            (f":x{product.average}" if product.average != 1 else "")

    def cached(self, raster: Raster, product: Product) -> Optional[Footprint]:
        row = self.known.get(raster.id)
        if row and row[0] == self._stamp(raster, product):
            fp = Footprint(**json.loads(row[1]))
            if os.path.exists(fp.path):
                return fp
        return None

    def footprint(self, raster: Raster, product: Product, read_path) -> Footprint:
        """The raster's footprint: from the cache while the file and the grid are the same and the file it is read
        from is there, else read (read_path(): (the file to read, made when missing, and its footprint))."""
        fp = self.cached(raster, product)
        if fp is not None:
            return fp
        stamp = self._stamp(raster, product)
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
        """A fetched file against its sha256 of done.jsonl, once (the result kept with its size and time); a
        mismatch is an error naming the file (the fetch's to fetch again)."""
        if raster.sha256 is None:
            return
        stamp = self._stamp(raster, product)
        row = self.known.get(raster.id)
        if row and row[0] == stamp and row[2]:
            return
        if _sha256(raster.path) != raster.sha256:
            raise ValueError(f"{raster.path}: {SHA_MISMATCH}")
        self.flush()
        with self.lock, self.db:
            self.db.execute("UPDATE rasters SET checked = 1 WHERE id = ? AND stamp = ?", (raster.id, stamp))
        if raster.id in self.known:
            self.known[raster.id] = (self.known[raster.id][0], self.known[raster.id][1], 1)

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


def _write(path: str, tile: np.ndarray, crs: str, transform):
    """A tile in the mirror's profile (sk_tiles._write, into <path>.new), synced, then put in place."""
    sk_tiles._write(path + ".new", tile, crs, transform)
    _fsync(path + ".new")
    _site("tile.before_replace")
    _replace(path + ".new", path)
    _site("tile.after_replace")


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


def assemble(key: Tuple[int, int], product: Product, footprints: Sequence[Tuple[str, Footprint]],
             handles: Dict[str, "rio.DatasetReader"]) -> np.ndarray:
    """Tile (i, j) from every footprint covering it, in their order, by the product's overlap rule; NaN for no data.
    An averaged product's tile is put together on the inputs' pixels (the masks and the overlap rule on those), then
    each pixel is the mean of the valid input pixels of its block (_block_means, in float64; NaN where none)."""
    i, j = key
    res, (ox, oy) = input_res(product), product.origin
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
    if product.average != 1:
        from sources.readers.download import _block_means  # the project's rule of averaged tiles (sk_tiles.average)
        return _block_means(tile.astype(np.float64), product.average).astype(np.float32)
    return tile


@dataclass
class Plan:
    """A product's rasters on the tile grid: the footprints in input order, the rows and columns of its extent, the
    raster indexes covering each tile, the rasters by id."""
    footprints: List[Tuple[str, Footprint]]
    rows: range
    cols: range
    covering: Dict[Tuple[int, int], List[int]]
    input_crs: Dict[str, List[str]]
    rasters: Dict[str, Raster] = field(default_factory=dict)

    def keys(self) -> List[str]:
        """Every tile of the extent, rows from the top, columns from the west."""
        return [f"{i}_{j}" for j in self.rows for i in self.cols]


def plan(product: Product, rasters: Sequence[Raster], work: str, state: State,
         max_memory_gb: float = MAX_MEMORY_GB, files: Optional[WorkFiles] = None) -> Plan:
    """Where the rasters lie on the product's grid (the footprints from the cache, a file opened only when it is new
    or changed)."""
    own = files is None
    files = files or WorkFiles(work)
    try:
        footprints, input_crs = [], {}
        for raster in rasters:
            fp = state.footprint(raster, product,
                                 lambda r=raster: readable(r, work, input_res(product), max_memory_gb, files, product))
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
    by_id = {r.id: r for r in rasters}
    if not footprints:
        return Plan([], range(0), range(0), {}, input_crs, by_id)
    return Plan(footprints, range(top, bottom - 1, -1), range(left, right + 1), covering, input_crs, by_id)


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


def _folder(out: str, ds: Dataset, product: Product) -> str:
    """The product's final folder in the mirror: it exists only once the product is whole."""
    return os.path.join(out, *tile_folder(ds, product).split("/"))


def _load_index(path: str) -> Dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"tiles": {}}


def final_state(out: str, ds: Dataset, product: Product) -> Optional[str]:
    """"final" when the product's folder is in the mirror with its index.json; "before" for a folder an earlier
    version of this tool left unfinished (an index saying "partial", or none); None when there is no folder."""
    folder = _folder(out, ds, product)
    if not os.path.isdir(folder):
        return None
    index = os.path.join(folder, "index.json")
    return "final" if os.path.exists(index) and not _load_index(index).get("partial") else "before"


def _workers(product: Product, threads: int, max_memory_gb: float) -> Tuple[int, int]:
    """(tiles written at once, GDAL's cache in MB) within the bound; ValueError when not one tile fits. The tiles in
    flight hold their output pixels; the one being assembled holds its inputs' pixels (an averaged product's: average²
    of them per output pixel, and the float64 copy and sum of the mean, AVERAGE_BYTES_PER_PX more each)."""
    cache_bytes, left = _budget(max_memory_gb)
    per_tile = tile_px(product.res) ** 2 * TILE_BYTES_PER_PX
    assembling = per_tile if product.average == 1 else \
        tile_px(input_res(product)) ** 2 * (TILE_BYTES_PER_PX + AVERAGE_BYTES_PER_PX)
    workers = min(max(1, threads), (left - assembling) // per_tile)
    if workers < 1:
        raise ValueError(f"--max-memory-gb {max_memory_gb:g}: too little for one tile of {product.res:g} m "
                         f"({(per_tile + assembling) / 1e9:.2f} GB beside GDAL's cache of {cache_bytes / 1e9:.2f} GB "
                         f"and {BASE_MB} MB of base)")
    return int(workers), cache_bytes >> 20


# The journal and the staging folder

INPUTS_FILE = "inputs.jsonl"  # in a final folder: {"id", "stamp"} of every raster the cut read, in their order


def journal_path(work: str, ds: Dataset, product: Product, out: str) -> str:
    """<work>/journals/<dataset>.<product>.<res>m-<the mirror's>.jsonl: one line per finished tile, kept after the
    product is final (verify reads it); one per mirror folder, so a new edition cut into a fresh --out has its own."""
    mirror = hashlib.sha1(os.path.normcase(os.path.abspath(out)).encode("utf-8")).hexdigest()[:8]
    return os.path.join(work, "journals", f"{ds.name}.{product.name}.{product.res:g}m-{mirror}.jsonl")


def product_rule(product: Product) -> str:
    """What a tile's values depend on besides its rasters (the grid, the CRS, the masks, the overlap rule, the
    encoding): a tile journaled under another rule is cut again."""
    rule = [product.res, product.crs, list(product.origin), list(product.nodata), product.sea, product.floor,
            product.overlap, TILE_M, MAX_Z_ERROR, CUT_VERSION]
    if product.average != 1:  # the products of before keep their rule (and their journals)
        rule.append(["average", product.average])
    return hashlib.sha1(json.dumps(rule).encode("utf-8")).hexdigest()[:16]


def read_journal(path: str) -> Dict[str, Dict]:
    """{tile key: its last line} ({"key", "sha256" (None: no data), "fed": {raster id: stamp}}); a torn or foreign line
    is ignored."""
    found = {}
    if not os.path.exists(path):
        return found
    with open(path, "rb") as f:
        for raw in f:
            try:
                row = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("key"), str) and isinstance(row.get("fed"), dict):
                found[row["key"]] = row
    return found


class Journal:
    """The journal appended to: a line after the tile's file is in place and synced, the line synced too."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        if os.path.exists(path) and os.path.getsize(path):
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                torn = f.read(1) != b"\n"
            if torn:  # a line cut by a stop: the next one starts on its own line
                with open(path, "ab") as f:
                    f.write(b"\n")

    def append(self, key: str, sha: Optional[str], fed: Dict[str, str], rule: str, order: List[str]):
        _site("journal.before_line")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "sha256": sha, "fed": fed, "order": order, "rule": rule},
                               sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        _site("journal.after_line")


def staging_folder(work: str, out: str, ds: Dataset, product: Product) -> Tuple[str, str]:
    """(the staging folder of a product, why there): <work>/staging/... when a folder renames from --work into --out
    (tried with an empty folder), else <out>/.staging/... (another filesystem, or another mount in a container); never
    <out>/<dataset>/..., where a reader would take it for the dataset."""
    rel = os.path.join(ds.name, product.name, f"{product.res:g}m")
    in_work = os.path.join(work, "staging", rel)
    os.makedirs(os.path.join(work, "staging"), exist_ok=True)
    os.makedirs(out, exist_ok=True)
    name = f".probe-{ds.name}.{product.name}.{product.res:g}m"  # under the product's lock: one at a time
    probe, target = os.path.join(work, "staging", name), os.path.join(out, name)
    for left in (probe, target):  # a stop between the two lines below left it
        if os.path.isdir(left):
            os.rmdir(left)
    os.makedirs(probe, exist_ok=True)
    try:
        os.replace(probe, target)
        os.rmdir(target)
        return in_work, "in --work (it renames into --out)"
    except OSError:
        if os.path.isdir(probe):
            os.rmdir(probe)
        return os.path.join(out, ".staging", rel), "in <out>/.staging (--work does not rename into --out: " \
            "another filesystem or mount)"


def cut(name: str, work: str, out: str, rows_limit: Optional[int] = None, inputs: Optional[str] = None,
        product: Optional[str] = None, threads: int = THREADS, max_memory_gb: float = MAX_MEMORY_GB,
        without: Sequence[str] = ()) -> Dict:
    """Cut every product of the dataset (or the one named) that is complete and not final yet (see the module's
    docstring); rows_limit stops after that many rows of tiles to cut (a trial: the staging folder stays). The state of
    each product by name: "final" (it was), "cut" (made final now), "waiting" (inputs missing), "stopped" (the
    trial), "before" (a folder of an earlier version of the tool)."""
    ds = dataset(name)
    check_names(ds)
    check_folders(work, inputs, out)
    states = {}
    with _work_lock(work):
        for prod in _products(ds, product):
            states[prod.name] = _cut_product(ds, prod, work, out, rows_limit, inputs, threads, max_memory_gb,
                                             without)
    return states


def _cut_product(ds: Dataset, product: Product, work: str, out: str, rows_limit: Optional[int],
                 inputs: Optional[str], threads: int, max_memory_gb: float, without: Sequence[str]) -> str:
    where = tile_folder(ds, product)
    state_now = final_state(out, ds, product)
    if state_now == "final":
        print(f"{where}: final; nothing is cut again (changed, added or removed inputs make a new edition: a fresh "
              "--out or a new dataset name)", flush=True)
        _card_if_needed(ds, out)
        return "final"
    if state_now == "before":
        print(f"{where}: a folder an earlier version of this tool left unfinished: move it away, then cut again",
              flush=True)
        return "before"
    files = WorkFiles(work)
    try:
        r = resolve(product, work, inputs, files, without)
        if not r.complete:
            shown = r.missing[:20]
            print(f"waiting: {where}: {'; '.join(r.counts) or 'inputs missing'}; missing "
                  f"{', '.join(shown)}{' and more' if len(r.missing) > 20 else ''}", flush=True)
            return "waiting"
        if r.unpack:
            _extract_product(ds, product, work, inputs, files, max_memory_gb, without)
            r = resolve(product, work, inputs, files, without)
        if r.unpack:
            raise ValueError(f"{where}: members still to unpack: {r.unpack[:3]}")
        with _product_lock(out, ds, product):  # only now is anything written under --out
            if final_state(out, ds, product) is not None:
                print(f"{where}: made final meanwhile by another run", flush=True)
                return "final"
            staging, why = staging_folder(work, out, ds, product)
            print(f"{where}: staging {why}: {staging}", flush=True)
            return _cut_staged(ds, product, work, out, staging, r, rows_limit, threads, max_memory_gb, files)
    finally:
        files.close()


def _cut_staged(ds: Dataset, product: Product, work: str, out: str, staging: str, r: Resolved,
                rows_limit: Optional[int], threads: int, max_memory_gb: float, files: WorkFiles) -> str:
    """The cut in the staging folder: tiles kept when their file's sha256 is their journal line's and the rasters
    that fed them are the same; every other tile cut (again); then the product made final."""
    where = tile_folder(ds, product)
    workers, cache_mb = _workers(product, threads, max_memory_gb)
    state = State(work, ds, product)
    start, cut_rows = time.time(), 0
    jpath = journal_path(work, ds, product, out)
    rule = product_rule(product)
    try:
        with rio.Env(GDAL_CACHEMAX=cache_mb, GDAL_NUM_THREADS=str(max(1, threads))):
            p = plan(product, r.rasters, work, state, max_memory_gb, files)
            if not p.footprints:
                raise ValueError(f"{where}: complete but without a raster")
            ids = [rid for rid, _ in p.footprints]
            stamps = {rid: p.rasters[rid].stamp for rid in ids}
            journal = read_journal(jpath)
            os.makedirs(staging, exist_ok=True)
            done: Dict[str, Optional[str]] = {}
            to_hash = []
            for key in p.keys():
                i, j = map(int, key.split("_"))
                line = journal.get(key)
                fed = {ids[n]: stamps[ids[n]] for n in p.covering.get((i, j), [])}
                order = [ids[n] for n in p.covering.get((i, j), [])]
                if not line or line["fed"] != fed or line.get("order") != order or line.get("rule") != rule:
                    continue
                path = os.path.join(staging, *tile_name(i, j).split("/"))
                if line["sha256"] is None and not os.path.exists(path):
                    done[key] = None
                elif line["sha256"] is not None and os.path.exists(path):
                    to_hash.append((key, path, line["sha256"]))
            with ThreadPoolExecutor(max_workers=max(1, threads)) as hashing:  # a restart's cost: hashing kept tiles
                for (key, _, sha), found in zip(to_hash, hashing.map(lambda t: _sha256(t[1]), to_hash)):
                    if found == sha:
                        done[key] = sha
            _clear_staging(staging, {os.path.normcase(os.path.join(staging, *tile_name(*map(int, k.split("_")))
                                                                   .split("/"))) for k, v in done.items() if v})
            todo = [k for k in p.keys() if k not in done]
            px = tile_px(product.res)
            print(f"{where}: {len(p.footprints)} raster(s), {len(p.rows)} x {len(p.cols)} tiles of {px} px, "
                  f"{len(done)} kept from before, {len(todo)} to cut, {workers} at a time, GDAL's cache {cache_mb} MB",
                  flush=True)
            for label, which in p.input_crs.items():
                print(f"  {len(which)} raster(s) labelled {label}: read as {product.crs}", flush=True)
            jr = Journal(jpath)
            last_row: Dict[str, int] = {}
            for _, fp in p.footprints:
                last_row[fp.path] = min(last_row.get(fp.path, 1 << 30), tiles_of(fp, product)[0][-1])
            handles: Dict[str, "rio.DatasetReader"] = {}
            checked = set()
            todo_set = set(todo)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                try:
                    for n, j in enumerate(p.rows):
                        row = [i for i in p.cols if f"{i}_{j}" in todo_set]
                        if not row:
                            continue
                        if rows_limit is not None and cut_rows >= rows_limit:
                            break
                        cut_rows += 1
                        pending, results = deque(), {}
                        for i in row:
                            fps = [p.footprints[k] for k in p.covering.get((i, j), [])]
                            for rid, fp in fps:
                                if rid not in checked:
                                    state.check(p.rasters[rid], product)
                                    checked.add(rid)
                                if fp.path not in handles:
                                    handles[fp.path] = rio.open(fp.path)
                            tile = assemble((i, j), product, fps, handles) if fps else None
                            pending.append((i, pool.submit(_save_tile, staging, product, i, j, tile)))
                            while len(pending) > workers:
                                ii, fut = pending.popleft()
                                results[ii] = fut.result()
                        while pending:
                            ii, fut = pending.popleft()
                            results[ii] = fut.result()
                        for i in sorted(results):
                            key = f"{i}_{j}"
                            cover = p.covering.get((i, j), [])
                            jr.append(key, results[i], {ids[k]: stamps[ids[k]] for k in cover}, rule,
                                      [ids[k] for k in cover])
                            done[key] = results[i]
                        for path in [path for path in handles if last_row[path] >= j]:
                            handles.pop(path).close()
                        print(f"  row {n + 1}/{len(p.rows)}: {sum(v is not None for v in done.values())} tiles with "
                              f"data, {(time.time() - start) / 60:.1f} min", flush=True)
                finally:
                    for h in handles.values():
                        h.close()
    finally:
        state.close()
    if any(k not in done for k in p.keys()):
        print(f"{where}: stopped after {cut_rows} row(s) (a trial): {len(done)} of {len(p.keys())} tiles in the "
              f"staging folder {staging}", flush=True)
        return "stopped"
    _finalize(ds, product, out, staging, p, r, done)
    tiles = sum(v is not None for v in done.values())
    print(f"{_folder(out, ds, product)}: final, {tiles} tiles with data of {len(done)}, "
          f"{(time.time() - start) / 60:.1f} min", flush=True)
    return "cut"


def _clear_staging(staging: str, keep: set):
    """Every file of the staging folder but the tiles kept: a stopped run's .new and .part, tiles not in the
    journal, an index.json of a finalization that did not end (all made again)."""
    for root, _, names in os.walk(staging):
        for name in names:
            path = os.path.join(root, name)
            if os.path.normcase(path) not in keep:
                _remove(path, staging)


def _save_tile(folder: str, product: Product, i: int, j: int, tile: Optional[np.ndarray]) -> Optional[str]:
    """A tile written into the staging folder and synced (its sha256), or None when it holds no data."""
    if tile is None or not np.isfinite(tile).any():
        return None
    (ox, oy), res = product.origin, product.res
    path = os.path.join(folder, *tile_name(i, j).split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, np.ascontiguousarray(tile), product.crs, from_origin(ox + i * TILE_M, oy + (j + 1) * TILE_M, res, res))
    return _sha256(path)


def _index(ds: Dataset, product: Product, p: Plan, r: Resolved, done: Dict[str, Optional[str]]) -> Dict:
    """The product's index.json: every tile of the extent (rows from the top) with its sha256 (null: no data), then
    the keys of 2026-11-15 in their order and a newer dataset's additions after them."""
    urls = [spec.url for spec in product.inputs if isinstance(spec, Url)]
    source = urls[0] if ds.legacy else "; ".join(
        spec.url if isinstance(spec, Url) else spec.pattern if isinstance(spec, Placed)
        else f"{spec.area}/{spec.collection or spec.group}" for spec in product.inputs)
    index = {"tiles": {k: done[k] for k in p.keys()}}
    index.update(dataset=ds.key if ds.legacy else ds.name, product=product.name,
                 title=product.title, source=source, crs=product.crs, heights=product.heights, tile_m=TILE_M,
                 resolution=product.res, origin=list(product.origin), block=BLOCK,
                 encoding=f"COG LERC_ZSTD, max_z_error {MAX_Z_ERROR} m", licence=ds.licence,
                 attribution=ds.attribution, created=datetime.date.today().isoformat())
    if ds.legacy:
        return index
    masks = {"nodata": list(product.nodata) + ["the files' own"]}
    if product.sea is not None:
        masks["sea"] = product.sea
    if product.floor is not None:
        masks["below"] = product.floor
    index.update(inputs=len(p.footprints), overlap=product.overlap, masks=masks)
    if product.average != 1:  # each pixel the mean of the valid input pixels of its average x average block
        index.update(average=product.average, input_resolution=input_res(product))
    if p.input_crs:
        index["input_crs"] = {label: (ids if len(ids) <= 20 else ids[:20] + [f"... {len(ids) - 20} more"])
                              for label, ids in p.input_crs.items()}
    if r.without:
        index["missing_inputs"] = sorted(r.without)
    return index


def _finalize(ds: Dataset, product: Product, out: str, staging: str, p: Plan, r: Resolved,
              done: Dict[str, Optional[str]]):
    """index.json written into the staging folder, the folder synced and renamed into the mirror in one step, then
    the dataset's card written whole."""
    if not ds.legacy:  # the inputs this edition was cut from, for verify (the datasets of before keep their layout)
        path = os.path.join(staging, INPUTS_FILE)
        with open(path + ".part", "w", encoding="utf-8", newline="\n") as f:
            for raster in r.rasters:
                f.write(json.dumps({"id": raster.id, "stamp": raster.stamp}, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        _site("inputs.before_replace")
        _replace(path + ".part", path)
        _site("inputs.after_replace")
    path = os.path.join(staging, "index.json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(_index(ds, product, p, r, done), f)
        f.flush()
        os.fsync(f.fileno())
    _site("index.before_replace")
    _replace(path + ".part", path)
    _site("index.after_replace")
    _fsync_dir(staging)
    folder = _folder(out, ds, product)
    os.makedirs(os.path.dirname(folder), exist_ok=True)
    _site("rename.before")
    try:
        _replace(staging, folder)
    except OSError as e:
        if e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17:  # ERROR_NOT_SAME_DEVICE
            raise ValueError(f"the staging folder {staging} does not rename into {folder} (another filesystem: "
                             f"{os.path.dirname(folder)} is linked or mounted elsewhere than {out}): make it a plain "
                             "folder of --out's filesystem, or cut into an --out on that filesystem; the staging "
                             "folder is kept") from e
        raise
    _site("rename.after")
    _fsync_dir(os.path.dirname(folder))
    parent = os.path.dirname(staging)  # empty folders a staging in <out>/.staging leaves
    while os.path.basename(parent) and os.path.isdir(parent) and not os.listdir(parent) and \
            os.path.basename(parent) != "staging" and os.path.basename(parent) != ".staging":
        os.rmdir(parent)
        parent = os.path.dirname(parent)
    write_card(ds, out)


# The dataset card

def card_text(ds: Dataset, out: Optional[str] = None) -> str:
    """The dataset card: a dataset's published text of before while it has its one product, else made from its
    record, every product with the changes made to it (and, read from its final index in out, the inputs it was cut
    without)."""
    if ds.card is not None:
        if len(ds.products) != 1:
            raise ValueError(f"{ds.name}: a fixed card describes one product; with more the card is generated "
                             "(remove card=)")
        return ds.card
    lines = [f"# {ds.heading or ds.title + ' as 2 km tiles'}", ""]
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
        joined = len(product.inputs) > 1 or any(isinstance(s, Fetched) or len(s.members) > 1 for s in product.inputs)
        rule = ("the first listed wins where they overlap" if product.overlap == "first" else
                "where they overlap they agree within 5 mm")
        missing = []
        if out is not None and final_state(out, ds, product) == "final":
            missing = _load_index(os.path.join(_folder(out, ds, product), "index.json")).get("missing_inputs", [])
        lines += [f"## `{folder}`: {product.title}", ""]
        if product.about:
            lines += [f"Source: {product.about}.", ""]
        fine = input_res(product)
        mean = (f"each {product.res:g} m pixel is the mean of the valid {fine:g} m pixels of its {product.average} x "
                f"{product.average} block (a block without one is no data); " if product.average != 1 else "")
        grid = (f"its own {product.res:g} m pixel grid" if product.average == 1 else
                f"a {product.res:g} m pixel grid on the edges of the {fine:g} m pixels")
        lines += [f"Changes made: {mean}cut into 2 km x 2 km Cloud Optimized GeoTIFFs on {grid} "
                  f"in {product.crs} (tile (i, j) starts at x = 2000 i + {ox:g}, y = 2000 j + {oy:g})"
                  + (f", the inputs joined where they meet ({rule})" if joined else "")
                  + f"; {', '.join(masks[:-1]) + ' and ' + masks[-1] if len(masks) > 1 else masks[0]} made no "
                  + ("data" if product.average == 1 else f"data (on the {fine:g} m pixels, before the mean)")
                  + "; stored with LERC compression with a maximum error of "
                  "5 mm" + (f"; {product.card_changes}" if product.card_changes else "")
                  + f". Heights {product.heights}; values are not otherwise changed."
                  + (f" Cut without {len(missing)} sheets the provider did not deliver: {', '.join(missing)}."
                     if missing else ""), ""]
    lines += [f"Layout: `<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif`; `<product>/<res>m/index.json` lists every "
              "tile of the extent with its sha256 (null: no data). Made for Find-a-Line (a highline finder); not "
              f"endorsed by {ds.not_endorsed or ds.provider}.", ""]
    return "\n".join(lines)


def _card_path(ds: Dataset, out: str) -> str:
    return os.path.join(out, ds.name, "README.md")


def write_card(ds: Dataset, out: str):
    """README.md beside the products, written whole (unless it is already that text)."""
    path = _card_path(ds, out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = card_text(ds, out)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    with open(path + ".part", "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    _site("card.before_replace")
    _replace(path + ".part", path)
    _site("card.after_replace")


def _card_if_needed(ds: Dataset, out: str):
    """The card of a dataset with a final product, when a stop after the rename left it missing or of before."""
    path = _card_path(ds, out)
    text = card_text(ds, out)
    if not os.path.exists(path):
        write_card(ds, out)
        return
    with open(path, encoding="utf-8") as f:
        same = f.read() == text
    if not same:  # closed first: Windows refuses to replace a file that is still open
        write_card(ds, out)


# Verify

def default_samples(tiles: int) -> int:
    """Tiles with data compared with the inputs: 1 % of them, at least 8 and at most 500."""
    return max(8, min(500, tiles // 100))


def verify(name: str, work: str, out: str, inputs: Optional[str] = None, product: Optional[str] = None,
           samples: Optional[int] = None, seed: int = 0, max_memory_gb: float = MAX_MEMORY_GB,
           points: int = POINTS) -> Dict:
    """Each final product's tiles against its inputs (see the module's docstring): {product: result}; each result
    written to verify.json beside the index. ok False on any failure, None for a product that is not final."""
    ds = dataset(name)
    check_folders(work, inputs, out)
    results = {}
    with _work_lock(work):
        for prod in _products(ds, product):
            if final_state(out, ds, prod) != "final":
                results[prod.name] = _verify_product(ds, prod, work, out, inputs, samples, seed, max_memory_gb,
                                                     points)  # "not final": nothing written, no lock
                continue
            with _product_lock(out, ds, prod):
                results[prod.name] = _verify_product(ds, prod, work, out, inputs, samples, seed, max_memory_gb,
                                                     points)
    return results


def _own_reading(paths: Sequence[Tuple[str, str]], product: Product) -> Dict[str, Tuple[Tuple, Footprint]]:
    """{raster id: ((left, bottom, right, top), footprint)} read from each raster's own file once (not from the cut's
    cache)."""
    found = {}
    for rid, path in paths:
        with rio.open(path) as src:
            found[rid] = (tuple(src.bounds), _footprint_of(src, product, path))
    return found


def _input_masks(src, product: Product, values: np.ndarray) -> np.ndarray:
    """The valid input pixels of values read from src, masked by these few lines (not mask()): finite, none of the
    product's nodata, the file's own and the sea's value, not below the floor."""
    bad = ~np.isfinite(values)
    for value in list(product.nodata) + [src.nodata, product.sea]:
        if value is not None and not np.isnan(value):
            bad |= values.astype(np.float32) == np.float32(value)
    if product.floor is not None:
        with np.errstate(invalid="ignore"):
            bad |= values < product.floor
    return ~bad


def _edge_blocks(key: str, product: Product, readers: Sequence[Tuple[str, str, Tuple]], rng: random.Random,
                 handles: Dict[str, "rio.DatasetReader"], most: int = EDGE_BLOCKS) -> Tuple[Tuple, Dict[str, int]]:
    """An averaged product's blocks of a tile where its mean can go wrong, found from the input rasters themselves
    (each read through its own transform, masked apart): partly valid (1 to average² - 1 valid input pixels) and on a
    seam (an input pixel valid in two rasters). At most `most` of each kind, chosen by rng. ((rows, cols) of the chosen
    blocks on the tile's pixels, {"partial_found", "partial_chosen", "seam_found", "seam_chosen"})."""
    i, j = map(int, key.split("_"))
    a, fine, (ox, oy) = product.average, input_res(product), product.origin
    n = tile_px(fine)
    left, top = ox + i * TILE_M, oy + (j + 1) * TILE_M
    valid_any = np.zeros((n, n), dtype=bool)
    valid_count = np.zeros((n, n), dtype=np.uint8)
    for _, path, (b_left, b_bottom, b_right, b_top) in readers:
        if b_right <= left or b_left >= left + TILE_M or b_top <= top - TILE_M or b_bottom >= top:
            continue
        if path not in handles:
            handles[path] = rio.open(path)
        src = handles[path]
        c0 = int(np.floor((left - src.transform.c) / src.transform.a + 0.5))
        r0 = int(np.floor((src.transform.f - top) / -src.transform.e + 0.5))
        r_in, r_end, c_in, c_end = max(r0, 0), min(r0 + n, src.height), max(c0, 0), min(c0 + n, src.width)
        if r_in >= r_end or c_in >= c_end:
            continue
        ok = _input_masks(src, product, src.read(1, window=Window(c_in, r_in, c_end - c_in, r_end - r_in)))
        valid_any[r_in - r0:r_end - r0, c_in - c0:c_end - c0] |= ok
        valid_count[r_in - r0:r_end - r0, c_in - c0:c_end - c0] += ok.astype(np.uint8)
    per_block = valid_any.reshape(n // a, a, n // a, a).sum(axis=(1, 3))
    seam = (valid_count >= 2).reshape(n // a, a, n // a, a).any(axis=(1, 3))
    rows, cols, counts = [], [], {}
    for kind, where in (("partial", (per_block > 0) & (per_block < a * a)), ("seam", seam)):
        found = list(zip(*np.nonzero(where)))
        chosen = sorted(rng.sample(found, min(most, len(found))))
        rows += [r for r, _ in chosen]
        cols += [c for _, c in chosen]
        counts[f"{kind}_found"], counts[f"{kind}_chosen"] = len(found), len(chosen)
    return (np.array(rows, dtype=int), np.array(cols, dtype=int)), counts


def _point_problems(key: str, got: np.ndarray, product: Product, readers: Sequence[Tuple[str, str, Tuple]],
                    rng: random.Random, n: int, handles: Dict[str, "rio.DatasetReader"],
                    extra: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> Tuple[List[str], int]:
    """A check apart from the cut's own reading: n random pixels of a tile (and the pixels of extra, (rows, cols):
    an averaged product's edge blocks), their centres' coordinates in the dataset's CRS read straight from the input
    rasters through each raster's own transform (the rasters chosen by their own bounds), masked by these few lines
    (not mask()), the first raster with a value taken; compared with the tile within 5 mm and for no
    data. An averaged product's pixel is compared with the mean of its block's input pixels, each read so (the sum of
    the valid ones over their count, here). The problems found and the random pixels compared."""
    i, j = map(int, key.split("_"))
    px, res, (ox, oy) = got.shape[0], product.res, product.origin
    rows = np.array([rng.randrange(px) for _ in range(n)], dtype=int)
    cols = np.array([rng.randrange(px) for _ in range(n)], dtype=int)
    random_points = n
    if extra is not None and len(extra[0]):
        rows, cols = np.concatenate([rows, extra[0]]), np.concatenate([cols, extra[1]])
        n = rows.size
    xs = ox + i * TILE_M + (cols + 0.5) * res
    ys = oy + (j + 1) * TILE_M - (rows + 0.5) * res
    a = product.average
    if a != 1:  # the centres of each sampled pixel's a x a input pixels: n rows of a * a points
        offsets = (np.arange(a) + 0.5) * input_res(product)
        dy, dx = np.meshgrid(offsets, offsets, indexing="ij")
        xs = ((ox + i * TILE_M + cols * res)[:, None] + dx.reshape(-1)[None, :]).reshape(-1)
        ys = ((oy + (j + 1) * TILE_M - rows * res)[:, None] - dy.reshape(-1)[None, :]).reshape(-1)
    found = np.full(xs.size, np.nan)
    left, right, bottom, top = ox + i * TILE_M, ox + (i + 1) * TILE_M, oy + j * TILE_M, oy + (j + 1) * TILE_M
    for rid, path, (b_left, b_bottom, b_right, b_top) in readers:
        if b_right <= left or b_left >= right or b_top <= bottom or b_bottom >= top:
            continue
        if path not in handles:
            handles[path] = rio.open(path)
        src = handles[path]
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
    if a != 1:
        blocks = found.reshape(n, a * a)
        valid = ~np.isnan(blocks)
        count = valid.sum(axis=1)
        total = np.where(valid, blocks, 0.0).sum(axis=1)
        found = np.full(n, np.nan)
        found[count > 0] = total[count > 0] / count[count > 0]
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
    return problems, random_points


def _touched(bounds: Tuple[float, float, float, float], product: Product) -> set:
    """The keys of the tiles a box touches, computed here (not with tiles_of)."""
    (ox, oy), (b_left, b_bottom, b_right, b_top) = product.origin, bounds
    i0, i1 = math.floor((b_left - ox) / TILE_M + 1e-9), math.ceil((b_right - ox) / TILE_M - 1e-9)
    j0, j1 = math.floor((b_bottom - oy) / TILE_M + 1e-9), math.ceil((b_top - oy) / TILE_M - 1e-9)
    return {f"{i}_{j}" for i in range(i0, i1) for j in range(j0, j1)}


def _verify_product(ds: Dataset, product: Product, work: str, out: str, inputs: Optional[str],
                    samples: Optional[int], seed: int, max_memory_gb: float, points: int = POINTS) -> Dict:
    where = tile_folder(ds, product)
    if final_state(out, ds, product) != "final":
        print(f"{where}: not final: nothing to verify", flush=True)
        return {"dataset": ds.name, "product": product.name, "final": False, "ok": None, "problems": []}
    folder = _folder(out, ds, product)
    final_path = os.path.join(folder, "index.json")
    index = _load_index(final_path)
    index_sha = _sha256(final_path)
    problems: List[str] = []
    notes: List[str] = []
    verify_path = os.path.join(folder, "verify.json")
    if os.path.exists(verify_path + ".part"):  # a verify stopped while writing its result
        _remove(verify_path + ".part", folder)
    listed = {os.path.normcase(os.path.join(folder, *tile_name(*map(int, k.split("_"))).split("/"))): k
              for k, v in index["tiles"].items() if v}

    def tile_problem(item):
        key, digest = item
        path = os.path.join(folder, *tile_name(*map(int, key.split("_"))).split("/"))
        if digest is None:
            return f"{key}: listed as without data, but its file exists" if os.path.exists(path) else None
        if not os.path.exists(path):
            return f"{key}: its file is missing"
        return f"{key}: the file does not match its sha256" if _sha256(path) != digest else None
    with ThreadPoolExecutor(max_workers=THREADS) as hashing:  # every listed tile's sha256 on several threads
        problems += [x for x in hashing.map(tile_problem, list(index["tiles"].items())) if x]
    unlisted = []
    for root, _, names in os.walk(folder):
        for n in names:
            path = os.path.join(root, n)
            if os.path.normcase(path) not in listed and n not in ("index.json", "verify.json", INPUTS_FILE):
                unlisted.append(os.path.relpath(path, folder).replace(os.sep, "/"))
    if unlisted:
        problems.append(f"{len(unlisted)} file(s) the index does not list: {unlisted[:5]}")
    keys = [k for k, v in index["tiles"].items() if v]
    nulls = [k for k, v in index["tiles"].items() if v is None]
    samples = default_samples(len(keys)) if samples is None else samples
    compared, removed, pixels = [], [], 0
    journal = read_journal(journal_path(work, ds, product, out))
    files = WorkFiles(work)
    handles: Dict[str, "rio.DatasetReader"] = {}
    try:
        # The inputs as they are now (index.json's missing_inputs is a record of the cut, not a request)
        r = resolve(product, work, inputs, files)
        if r.unpack:  # a clean removed the members: unpacked again to read them
            _extract_product(ds, product, work, inputs, files, max_memory_gb)
            r = resolve(product, work, inputs, files)
        # Judged against the inputs this edition was cut from (inputs.jsonl; a folder of before: those of now)
        recorded = {row["id"]: row.get("stamp") for row in read_jsonl(os.path.join(folder, INPUTS_FILE))
                    if row.get("id")} if os.path.exists(os.path.join(folder, INPUTS_FILE)) else None
        rasters = r.rasters if recorded is None else [x for x in r.rasters if x.id in recorded]
        if recorded is not None:
            later = [x.id for x in r.rasters if x.id not in recorded]
            if later:
                notes.append(f"{len(later)} inputs arrived after this product was cut (not part of this edition): a "
                             f"new edition would include them: {', '.join(later[:5])}")
            now = {x.id: x.stamp for x in rasters}
            intact = all(now.get(rid) == stamp for rid, stamp in recorded.items())
        else:
            intact = r.complete
        present = {x.id: x for x in rasters}
        _, cache_mb = _workers(product, 1, max_memory_gb)
        with rio.Env(GDAL_CACHEMAX=cache_mb):
            paths = [(x.id, readable(x, work, input_res(product), max_memory_gb, files)) for x in rasters]
            own = _own_reading(paths, product)
            bounds = {rid: b for rid, (b, _) in own.items()}
            readers = [(rid, path, bounds[rid]) for rid, path in paths]
            # The extent from the rasters' own bounds against the index: every tile a raster touches is listed,
            # every tile with data lies under a raster (only while every input is there)
            if intact:
                touched = set().union(*(_touched(b, product) for b in bounds.values())) if bounds else set()
                outside_index = sorted(touched - set(index["tiles"]))
                if outside_index:
                    problems.append(f"{len(outside_index)} tile(s) under an input are not in the index: "
                                    f"{outside_index[:5]}")
                stray = sorted(set(keys) - touched)
                if stray:
                    problems.append(f"{len(stray)} tile(s) with data lie under no input: {stray[:5]}")
                if journal:
                    fed_ids = set().union(*(set(line["fed"]) for line in journal.values()))
                    for rid in present:
                        if rid not in fed_ids:
                            if _touched(bounds[rid], product) & set(index["tiles"]):
                                problems.append(f"{rid}: an input under listed tiles that fed none (never read)")
                            else:
                                notes.append(f"{rid}: fed nothing (outside the grid)")
                else:
                    notes.append("no journal in this work folder: which inputs fed which tile is not checked")
            else:
                notes.append("inputs removed since the cut: the extent and the feeders are not checked")

            def checkable(key):
                line = journal.get(key)
                if line is None:
                    return intact
                return all(rid in present and present[rid].stamp == s for rid, s in line["fed"].items())
            checkable_keys = [k for k in keys if checkable(k)]
            checkable_nulls = [k for k in nulls if checkable(k)]
            removed = sorted(set(keys) - set(checkable_keys)) + sorted(set(nulls) - set(checkable_nulls))
            rng = random.Random(f"{ds.name}/{product.name}/{seed}")
            chosen = sorted(rng.sample(checkable_keys, min(samples, len(checkable_keys))))
            chosen_nulls = sorted(rng.sample(checkable_nulls, min(2, len(checkable_nulls))))
            px = tile_px(product.res)
            ox, oy = product.origin
            fps = [(rid, own[rid][1]) for rid, _ in paths]  # read again, not from the cut's cache
            for key in chosen + chosen_nulls:
                for h in handles.values():  # one sampled tile's files open at a time, never every raster
                    h.close()
                handles.clear()
                i, j = map(int, key.split("_"))
                tile_box = (ox + i * TILE_M, oy + j * TILE_M, ox + (i + 1) * TILE_M, oy + (j + 1) * TILE_M)
                under = [(rid, fp) for rid, fp in fps
                         if not (bounds[rid][2] <= tile_box[0] or bounds[rid][0] >= tile_box[2] or
                                 bounds[rid][3] <= tile_box[1] or bounds[rid][1] >= tile_box[3])]
                for _, fp in under:
                    if fp.path not in handles:
                        handles[fp.path] = rio.open(fp.path)
                expected = assemble((i, j), product, under, handles) if under else \
                    np.full((px, px), np.nan, np.float32)
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
                extra, edges = None, {}
                if product.average != 1:  # the blocks where a mean can go wrong, from the inputs themselves
                    extra, edges = _edge_blocks(key, product, readers, rng, handles)
                    problems += [f"{key}: {kind} blocks found but none compared" for kind in ("partial", "seam")
                                 if edges[f"{kind}_found"] and not edges[f"{kind}_chosen"]]
                found, n = (_point_problems(key, got, product, readers, rng, points, handles) if extra is None else
                            _point_problems(key, got, product, readers, rng, points, handles, extra=extra))
                problems += found
                pixels += n
                compared.append({"tile": key, "data": True, "max_diff_m": round(worst, 5),
                                 "valid_px": int(both.sum()), **edges})
    finally:
        for h in handles.values():
            h.close()
        files.close()
    # ok: no problem and tiles with data really compared; none compared (their inputs gone): not checkable (None)
    with_data = sum(1 for c in compared if c["data"])
    ok = False if problems else (True if with_data else None)
    result = {"dataset": ds.name, "product": product.name, "checked": datetime.datetime.now().isoformat(
        timespec="seconds"), "index_sha256": index_sha, "seed": seed, "samples_asked": samples,
        "tiles": len(index["tiles"]), "with_data": len(keys), "sha256_checked": len(keys), "samples": compared,
        "points_compared": pixels, "not_checkable": len(removed), "not_checkable_tiles": removed[:100],
        "notes": notes, "unlisted": unlisted[:100], "problems": problems, "ok": ok}
    for note in notes:
        print(f"{where}: {note}", flush=True)
    before = _load_index(verify_path) if os.path.exists(verify_path) else None
    if before and ok is None and before.get("ok") and before.get("index_sha256") == index_sha:
        print(f"{where}: verify: nothing checkable ({len(removed)} tiles: inputs removed); the passing verify of "
              f"{before.get('checked')} of this index kept", flush=True)
        return {**before, "kept": True}
    with open(verify_path + ".part", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    _site("verify.before_replace")
    _replace(verify_path + ".part", verify_path)
    _site("verify.after_replace")
    if ok is None:
        print(f"{where}: final, not verified (inputs removed): {len(removed)} tiles not checkable", flush=True)
        return result
    print(f"{where}: verify {'ok' if not problems else 'FAILED'}: {len(keys)} tiles' sha256, "
          f"{len(compared)} compared with the inputs ({pixels} pixels also read straight from them)"
          + (f", {len(removed)} tiles: inputs removed" if removed else "")
          + "".join(f"\n  {x}" for x in problems[:20]), flush=True)
    return result


def verified(ds: Dataset, product: Product, out: str) -> Optional[str]:
    """When a product is final and its verify.json passed on this very index.json: the verify's date, else None."""
    if final_state(out, ds, product) != "final":
        return None
    folder = _folder(out, ds, product)
    final, verify_path = os.path.join(folder, "index.json"), os.path.join(folder, "verify.json")
    if not os.path.exists(verify_path):
        return None
    result = _load_index(verify_path)
    return result.get("checked") if result.get("ok") and result.get("index_sha256") == _sha256(final) else None


# Status and clean

def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, n)) for r, _, ns in os.walk(path) for n in ns)


def status(names: Sequence[str], work: str, out: Optional[str], inputs: Optional[str]) -> List[str]:
    """Lines a person can read, per product: final (when, tiles, verified or not), cutting (tiles done of planned),
    ready to cut, or waiting (present of expected, the first ids missing)."""
    lines = []
    for name in names:
        ds = dataset(name)
        lines.append(f"{name}: {ds.title}")
        for product in ds.products:
            head = f"  {product.name}/{product.res:g}m"
            if out and final_state(out, ds, product) == "final":
                index = _load_index(os.path.join(_folder(out, ds, product), "index.json"))
                when = verified(ds, product, out)
                with_data = sum(v is not None for v in index["tiles"].values())
                result_path = os.path.join(_folder(out, ds, product), "verify.json")
                result = _load_index(result_path) if os.path.exists(result_path) else {}
                lines.append(f"{head}: final ({index.get('created')}), {with_data} tiles with data of "
                             f"{len(index['tiles'])}, " + (f"verified {when}" if when else
                                                           "verify FAILED: " + "; ".join(result["problems"][:2])
                                                           if result.get("ok") is False else
                                                           "not verified (inputs removed)" if "ok" in result
                                                           else "not verified"))
                continue
            if out and final_state(out, ds, product) == "before":
                lines.append(f"{head}: an unfinished folder of an earlier version of the tool: move it away")
                continue
            try:
                r = resolve(product, work, inputs, without=())
            except ValueError as e:
                lines.append(f"{head}: {e}")
                continue
            journal = read_journal(journal_path(work, ds, product, out)) if out else {}
            if not r.complete:
                shown = r.missing[:20]
                lines.append(f"{head}: waiting ({'; '.join(r.counts) or 'inputs missing'}); missing "
                             f"{', '.join(shown)}" + (" and more" if len(r.missing) > 20 else ""))
            elif journal:
                planned = None
                state = State(work, ds, product)
                try:
                    fps = [state.cached(x, product) for x in r.rasters]
                finally:
                    state.close()
                if all(fps):
                    keys = set()
                    for fp in fps:
                        rows, cols = tiles_of(fp, product)
                        keys |= {(i, j) for j in rows for i in cols}
                    i_s, j_s = [k[0] for k in keys], [k[1] for k in keys]
                    planned = (max(i_s) - min(i_s) + 1) * (max(j_s) - min(j_s) + 1)
                lines.append(f"{head}: cutting: {len(journal)} tiles done" + (f" of {planned}" if planned else ""))
            else:
                lines.append(f"{head}: ready to cut ({'; '.join(r.counts) or f'{len(r.rasters)} raster(s)'})")
        for url in _urls(ds):
            path = zip_path(url, work)
            if os.path.exists(path):
                lines.append(f"  work: {path} ({_size(path) / 1e6:.0f} MB)")
            elif os.path.exists(path + ".part"):
                lines.append(f"  work: {path}.part, {_size(path + '.part')} of {url.bytes} bytes")
    if os.path.isdir(os.path.join(work, "tiled")):
        lines.append(f"work: tiled copies {_size(os.path.join(work, 'tiled')) / 1e9:.2f} GB")
    for ds_name, prod, res, path, _ in staging_folders(work, out):
        tiles = sum(1 for _, _, ns in os.walk(path) for n in ns if n.endswith(".tif"))
        final = ""
        if out and os.path.isfile(os.path.join(out, ds_name, prod, res, "index.json")):
            final = " (the product is final: a leftover, clean removes it)"
        lines.append(f"staging: {ds_name}/{prod}/{res}: {tiles} tiles, {_size(path) / 1e6:.1f} MB, {path}{final}")
    return lines


def staging_folders(work: str, out: Optional[str]) -> List[Tuple[str, str, str, str, str]]:
    """Every staging folder in both places: (dataset, product, res folder, its path, the place's root)."""
    found = []
    for root in [os.path.join(work, "staging")] + ([os.path.join(out, ".staging")] if out else []):
        if not os.path.isdir(root):
            continue
        for ds_name in sorted(os.listdir(root)):
            if ds_name.startswith(".") or not os.path.isdir(os.path.join(root, ds_name)):
                continue
            for prod in sorted(os.listdir(os.path.join(root, ds_name))):
                for res in sorted(os.listdir(os.path.join(root, ds_name, prod))):
                    path = os.path.join(root, ds_name, prod, res)
                    if os.path.isdir(path):
                        found.append((ds_name, prod, res, path, root))
    return found


def _remove_staging(path: str, root: str):
    """A staging folder removed file by file (only below the staging place's root), then its empty folders."""
    for top, dirs, names in os.walk(path, topdown=False):
        for n in names:
            _remove(os.path.join(top, n), root)
        os.rmdir(top)


def clean(name: str, work: str, inputs: Optional[str] = None, product: Optional[str] = None,
          out: Optional[str] = None, staging: bool = False) -> List[str]:
    """The product's unpacked members and tiled copies removed from work: only files the tool recorded as made by it
    (WorkFiles), never an input, never a downloaded file; what is left in work, as lines. With out: the product's
    staging folder too when the product is final already (a leftover), or with staging=True (--staging) when no run
    cuts it now (its lock), never one a running cut holds."""
    ds = dataset(name)
    check_folders(work, inputs, out)
    removed = 0
    with _work_lock(work):
        if out:
            for prod in _products(ds, product):
                for ds_name, prod_name, res, path, root in staging_folders(work, out):
                    if (ds_name, prod_name, res) != (ds.name, prod.name, f"{prod.res:g}m"):
                        continue
                    final = final_state(out, ds, prod) == "final"
                    if not final and not staging:
                        print(f"{path}: the staging folder of a product being cut: kept (--staging removes it when "
                              "no run cuts it)", flush=True)
                        continue
                    try:
                        with _product_lock(out, ds, prod):
                            removed += _size(path)
                            _remove_staging(path, root)
                            print(f"{path}: removed" + (" (the product is final)" if final else ""), flush=True)
                    except Busy as e:
                        print(f"{path}: kept: {e}", flush=True)
        files = WorkFiles(work)
        try:
            for prod in _products(ds, product):
                try:
                    rasters = resolve(prod, work, inputs, files).rasters
                except ValueError as e:
                    print(f"{tile_folder(ds, prod)}: {e}", flush=True)
                    continue
                for raster in rasters:
                    for path in (_copy_path(raster.path, work), raster.path):
                        if files.made(path) and os.path.exists(path):
                            try:
                                size = _size(path)
                                _remove(path, work)
                                removed += size
                            except ValueError as e:  # a link that leads outside --work: left
                                print(e, flush=True)
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


def _without(args) -> List[str]:
    ids = list(args.without or [])
    if args.without_file:
        with open(args.without_file, encoding="utf-8") as f:
            ids += [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["download", "extract", "cut", "verify", "status", "clean", "all"])
    parser.add_argument("dataset", nargs="?", choices=sorted(DATASETS))
    parser.add_argument("--work", required=True, help="the tool's own files: downloads, unpacked rasters, staging, "
                                                      "journals, caches (apart from the inputs and the mirror)")
    parser.add_argument("--inputs", help="placed files and the fetch tool's folders (apart from --work and --out)")
    parser.add_argument("--out", help=f"the mirror (default: the environment's {MIRROR_ENV})")
    parser.add_argument("--product", help="one product of the dataset")
    parser.add_argument("--rows", type=int, help="cut: stop after this many rows of tiles (a trial)")
    parser.add_argument("--threads", type=int, default=THREADS, help=f"tiles written at once (default {THREADS})")
    parser.add_argument("--max-memory-gb", type=float, default=MAX_MEMORY_GB,
                        help=f"the cut's estimated bound, GDAL's cache included (default {MAX_MEMORY_GB:g})")
    parser.add_argument("--samples", type=int, help="verify: tiles compared (default 1 %%, at least 8, at most 500)")
    parser.add_argument("--seed", type=int, default=0, help="verify: the sample's seed (default 0)")
    parser.add_argument("--without", nargs="+", metavar="ID",
                        help="cut: the product is complete without exactly these fetched ids (sheets the provider "
                             "never delivered); recorded in the index and the card")
    parser.add_argument("--without-file", help="cut: the ids of --without, one per line")
    parser.add_argument("--staging", action="store_true",
                        help="clean: also the staging folder of a product not final yet (no run may be cutting it)")
    args = parser.parse_args()
    out = args.out or os.environ.get(MIRROR_ENV)
    without = _without(args)
    if args.step != "status" and not args.dataset:
        sys.exit("a dataset is needed")
    if without and not args.product and len(dataset(args.dataset).products) > 1:
        sys.exit("--without names one product's ids: give --product")
    if args.step in ("cut", "verify", "all") and not out:
        sys.exit(f"--out or {MIRROR_ENV} is needed")
    try:
        check_folders(args.work, args.inputs, out)
        if args.step == "status":
            print("\n".join(status([args.dataset] if args.dataset else sorted(DATASETS), args.work, out,
                                   args.inputs)))
            return
        ds = dataset(args.dataset)
        if args.step == "all":
            failed = False
            with _work_lock(args.work):
                todo = []
                for prod in _products(ds, args.product):
                    when = verified(ds, prod, out)
                    if when:
                        print(f"{tile_folder(ds, prod)}: final and verified on {when}: skipped", flush=True)
                    else:
                        todo.append(prod)
                if todo and any(final_state(out, ds, prod) != "final" for prod in todo):
                    download(args.dataset, args.work)
                for prod in todo:
                    state_now = cut(args.dataset, args.work, out, args.rows, args.inputs, prod.name, args.threads,
                                    args.max_memory_gb, without)[prod.name]
                    if state_now not in ("cut", "final"):
                        continue  # waiting, a trial or a folder of before: the next product
                    results = verify(args.dataset, args.work, out, args.inputs, prod.name, args.samples, args.seed,
                                     args.max_memory_gb)
                    if results[prod.name]["ok"] is False:
                        failed = True
                        continue
                    clean(args.dataset, args.work, args.inputs, prod.name, out)
            if failed:
                sys.exit(1)
            return
        if args.step == "download":
            download(args.dataset, args.work)
        elif args.step == "extract":
            extract(args.dataset, args.work, args.inputs, args.product, args.max_memory_gb, without)
        elif args.step == "cut":
            cut(args.dataset, args.work, out, args.rows, args.inputs, args.product, args.threads, args.max_memory_gb,
                without)
        elif args.step == "verify":
            results = verify(args.dataset, args.work, out, args.inputs, args.product, args.samples, args.seed,
                             args.max_memory_gb)
            if any(r["ok"] is False for r in results.values()):
                sys.exit(1)
        elif args.step == "clean":
            clean(args.dataset, args.work, args.inputs, args.product, out, args.staging)
    except (Busy, ValueError) as e:  # a refusal (folders, --without, a file's sha256): one sentence, exit 1
        sys.exit(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
