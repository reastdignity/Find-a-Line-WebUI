"""
Slovak ALS elevation models as small tiles on Hugging Face (run by hand, not by the app).

ÚGKK SR publishes the 1 m terrain model (DMR 5.0) and surface model (DMP 1.0) of the
whole country only as one ZIP each with one huge TIFF inside (about 155–200 GB), which
cannot be read in parts over the network. This script turns such a TIFF into 2 km COG
tiles in its own grid (S-JTSK [JTSK03] EPSG:8353, Baltic 1957 heights EPSG:8357) and
writes them into a folder laid out as a Hugging Face dataset. Until it is uploaded, that
folder is a local mirror: sources.GridTiles (sources/layers/gridtiles.py) reads it through
FINDALINE_MIRROR (the folder above it; SLOVAK_TILES in sources/catalogue/slovakia.py), later it
downloads the same tiles from Hugging Face.
Licence CC BY 4.0, author ÚGKK SR (the licence PDF in the ZIPs).

    python tools/sk_tiles.py download dmp1 --zips C:\\sk-zips                    # the ZIP (resumable)
    python tools/sk_tiles.py extract dmp1 --zips C:\\sk-zips                     # the TIFF beside it
    python tools/sk_tiles.py cut dmp1 --zips C:\\sk-zips --out C:\\mirror\\slovakia  # tiles + index (resumable)
    python tools/sk_tiles.py average dmr5 --out C:\\mirror\\slovakia               # 2m and 5m from 1m (resumable)
    python tools/sk_tiles.py recompress C:\\mirror\\slovakia\\dmr5\\2m ...          # averaged tiles in ZSTD (resumable)
    python tools/sk_tiles.py upload dmp1 --out C:\\mirror\\slovakia --repo user/name  # needs HF_TOKEN

--work DIR stands for both --zips DIR and --out DIR/tiles.

Layout in the dataset: <product>/1m/<block>/<E>_<N>.tif, where E, N are the tile's lower
left corner in km divided by 2 (E = floor(x / 2000)) and <block> groups 10 x 10 tiles
(E // 10, N // 10) so no folder holds more than 100 files; <product>/1m/index.json lists
the tiles with their sha256 (None: no data there). The TIFF is read in 2 km bands of the
full width from the top. Extract it first (122–157 GB): GDAL can read it straight from the
ZIP (/vsizip/; the national ZIPs are plain Deflate, forwards only), but at about 7 MB/s
(DMP 1.0: 9 min per band, 15 h in all) against 400 MB/s for Python's zipfile, and from the
plain file the band takes a fraction of that; cut uses the extracted TIFF when it is there.
Encoding: LERC_ZSTD with a maximum error of 5 mm (5.5 MB per km² at 0.5 m in the trial
on lot 04, against 9.4 MB lossless; the surveys are accurate to centimetres).

average writes the same tiles at coarser resolutions, <product>/2m and <product>/5m (FACTORS),
from the 1 m tiles: each pixel the mean of the valid 1 m pixels of its 2 x 2 or 5 x 5 block
(sources.readers.download._block_means, the rule of Download(average=)), a float32 GeoTIFF
without further loss (ZSTD with the floating point predictor, AVERAGED_PROFILE), with its own
index.json (null for the tiles without data). A search on a grid of exactly that resolution
reads them (sources.GridTiles with `averaged`): the country layer's bands at 2 m and 5 m
stitch a tile from 4 and 25 times fewer pixels.

recompress writes the averaged tiles of folders made before in AVERAGED_PROFILE (deflate until
2026-11-08: the same bits in about the same bytes, decoded in about 60 % of the time): every .tif
under each folder given, read, written to a .part beside it, read back and compared bit for bit
(values, georeference, nodata, tags), then put in its place atomically; a file that differs or
cannot be replaced is listed and left as it was, a file already in ZSTD is skipped (resumable).
A mirror's folder (an index.json in it) gets its tiles' new sha256 and encoding text in the
index and the dataset card beside the products written again; a folder in a cache (a LAYOUT
file above it: the copies GridTiles made of the mirror's tiles) gets each rewritten tile's new
sha256 in the cache's index (cache.reencoded: its times kept), under the tile's lock. A LERC
tile (the 1 m tiles) is refused and left.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import rasterio as rio
import requests
from rasterio.transform import from_origin
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources import grid_tile_name  # noqa: E402

BASE = "https://opendata.skgeodesy.sk/static/LLS"
PRODUCTS = {
    "dmr5": {"zip": f"{BASE}/DMR5/DMR5_0_sjtsk03_bpv.zip", "member": "dmr5_0/dmr5_jtsk03.tif",
             "title": "DMR 5.0 digital terrain model (ground)"},
    "dmp1": {"zip": f"{BASE}/DMP1/DMP1_0_sjtsk03_bpv.zip", "member": "dmp1_0/dmp1_jtsk03.tif",
             "title": "DMP 1.0 digital surface model (with vegetation and buildings)"},
}
# The national TIFFs name their CRS only (a LOCAL_CS, no projection): the tiles get the
# EPSG code, or nothing could reproject them
CRS = "EPSG:8353"
TILE_M = 2000
BLOCK = 10          # tiles per folder side
MAX_Z_ERROR = 0.005  # metres
# GDAL's block cache keeps the TIFF blocks a band shares with the previous one (a block
# row of the whole country is a few hundred MB), so they are not read again
CACHE_MB = 4096
WRITE_THREADS = os.cpu_count() or 4  # LERC and the COG driver release the GIL
HEADERS = {"User-Agent": "Find-a-Line/1.0 (highline finder; tiles for a public mirror)"}


FACTORS = (2, 5)     # the coarser resolutions kept beside the 1 m tiles (average)
# The averaged tiles: lossless float32, ZSTD with the floating point predictor in 256 px tiles (deflate with the same
# predictor until 2026-11-08). On 20 tiles of DMR 5.0 at 2 m (2026-11-08): deflate 2.06 MB a tile, decoded at one
# thread in 14.2 ms/Mpx; ZSTD at levels 3 / 9 / 15 2.08 / 2.04 / 2.03 MB, 9.0 / 8.0 / 8.0 ms/Mpx, encoded in
# 0.013 / 0.036 / 0.155 s. Level 9 (GDAL's default: the same bytes) decodes as fast as 15 and encodes 4 times faster
ZSTD_LEVEL = 9
AVERAGED_PROFILE = dict(compress="ZSTD", predictor=3, zstd_level=ZSTD_LEVEL, tiled=True, blockxsize=256,
                        blockysize=256)
REPLACE_SECONDS = 30  # recompress: how long replacing a tile another process has open is tried (Windows)


def tile_folder(product: str, res: float = 1.0) -> str:
    return f"{product}/{res:g}m"


def tile_name(i: int, j: int) -> str:
    """Path of tile (i, j) inside the product folder (the naming of sources.GridTiles)."""
    return grid_tile_name(i, j, BLOCK)


def download(product: str, zips: str):
    """Download the ZIP into the folder zips, resuming a partial file."""
    url = PRODUCTS[product]["zip"]
    path = os.path.join(zips, os.path.basename(url))
    total = int(requests.head(url, headers=HEADERS, timeout=60).headers["Content-Length"])
    done = os.path.getsize(path) if os.path.exists(path) else 0
    if done == total:
        print(f"{path}: complete ({total / 1e9:.1f} GB)")
        return path
    start, last = time.time(), time.time()
    with requests.get(url, headers={**HEADERS, "Range": f"bytes={done}-"}, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "ab") as f:
            for chunk in r.iter_content(chunk_size=8 << 20):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 30:
                    last = time.time()
                    print(f"  {done / 1e9:.1f} of {total / 1e9:.1f} GB, {done / total:.1%}, "
                          f"{(time.time() - start) / 60:.0f} min", flush=True)
    print(f"{path}: {done / 1e9:.1f} GB in {(time.time() - start) / 60:.0f} min")
    return path


def extracted(product: str, zips: str) -> str:
    """Path of the TIFF extracted beside the ZIP."""
    return os.path.join(zips, os.path.basename(PRODUCTS[product]["member"]))


def extract(product: str, zips: str):
    """Extract the TIFF from the ZIP into the folder zips (through a .part file)."""
    spec = PRODUCTS[product]
    path = extracted(product, zips)
    with zipfile.ZipFile(os.path.join(zips, os.path.basename(spec["zip"]))) as archive:
        total = archive.getinfo(spec["member"]).file_size
        if os.path.exists(path) and os.path.getsize(path) == total:
            print(f"{path}: already extracted ({total / 1e9:.1f} GB)")
            return path
        start, last, done = time.time(), time.time(), 0
        with archive.open(spec["member"]) as src, open(path + ".part", "wb") as dst:
            while chunk := src.read(64 << 20):
                dst.write(chunk)
                done += len(chunk)
                if time.time() - last > 30:
                    last = time.time()
                    print(f"  {done / 1e9:.1f} of {total / 1e9:.1f} GB, {(time.time() - start) / 60:.0f} min",
                          flush=True)
    os.replace(path + ".part", path)
    print(f"{path}: {total / 1e9:.1f} GB in {(time.time() - start) / 60:.0f} min")
    return path


def _write(path: str, band: np.ndarray, crs, transform):
    tmp = path + ".part"
    with rio.open(tmp, "w", driver="COG", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, transform=transform, nodata=np.nan, compress="LERC_ZSTD", max_z_error=MAX_Z_ERROR,
                  blocksize=512, overview_resampling="average") as dst:
        dst.write(band, 1)
    os.replace(tmp, path)


def _write_averaged_part(path: str, band: np.ndarray, crs, transform, tags=None, level: Optional[int] = None) -> str:
    """An averaged tile written to a temporary file next to path (its .part), whose name is returned:
    AVERAGED_PROFILE (level: ZSTD's instead of the profile's), NaN for no data."""
    from sources.net import _part
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = _part(path)
    profile = {**AVERAGED_PROFILE, **({} if level is None else {"zstd_level": level})}
    with rio.open(tmp, "w", driver="GTiff", height=band.shape[0], width=band.shape[1], count=1, dtype="float32",
                  crs=crs, transform=transform, nodata=np.nan, **profile) as dst:
        dst.write(band.astype(np.float32, copy=False), 1)
        if tags:
            dst.update_tags(**tags)
    return tmp


def _write_averaged(path: str, band: np.ndarray, crs, transform, level: Optional[int] = None):
    """An averaged tile, atomically: float32 in AVERAGED_PROFILE, lossless, so a 2 m or 5 m tile stays GDAL's
    average of the 1 m tiles byte for byte, and the mirror's hashes in index.json stay those of the files on disk."""
    os.replace(_write_averaged_part(path, band, crs, transform, level=level), path)


