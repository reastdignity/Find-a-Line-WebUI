"""
Own copies of elevation models published only as one big file, cut into 2 km tiles for the local mirror (run by
hand, not by the app).

Madeira's 2 m DTM (DROTe: one ZIP of one BigTIFF) and Valle d'Aosta's 2 m DTM (the region's DTM 2005/2008: one ZIP
of one ESRI ASCII grid with decimal commas, packed with Deflate64, which Python's zipfile cannot unpack) cannot be read
in parts over the network. This tool downloads such a file once, unpacks it, reads the raster in bands of 2 km from
the top and writes 2 km tiles in the dataset's own CRS on its own pixel grid (the tile grid starts at the dataset's
`origin`, its pixel edges modulo 2 km), in the layout and encoding of tools/sk_tiles.py (Slovakia's tiles, whose
helpers it reuses): <mirror>/<folder>/<product>/<res>m/<block>/<i>_<j>.tif, COG LERC_ZSTD within 5 mm
(sk_tiles._write), index.json with every tile of the raster's extent and its sha256 (null: no data), "partial" while
rows are still to be cut, a dataset card (README.md) with the licence beside the products. sources.GridTiles reads
them through FINDALINE_MIRROR (the folder above <folder>), with the same `origin`; tile (i, j) covers
[origin_x + 2000 i, origin_x + 2000 (i + 1)) x [origin_y + 2000 j, origin_y + 2000 (j + 1)).

    python tools/mirror_tiles.py download aosta --work C:\\fal\\work          # the ZIP (resumed where allowed)
    python tools/mirror_tiles.py extract aosta --work C:\\fal\\work           # the raster beside it (7-Zip for Deflate64)
    python tools/mirror_tiles.py cut aosta --work C:\\fal\\work [--out DIR]    # tiles + index (resumable)
    python tools/mirror_tiles.py all aosta --work C:\\fal\\work [--out DIR]    # the three steps in turn

--out is the mirror (default: the environment's FINDALINE_MIRROR); the tiles go to <out>/<folder>/<product>/<res>m.
A new dataset of this kind (Valle d'Aosta's DSM, which follows by hand later) is one more entry of DATASETS.

Download: one GET of the whole file through the app's request path (cache.http_headers, net.rate_turn,
servicecounts), into <name>.part; an interrupted download resumes with a Range from where it stopped when the
dataset allows it (`resume_below`: Valle d'Aosta's firewall answers HTTP 500 to a Range starting beyond about 1e8
bytes, so there a broken download starts again), at most ATTEMPTS attempts; a server answering 200 to the Range
sends the whole file, which is then written from the start; never more than the dataset's `bytes` are read (a file of
another size stops the download: the dataset has changed, check it and update DATASETS).
"""

import argparse
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

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
from sk_tiles import TILE_M, BLOCK, MAX_Z_ERROR, CACHE_MB, WRITE_THREADS, tile_name, _sha256  # noqa: E402

ATTEMPTS = 3      # download attempts (the first and two more)
# Replacing a file on a network share (the mirror on Z:) is refused now and then for a moment (WinError 5 while
# the share or a scanner holds the old file): tried again for this long
REPLACE_SECONDS = 60
CHUNK = 8 << 20   # bytes per write of a download
# 7-Zip unpacks Deflate64 (ZIP method 9); zipfile only stored and Deflate (0, 8)
SEVEN_ZIP = os.environ.get("FINDALINE_7ZIP") or shutil.which("7z") or shutil.which("7za") or \
    r"C:\Program Files\7-Zip\7z.exe"

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

# url, its size in bytes, the raster's member in the ZIP, the mirror's folder and product, the CRS (the files' own:
# the tiles carry its EPSG code), the pixel size, the tile grid's origin (the pixel edges modulo TILE_M), the values
# that mean no data, resume_below (a broken download resumes by a Range only below this byte; None: always)
DATASETS: Dict[str, Dict] = {
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
}


class SizeChanged(RuntimeError):
    """The server's file is not of the dataset's size: never read beyond it."""


def tile_folder(spec: Dict) -> str:
    """The product's folder below the mirror: <folder>/<product>/<res>m."""
    return f"{spec['folder']}/{spec['product']}/{spec['res']:g}m"


# Download

def zip_path(spec: Dict, work: str) -> str:
    return os.path.join(work, os.path.basename(spec["url"]))


def download(name: str, work: str) -> str:
    """The dataset's ZIP in work (see the module's docstring); its path."""
    spec = DATASETS[name]
    url, total = spec["url"], spec["bytes"]
    os.makedirs(work, exist_ok=True)
    path = zip_path(spec, work)
    part = path + ".part"
    if os.path.exists(path) and os.path.getsize(path) == total:
        print(f"{path}: complete ({total / 1e9:.2f} GB)")
        return path
    resume_below = spec.get("resume_below")
    error = None
    for attempt in range(ATTEMPTS):
        done = os.path.getsize(part) if os.path.exists(part) else 0
        if done >= total or (done and resume_below is not None and done >= resume_below):
            print(f"  {done} bytes of before: the download starts again (no Range from there)", flush=True)
            os.remove(part)
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
                os.remove(part)
            raise
        except (requests.RequestException, RuntimeError, OSError) as e:
            error = cache.clean_error(e)
        print(f"  attempt {attempt + 1} of {ATTEMPTS}: {error}", flush=True)
        if attempt + 1 < ATTEMPTS:
            net._sleep(attempt)
    raise RuntimeError(f"Could not download {url}: {error}")


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


# Extract

def extracted(spec: Dict, work: str) -> str:
    return os.path.join(work, os.path.basename(spec["member"]))


def extract(name: str, work: str) -> str:
    """The raster member of the ZIP beside it (through a .part, removed when the unpacking fails: up to 9.85 GB):
    zipfile for stored and Deflate members (its CRC checked), 7-Zip for the others (Deflate64; 7-Zip checks the CRC).
    Its path."""
    spec = DATASETS[name]
    path = extracted(spec, work)
    with zipfile.ZipFile(zip_path(spec, work)) as archive:
        info = archive.getinfo(spec["member"])
        if os.path.exists(path) and os.path.getsize(path) == info.file_size:
            print(f"{path}: already extracted ({info.file_size / 1e9:.2f} GB)")
            return path
        start, part = time.time(), path + ".part"
        try:
            if info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                with archive.open(info) as src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst, 64 << 20)
            else:
                _seven_zip(zip_path(spec, work), spec["member"], part)
            if os.path.getsize(part) != info.file_size:
                raise RuntimeError(f"{part}: {os.path.getsize(part)} bytes, {info.file_size} expected")
        except BaseException:
            if os.path.exists(part):
                os.remove(part)
            raise
    os.replace(part, path)
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


# Reading in bands

class Bands:
    """A raster read in bands of rows from the top: width, height, left, top, res; rows(r0, r1) gives rows r0 to r1
    as float32 with NaN for every no-data value (rows asked in increasing order)."""
    width: int
    height: int
    left: float
    top: float
    res: float

    def __init__(self, nodata: Tuple[float, ...]):
        self.nodata = tuple(nodata)

    def _masked(self, values: np.ndarray) -> np.ndarray:
        values = values.astype(np.float32, copy=False)
        for value in self.nodata:
            values[values == np.float32(value)] = np.nan
        return values

    def close(self):
        pass


class TiffBands(Bands):
    """A GeoTIFF (strips or tiles) read by rasterio in windows of whole rows."""

    def __init__(self, path: str, nodata: Tuple[float, ...]):
        src = self.src = rio.open(path)
        super().__init__(nodata + ((src.nodata,) if src.nodata is not None else ()))
        if src.count != 1 or src.transform.b or src.transform.d:
            raise ValueError(f"{path}: one band without rotation expected")
        if not math.isclose(src.res[0], src.res[1]):
            raise ValueError(f"{path}: square pixels expected, not {src.res}")
        self.width, self.height, self.res = src.width, src.height, float(src.res[0])
        self.left, self.top = src.transform.c, src.transform.f
        self.crs = src.crs

    def rows(self, r0: int, r1: int) -> np.ndarray:
        return self._masked(self.src.read(1, window=Window(0, r0, self.width, r1 - r0)))

    def close(self):
        self.src.close()