def averaged_encoding(factor) -> str:
    """The encoding text of an averaged folder's index.json."""
    return (f"GeoTIFF float32 ZSTD (level {AVERAGED_PROFILE['zstd_level']}) with the floating point predictor, "
            f"lossless: the mean of the valid 1 m pixels of each {factor:g} x {factor:g} block "
            "(sources.readers.download._block_means)")


def is_zstd(path: str) -> bool:
    """Whether a tile is ZSTD-compressed already (from its header)."""
    with rio.open(path) as src:
        return (src.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION") or "").upper() == "ZSTD"


def _same_tile(a, b, band: np.ndarray) -> bool:
    """Whether the open raster b holds band and the georeference, nodata and tags of the open raster a, bit for bit."""
    if (b.count, b.dtypes, b.shape, b.crs, b.transform, b.tags()) != (a.count, a.dtypes, a.shape, a.crs, a.transform,
                                                                       a.tags()):
        return False
    if not (np.isnan(b.nodata) if a.nodata is not None and np.isnan(a.nodata) else b.nodata == a.nodata):
        return False
    return np.array_equal(b.read(1).view(np.uint32), band.view(np.uint32))


def _layout_root(folder: str) -> Optional[str]:
    """The cache folder above folder (the one with the LAYOUT file, cache.check_layout's), or None."""
    path = os.path.abspath(folder)
    while True:
        parent = os.path.dirname(path)
        if os.path.isfile(os.path.join(path, "LAYOUT")):
            return path
        if parent == path:
            return None
        path = parent


def _recompress_tile(path: str, cache_dir: Optional[str]) -> dict:
    """One averaged tile written again in AVERAGED_PROFILE (see recompress): {"status": "rewritten" | "skipped"
    | "failed", "before", "after" (bytes), "sha256" (of the file now), "error"}. In a cache under the tile's lock,
    the index row's sha256 made the file's (cache.reencoded) also for a file found in ZSTD already with another."""
    import contextlib
    import cache
    from sources.net import tile_lock
    before = os.path.getsize(path)
    lock = tile_lock(cache_dir, path) if cache_dir else contextlib.nullcontext()
    with lock:
        if is_zstd(path):
            digest = _sha256(path)
            if cache_dir and (cache.info(cache_dir, path) or {}).get("sha256") not in (None, digest):
                cache.reencoded(cache_dir, path)  # replaced before an interruption, its row not updated yet
            return dict(status="skipped", before=before, after=before, sha256=digest, error=None)
        tmp = None
        try:
            with rio.open(path) as src:
                if src.count != 1 or src.dtypes[0] != "float32":
                    raise ValueError(f"{src.count} band(s) of {src.dtypes[0]}: not an averaged tile")
                compression = src.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION") or ""
                if compression.upper().startswith("LERC"):  # a 1 m tile: ZSTD would keep LERC's error, larger
                    raise ValueError(f"{compression}: not an averaged tile")
                band = src.read(1)
                # the tags but AREA_OR_POINT, which the GeoTIFF keys hold already: given, it would go into
                # GDAL_METADATA too, and the file would differ from what average writes
                from sources.layer import copied_tags
                tmp = _write_averaged_part(path, band, src.crs, src.transform, copied_tags(src))
                with rio.open(tmp) as back:
                    if not _same_tile(src, back, band) or not is_zstd(tmp):
                        raise ValueError("the rewritten tile differs from the original")
            deadline = time.monotonic() + REPLACE_SECONDS
            while True:
                try:
                    os.replace(tmp, path)
                    tmp = None
                    break
                except PermissionError:  # open in another process (Windows)
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.2)
        except Exception as e:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            return dict(status="failed", before=before, after=before, sha256=None, error=f"{type(e).__name__}: {e}")
        if cache_dir:
            cache.reencoded(cache_dir, path)
        return dict(status="rewritten", before=before, after=os.path.getsize(path), sha256=_sha256(path), error=None)