class AscBands(Bands):
    """An ESRI ASCII grid read line by line (decimal points or commas, LF or CRLF; a row may run over several
    lines): the header (ncols, nrows, xllcorner or xllcenter, yllcorner or yllcenter, cellsize, NODATA_value), then
    nrows rows of ncols values from the top. A row of another number of values, or a value that is not a number,
    raises ValueError."""

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
        super().__init__(tuple(nodata) + ((header["nodata_value"],) if "nodata_value" in header else ()))
        self.width, self.height, self.res = int(header["ncols"]), int(header["nrows"]), header["cellsize"]
        half = self.res / 2
        self.left = header["xllcorner"] if "xllcorner" in header else header["xllcenter"] - half
        bottom = header["yllcorner"] if "yllcorner" in header else header["yllcenter"] - half
        self.top = bottom + self.height * self.res
        self.crs = None
        self.row = 0  # the next row to read

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

    def rows(self, r0: int, r1: int) -> np.ndarray:
        if r0 < self.row:
            raise ValueError(f"rows are read from the top: row {r0} asked after row {self.row}")
        while self.row < r0:
            self._values()
        out = np.empty((r1 - r0, self.width), dtype=np.float32)
        for k in range(r1 - r0):
            out[k] = self._values()
        return self._masked(out)

    def close(self):
        self.f.close()


def open_bands(path: str, nodata: Tuple[float, ...]) -> Bands:
    return AscBands(path, nodata) if path.lower().endswith(".asc") else TiffBands(path, nodata)


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


def _on_grid(value: float, origin: float, res: float, what: str) -> float:
    """value moved onto the pixel grid through origin (within 1 mm: ASCII headers carry such noise); ValueError when
    it is not on it."""
    snapped = origin + round((value - origin) / res) * res
    if abs(snapped - value) > 1e-3:
        raise ValueError(f"the raster's {what} {value} is not on the grid of {res} m pixels through {origin} "
                         "(the dataset's origin is wrong)")
    return snapped


def cut(name: str, work: str, out: str, rows_limit: Optional[int] = None) -> Dict:
    """Cut the extracted raster into 2 km tiles under out (<out>/<folder>/<product>/<res>m), resuming: the rows
    of tiles in the index already are skipped; rows_limit stops after that many rows to cut (a trial). The index."""
    spec = DATASETS[name]
    res, (ox, oy), crs = spec["res"], spec["origin"], spec["crs"]
    px = round(TILE_M / res)
    if not math.isclose(px * res, TILE_M):
        raise ValueError(f"{res} m pixels do not divide {TILE_M} m tiles")
    root = os.path.join(out, spec["folder"])
    folder = os.path.join(out, *tile_folder(spec).split("/"))
    index_path = os.path.join(folder, "index.json")
    index = {"tiles": {}}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    source = extracted(spec, work)
    start, cut_rows = time.time(), 0
    with rio.Env(GDAL_CACHEMAX=CACHE_MB, GDAL_NUM_THREADS="ALL_CPUS"), \
            ThreadPoolExecutor(max_workers=WRITE_THREADS) as pool:
        bands = open_bands(source, tuple(spec["nodata"]))
        try:
            if not math.isclose(bands.res, res, rel_tol=1e-9):
                raise ValueError(f"{source}: {bands.res} m pixels, {res} m expected")
            if bands.crs is not None and bands.crs.to_epsg() not in (None, int(crs.split(":")[1])):
                raise ValueError(f"{source}: {bands.crs} is not {crs}")
            left = _on_grid(bands.left, ox, res, "left edge")
            top = _on_grid(bands.top, oy, res, "top edge")
            right, bottom = left + bands.width * res, top - bands.height * res
            rows = range(math.ceil((top - oy) / TILE_M) - 1, math.floor((bottom - oy) / TILE_M) - 1, -1)
            cols = range(math.floor((left - ox) / TILE_M), math.ceil((right - ox) / TILE_M))
            print(f"{source}: {bands.width} x {bands.height} px of {res:g} m, {len(rows)} x {len(cols)} tiles",
                  flush=True)
            for n, j in enumerate(rows):
                todo = [i for i in cols if f"{i}_{j}" not in index["tiles"]]
                if not todo:
                    continue
                if rows_limit is not None and cut_rows >= rows_limit:
                    break
                cut_rows += 1
                row0 = round((top - (oy + (j + 1) * TILE_M)) / res)  # the raster's row of the tiles' top edge
                c0 = round((ox + cols[0] * TILE_M - left) / res)
                band = np.full((px, len(cols) * px), np.nan, dtype=np.float32)
                r_in, r_end = max(row0, 0), min(row0 + px, bands.height)
                c_in, c_end = max(c0, 0), min(c0 + len(cols) * px, bands.width)
                part = bands.rows(r_in, r_end)
                band[r_in - row0:r_end - row0, c_in - c0:c_end - c0] = part[:, c_in:c_end]
                del part

                def save(i, band=band, j=j):
                    tile = np.ascontiguousarray(band[:, (i - cols[0]) * px:(i - cols[0] + 1) * px])
                    if not np.isfinite(tile).any():
                        return None
                    path = os.path.join(folder, *tile_name(i, j).split("/"))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    _write(path, tile, crs, from_origin(ox + i * TILE_M, oy + (j + 1) * TILE_M, res, res))
                    return _sha256(path)

                for i, digest in zip(todo, pool.map(save, todo)):
                    index["tiles"][f"{i}_{j}"] = digest
                del band
                index.update(dataset=name, product=spec["product"], title=spec["title"], source=spec["url"],
                             crs=crs, heights=spec["heights"], tile_m=TILE_M, resolution=res, origin=[ox, oy],
                             block=BLOCK, encoding=f"COG LERC_ZSTD, max_z_error {MAX_Z_ERROR} m",
                             licence=spec["licence"], attribution=spec["attribution"],
                             created=datetime.date.today().isoformat())
                sk_tiles._mark_partial(index, any(f"{i}_{jj}" not in index["tiles"] for jj in rows for i in cols))
                os.makedirs(folder, exist_ok=True)
                _save_index(index, index_path)
                done = sum(v is not None for v in index["tiles"].values())
                print(f"  row {n + 1}/{len(rows)}: {done} tiles with data, {(time.time() - start) / 60:.1f} min",
                      flush=True)
            if index.get("partial") and all(f"{i}_{j}" in index["tiles"] for j in rows for i in cols):
                sk_tiles._mark_partial(index, False)
                _save_index(index, index_path)
        finally:
            bands.close()
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
        f.write(spec["card"])
    tiles = [k for k, v in index["tiles"].items() if v]
    size = sum(os.path.getsize(os.path.join(folder, *tile_name(*map(int, k.split("_"))).split("/"))) for k in tiles)
    print(f"{folder}: {len(tiles)} tiles with data of {len(index['tiles'])}, {size / 1e9:.2f} GB, "
          f"{(time.time() - start) / 60:.1f} min" + (" (partial)" if index.get("partial") else ""), flush=True)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["download", "extract", "cut", "all"])
    parser.add_argument("dataset", choices=sorted(DATASETS))
    parser.add_argument("--work", required=True, help="folder of the ZIP and the extracted raster")
    parser.add_argument("--out", help=f"the mirror (default: the environment's {MIRROR_ENV})")
    parser.add_argument("--rows", type=int, help="cut: stop after this many rows of tiles (a trial)")
    args = parser.parse_args()
    out = args.out or os.environ.get(MIRROR_ENV)
    if args.step in ("cut", "all") and not out:
        sys.exit(f"--out or {MIRROR_ENV} is needed")
    if args.step in ("download", "all"):
        download(args.dataset, args.work)
    if args.step in ("extract", "all"):
        extract(args.dataset, args.work)
    if args.step in ("cut", "all"):
        cut(args.dataset, args.work, out, args.rows)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