def recompress(folder: str, threads: int = WRITE_THREADS) -> dict:
    """Write every averaged tile (.tif) under folder again in AVERAGED_PROFILE, losslessly (see the module's
    docstring): the files already in ZSTD skipped, each other one through a .part compared bit for bit before it
    replaces the file. A mirror's folder (index.json in it, which must be an averaged folder's): the tiles' sha256
    in the index (written every 30 s while it changes), and once no tile failed its encoding text and the dataset
    card beside the products; a folder in a cache: the index rows' sha256 (cache.reencoded). Returns the counts
    (files, rewritten, skipped, failed), the bytes before and after, the seconds and the failures ({path: error}),
    after printing a summary line."""
    start = time.time()
    folder = os.path.abspath(folder)
    paths = sorted(os.path.join(root, name) for root, _, names in os.walk(folder) for name in names
                   if name.endswith(".tif"))
    index_path = os.path.join(folder, "index.json")
    index = None
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        if "from_resolution" not in index:
            raise ValueError(f"{index_path}: not an averaged folder's index (no from_resolution)")
    cache_dir = None if index is not None else _layout_root(folder)
    kind = "a mirror's folder" if index is not None else (f"a folder of the cache {cache_dir}" if cache_dir
                                                           else "a folder")
    print(f"{folder}: {len(paths)} tiles, {kind}", flush=True)

    def save_index():
        with open(index_path + ".part", "w", encoding="utf-8") as f:
            json.dump(index, f)
        os.replace(index_path + ".part", index_path)

    def task(path):
        try:
            return _recompress_tile(path, cache_dir)
        except Exception as e:  # unreadable, its lock not had: listed and left
            size = os.path.getsize(path) if os.path.exists(path) else 0
            return dict(status="failed", before=size, after=size, sha256=None, error=f"{type(e).__name__}: {e}")

    counts = {"rewritten": 0, "skipped": 0, "failed": 0}
    before = after = corrected = unlisted = 0
    failed, dirty, last = {}, False, time.time()
    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        for n, (path, result) in enumerate(zip(paths, pool.map(task, paths)), 1):
            counts[result["status"]] += 1
            before += result["before"]
            after += result["after"]
            if result["status"] == "failed":
                failed[path] = result["error"]
            elif index is not None:
                key = os.path.basename(path)[:-len(".tif")]
                if index["tiles"].get(key) is None:
                    unlisted += 1  # a file the index does not name (or names as without data): left out of it
                elif index["tiles"][key] != result["sha256"]:
                    corrected += result["status"] == "skipped"  # replaced before an interruption
                    index["tiles"][key] = result["sha256"]
                    dirty = True
            if time.time() - last > 30 or n == len(paths):
                last = time.time()
                if dirty:
                    save_index()
                    dirty = False
                print(f"  {n}/{len(paths)} tiles, {counts['rewritten']} rewritten, {counts['failed']} failed, "
                      f"{(time.time() - start) / 60:.1f} min", flush=True)
    if index is not None and not failed:
        encoding = averaged_encoding(index["resolution"] / index["from_resolution"])
        if dirty or index.get("encoding") != encoding:
            index["encoding"] = encoding
            save_index()
        root = os.path.dirname(os.path.dirname(folder))
        if os.path.exists(os.path.join(root, "README.md")):
            write_card(root)
    elif dirty:
        save_index()
    seconds = time.time() - start
    print(f"{folder}: {len(paths)} files, {counts['rewritten']} rewritten, {counts['skipped']} already ZSTD, "
          f"{counts['failed']} failed; {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB; {seconds:.0f} s"
          + (f"; {corrected} index entries corrected" if corrected else "")
          + (f"; {unlisted} files not in the index" if unlisted else ""), flush=True)
    for path, error in failed.items():
        print(f"  failed: {path}: {error}", flush=True)
    return dict(files=len(paths), **counts, before=before, after=after, seconds=seconds, failures=failed,
                corrected=corrected, unlisted=unlisted)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cut(product: str, zips: str, root: str, rows_limit: Optional[int] = None):
    """Cut the TIFF (extracted, or else inside the ZIP) into 2 km tiles under root (skips
    rows already written; rows_limit stops after that many rows, for a timing trial)."""
    spec = PRODUCTS[product]
    source = extracted(product, zips)
    if not os.path.exists(source):
        source = f"/vsizip/{os.path.join(zips, os.path.basename(spec['zip']))}/{spec['member']}"
    out = os.path.join(root, tile_folder(product))
    index_path = os.path.join(out, "index.json")
    index = {"tiles": {}}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    start = time.time()
    with rio.Env(GDAL_CACHEMAX=CACHE_MB, GDAL_NUM_THREADS="ALL_CPUS"), rio.open(source) as src, \
            ThreadPoolExecutor(max_workers=WRITE_THREADS) as pool:
        assert abs(src.res[0] - 1.0) < 1e-9, f"expected 1 m, got {src.res[0]}"
        res = 1.0  # DMR 5.0 says 0.999999999998 m, its edges 0.1 mm off whole metres: the tiles get the exact grid
        left, bottom, right, top = src.bounds
        # The tile grid must fall on pixel edges (whole metres here)
        assert abs(left - round(left)) < 1e-3 and abs(top - round(top)) < 1e-3, src.bounds
        # DMP 1.0: "S-JTSK [JTSK03] / Krovak East North", DMR 5.0: "S_JTSK_JTSK03_Krovak_East_North"
        assert "SJTSKJTSK03KrovakEastNorth" in "".join(filter(str.isalnum, src.crs.to_wkt())), src.crs
        nodata = src.nodata
        rows = range(math.ceil(top / TILE_M) - 1, math.floor(bottom / TILE_M) - 1, -1)  # from the top
        cols = range(math.floor(left / TILE_M), math.ceil(right / TILE_M))
        print(f"{source}: {src.width} x {src.height} px, blocks {src.block_shapes[0]}, nodata {nodata}, "
              f"{len(rows)} x {len(cols)} tiles", flush=True)
        for n, j in enumerate(rows):
            if rows_limit is not None and n >= rows_limit:
                break
            todo = [i for i in cols if f"{i}_{j}" not in index["tiles"]]
            if not todo:
                continue
            # A 2 km band of the full width: the ZIP is read forwards only
            # (rasterio's boundless reads go through a warped VRT: the window is clipped here instead)
            row0 = round(top - (j + 1) * TILE_M)
            c0 = round((cols[0] * TILE_M - left) / res)
            band = np.full((TILE_M, len(cols) * TILE_M), np.nan, dtype=np.float32)
            r_in, c_in = max(row0, 0), max(c0, 0)
            r_end, c_end = min(row0 + TILE_M, src.height), min(c0 + len(cols) * TILE_M, src.width)
            part = src.read(1, window=Window(c_in, r_in, c_end - c_in, r_end - r_in), masked=True)
            band[r_in - row0:r_end - row0, c_in - c0:c_end - c0] = part.astype(np.float32).filled(np.nan)
            del part

            def save(i):
                tile = np.ascontiguousarray(band[:, (i - cols[0]) * TILE_M:(i - cols[0] + 1) * TILE_M])
                if not np.isfinite(tile).any():
                    return None  # no data: not uploaded
                path = os.path.join(out, tile_name(i, j))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                _write(path, tile, CRS, from_origin(i * TILE_M, (j + 1) * TILE_M, res, res))
                return _sha256(path)

            for i, digest in zip(todo, pool.map(save, todo)):
                index["tiles"][f"{i}_{j}"] = digest
            del band
            index.update(product=product, title=spec["title"], source=spec["zip"], crs=CRS,
                         heights="EPSG:8357 (Baltic 1957)", tile_m=TILE_M, resolution=res, block=BLOCK,
                         encoding=f"COG LERC_ZSTD, max_z_error {MAX_Z_ERROR} m", licence="CC-BY-4.0",
                         attribution="ÚGKK SR", created=datetime.date.today().isoformat())
            os.makedirs(out, exist_ok=True)
            with open(index_path + ".part", "w", encoding="utf-8") as f:
                json.dump(index, f)
            os.replace(index_path + ".part", index_path)
            done = sum(v is not None for v in index["tiles"].values())
            print(f"  row {n + 1}/{len(rows)}: {done} tiles with data, {(time.time() - start) / 60:.0f} min",
                  flush=True)
    write_card(root)
    print(f"done: {sum(v is not None for v in index['tiles'].values())} tiles in {(time.time() - start) / 60:.0f} min")


def average(product: str, root: str, factors=FACTORS):
    """The 1 m tiles under root averaged to each factor's resolution into <product>/<factor>m
    (skips the tiles in that folder's index already; the tiles without data are null there as in
    the 1 m index; the indexes written every 30 s and at the end)."""
    from affine import Affine
    from sources.readers.download import _block_means
    src_root = os.path.join(root, tile_folder(product))
    with open(os.path.join(src_root, "index.json"), encoding="utf-8") as f:
        source = json.load(f)
    if source.get("resolution", 1.0) != 1.0:
        sys.exit(f"{src_root}: tiles of {source.get('resolution')} m, 1 m expected")
    for factor in factors:
        if not isinstance(factor, int) or factor < 2 or TILE_M % factor:
            sys.exit(f"factor {factor!r}: a whole number above 1 dividing {TILE_M}")
    outs, indexes = {}, {}
    for factor in factors:
        outs[factor] = os.path.join(root, tile_folder(product, factor))
        path = os.path.join(outs[factor], "index.json")
        indexes[factor] = {"tiles": {}}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                indexes[factor] = json.load(f)
        indexes[factor].update({k: v for k, v in source.items() if k != "tiles"},
                               resolution=float(factor), from_resolution=1.0, encoding=averaged_encoding(factor),
                               created=datetime.date.today().isoformat())
    todo = {factor: {k for k in source["tiles"] if k not in indexes[factor]["tiles"]} for factor in factors}
    keys = sorted({k for ks in todo.values() for k in ks}, key=lambda k: (-int(k.split("_")[1]), int(k.split("_")[0])))
    print(f"{src_root}: {len(source['tiles'])} tiles, {len(keys)} to average by {', '.join(map(str, factors))}",
          flush=True)

    def save_index(factor):
        path = os.path.join(outs[factor], "index.json")
        os.makedirs(outs[factor], exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump(indexes[factor], f)
        os.replace(path + ".part", path)

    def work(key):
        i, j = map(int, key.split("_"))
        digest = source["tiles"][key]
        wanted = [f for f in factors if key in todo[f]]
        if digest is None:
            return key, {f: None for f in wanted}
        with rio.open(os.path.join(src_root, tile_name(i, j))) as s:
            values = s.read(1, masked=True).astype(np.float64).filled(np.nan)
            crs, transform = s.crs, s.transform
        found = {}
        for f in wanted:
            path = os.path.join(outs[f], tile_name(i, j))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _write_averaged(path, _block_means(values, f).astype(np.float32), crs, transform @ Affine.scale(f))
            found[f] = _sha256(path)
        return key, found

    start, last = time.time(), time.time()
    with ThreadPoolExecutor(max_workers=WRITE_THREADS) as pool:
        for n, (key, found) in enumerate(pool.map(work, keys), 1):
            for f, digest in found.items():
                indexes[f]["tiles"][key] = digest
            if time.time() - last > 30 or n == len(keys):
                last = time.time()
                for f in factors:
                    save_index(f)
                print(f"  {n}/{len(keys)} tiles, {(time.time() - start) / 60:.1f} min", flush=True)
    for f in factors:
        save_index(f)
        done = sum(v is not None for v in indexes[f]["tiles"].values())
        size = sum(os.path.getsize(os.path.join(outs[f], tile_name(*map(int, k.split("_")))))
                   for k, v in indexes[f]["tiles"].items() if v is not None)
        print(f"{outs[f]}: {done} tiles with data, {size / 1e9:.2f} GB")
    write_card(root)
    print(f"done in {(time.time() - start) / 60:.1f} min")


CARD = """---
license: cc-by-4.0
pretty_name: Slovakia ALS elevation models (ÚGKK SR) as 2 km tiles
tags: [geospatial, elevation, lidar, slovakia]
---
# Slovakia ALS elevation models as 2 km tiles

Tiles of the digital terrain model **DMR 5.0** and digital surface model **DMP 1.0** of the
Slovak airborne laser scanning project (1st cycle, 2017–2023), 1 m, made from the files
published by **ÚGKK SR** (Úrad geodézie, kartografie a katastra Slovenskej republiky) at
https://www.skgeodesy.sk/geoportal-en/zbgis/als/ under **CC BY 4.0**
(https://creativecommons.org/licenses/by/4.0/). Source: © ÚGKK SR.

Changes made: the national rasters (S-JTSK [JTSK03] EPSG:8353, Baltic 1957 heights EPSG:8357)
were cut into 2 km × 2 km Cloud Optimized GeoTIFFs on the same pixel grid and stored with
LERC compression with a maximum error of 5 mm. Values are not otherwise changed.

Layout: `<product>/1m/<E//10>_<N//10>/<E>_<N>.tif`, where E = floor(x / 2000) and
N = floor(y / 2000) of the tile's lower left corner; `<product>/1m/index.json` lists every tile
with its sha256. `<product>/2m` and `<product>/5m` hold the same tiles at 2 m and 5 m: each
pixel the mean of the valid 1 m pixels of its 2 × 2 or 5 × 5 block, stored as float32 GeoTIFF
(ZSTD with the floating-point predictor) without further loss, with their own `index.json`.
Made for Find-a-Line (a highline finder); not endorsed by ÚGKK SR.
"""


def write_card(root: str):
    """The dataset card (README.md) next to the product folders: the licence and attribution
    travel with the tiles, in the local mirror as on Hugging Face."""
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
        f.write(CARD)


def upload(product: str, root: str, repo: str):
    """Upload the tiles and the index (resumable; needs a write token in HF_TOKEN).

    To a dataset repository, as decided in the roadmap; a Storage Bucket (like FABDEM's)
    is still open: then only the destination of this call changes, not the layout."""
    from huggingface_hub import HfApi
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN to a Hugging Face token with write access")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    write_card(root)
    # With hf_xet (installed with huggingface_hub 2.x) a large folder goes in several commits,
    # and running the same call again resumes it
    api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=root,
                      allow_patterns=[f"{tile_folder(product)}/**", "README.md"]
                      + [f"{tile_folder(product, f)}/**" for f in FACTORS],
                      commit_message=f"{product}: 2 km tiles")
    print(f"uploaded {product} to https://huggingface.co/datasets/{repo}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["download", "extract", "cut", "average", "recompress", "upload"])
    parser.add_argument("product", metavar="product|folder",
                        help=f"the product ({', '.join(PRODUCTS)}); recompress: an averaged folder (more may follow)")
    parser.add_argument("folders", nargs="*", help="recompress: more averaged folders")
    parser.add_argument("--zips", help="folder of the ZIPs (download, cut)")
    parser.add_argument("--out", help="folder of the tiles, laid out as the dataset (cut, average, upload)")
    parser.add_argument("--work", help="the same as --zips WORK --out WORK/tiles")
    parser.add_argument("--rows", type=int, help="cut: stop after this many rows (a timing trial)")
    parser.add_argument("--factors", type=int, nargs="+", default=list(FACTORS),
                        help=f"average: the factors of the 1 m tiles to write (default {' '.join(map(str, FACTORS))})")
    parser.add_argument("--repo", help="Hugging Face dataset, user/name (upload)")
    parser.add_argument("--threads", type=int, default=WRITE_THREADS,
                        help=f"recompress: tiles at a time (default {WRITE_THREADS})")
    args = parser.parse_args()
    if args.step == "recompress":
        failed = 0
        for folder in [args.product] + args.folders:
            if not os.path.isdir(folder):
                sys.exit(f"{folder}: no such folder")
            try:
                failed += recompress(folder, args.threads)["failed"]
            except ValueError as e:
                sys.exit(str(e))
        sys.exit(1 if failed else 0)
    if args.product not in PRODUCTS or args.folders:
        parser.error(f"one product is needed: {', '.join(PRODUCTS)}")
    zips = args.zips or args.work
    out = args.out or (os.path.join(args.work, "tiles") if args.work else None)
    if args.step in ("download", "extract", "cut") and not zips:
        sys.exit("--zips (or --work) is needed")
    if args.step in ("cut", "average", "upload") and not out:
        sys.exit("--out (or --work) is needed")
    if args.step == "download":
        os.makedirs(zips, exist_ok=True)
        download(args.product, zips)
    elif args.step == "extract":
        extract(args.product, zips)
    elif args.step == "cut":
        cut(args.product, zips, out, args.rows)
    elif args.step == "average":
        average(args.product, out, tuple(args.factors))
    else:
        if not args.repo:
            sys.exit("--repo user/name is needed for the upload")
        upload(args.product, out, args.repo)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
