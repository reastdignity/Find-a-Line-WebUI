"""
Run by hand: what the blocks of a layer read by windows of big remote files (sources/readers/windows.py:
FileBlocks, the USGS blocks, Scotland's) really cost in bytes and requests (docs/performance.md, "Window
reads").

For each mode a child process with a new data folder under <out> (cache/LAYOUT only: the real cache is never
written) downloads the layer's blocks over the grid of a circle through sources.download_layers, as a search
does; GDAL's network statistics (CPL_VSIL_NETWORK_STATS_ENABLED, read through the GDAL library rasterio
carries) give the bytes and requests. Then the files' headers give what their internal tiles predict: summed
per block (each block reads every tile it touches) and each tile once (the files' own density).

    uv run tools/perf_window_reads.py --out <scratch> --source austria --lat 47.305 --lon 11.385 --radius 800 \\
        --mode blocks --mode cache=256 --mode cache=256,order=squares

Modes, options joined by commas:
  blocks          the blocks as a search reads them today
  cache=<MB>      GDAL's cache of downloaded ranges (CPL_VSIL_CURL_CACHE_SIZE, 16 MB by default)
  order=squares   the blocks handed to the pool in squares of SQUARE x SQUARE blocks
  order=tasks     each square one task of the pool, its blocks read one after another by one thread
                  (Layer._download_and_record each, as download_layers does)
  threads=<n>     sources.layer.DOWNLOAD_THREADS
  group=<m>       the blocks in squares of m metres, each file read once per square through our own range
                  requests, as the country prefetch reads them (sources.download_layers(group_m=))
  serial=<0|1>    the layer read range by range through GDAL's cache, in squares (1), or with one multi-range
                  request per block (0), whatever the catalogue says (Windows(serial=))
  gdalthreads=<n> GDAL_NUM_THREADS of sources.net._gdal_http (1: the app's, so that no error of GDAL's own
                  threads goes unseen; more lets GTiff fetch all the tiles of a window in one multi-range read)
  multirange=<v>  GDAL_HTTP_MULTIRANGE of sources.net._gdal_http (YES: the app's, several ranges in one
                  request; NO, SERIAL, PARALLEL)
Only the first file of a block is predicted (a block reads an older one only where the newer has no data).
"""

import argparse
import ctypes
import glob
import json
import math
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

SQUARE = 4  # blocks a side of the squares of order=squares
OPTIONS = {"cache": int, "order": str, "threads": int, "multirange": str, "group": float, "gdalthreads": int, "serial": int}


def parse_mode(text: str) -> Dict:
    """The options of a mode ("blocks", "cache=256,order=squares"): {name: value}."""
    mode = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        if part == "blocks":
            continue
        name, sep, value = part.partition("=")
        if not sep or name not in OPTIONS:
            raise ValueError(f"unknown option {part!r} (blocks, {', '.join(f'{n}=' for n in OPTIONS)})")
        mode[name] = OPTIONS[name](value)
        if name == "order" and value not in ("squares", "tasks"):
            raise ValueError("order=squares or order=tasks")
    return mode


def slug(mode: Dict) -> str:
    return "-".join(f"{k}{v}" for k, v in sorted(mode.items())) or "blocks"


def gdal_library() -> ctypes.CDLL:
    """The GDAL library of the rasterio in use (its wheel's rasterio.libs or .dylibs)."""
    import rasterio
    package = os.path.dirname(rasterio.__file__)
    for pattern in ("rasterio.libs/gdal*.dll", "rasterio.libs/libgdal*.so*", "rasterio/.dylibs/libgdal*.dylib"):
        found = glob.glob(os.path.join(os.path.dirname(package), pattern))
        if found:
            lib = ctypes.CDLL(found[0])
            lib.VSINetworkStatsGetAsSerializedJSON.restype = ctypes.c_void_p
            lib.VSINetworkStatsGetAsSerializedJSON.argtypes = [ctypes.c_void_p]
            return lib
    raise RuntimeError(f"no GDAL library next to {package}")


def network_stats(lib) -> Dict:
    """GDAL's network statistics since the last VSINetworkStatsReset (JSON)."""
    p = lib.VSINetworkStatsGetAsSerializedJSON(None)
    return json.loads(ctypes.string_at(p).decode()) if p else {}


def downloaded(stats: Dict) -> Dict[str, int]:
    """Bytes of GET and the number of GET and HEAD requests of all files in the statistics."""
    methods = stats.get("methods", {})
    return {"bytes": methods.get("GET", {}).get("downloaded_bytes", 0),
            "gets": methods.get("GET", {}).get("count", 0),
            "heads": methods.get("HEAD", {}).get("count", 0)}


def in_squares(layer, tiles: Sequence, blocks: int = SQUARE) -> list:
    """The tiles in squares of blocks x blocks (sources.layer.squares on the size of the first tile's request),
    each square's in their order: neighbours are read one after another."""
    import sources
    if not tiles:
        return []
    r = layer.index.request(tiles[0])
    return [t for square in sources.layer.squares(layer, tiles, abs(r.transform.a) * r.shape[1] * blocks)
            for t in square]


def _square_tasks(layer, tiles: Sequence, cache_dir: str, blocks: int = SQUARE):
    """The blocks downloaded by a pool of DOWNLOAD_THREADS whose tasks are squares of blocks x blocks, each
    square's blocks one after another in its thread (Layer._download_and_record each)."""
    from concurrent.futures import ThreadPoolExecutor
    import sources
    r = layer.index.request(tiles[0])
    squares = sources.layer.squares(layer, tiles, abs(r.transform.a) * r.shape[1] * blocks)

    def task(square):
        for tile in square:
            layer._download_and_record(tile, cache_dir, None, True, "terrain")
    with ThreadPoolExecutor(max_workers=sources.layer.DOWNLOAD_THREADS) as pool:
        list(pool.map(task, squares))


class _TiffTags:
    """A file's GDAL dataset opened through GDAL's C API (ctypes: every call releases the GIL) for its items of the
    TIFF domain (BLOCK_SIZE_x_y): GTiff loads its arrays of tile sizes on demand, an HTTP request for a tile beyond
    the bytes fetched so far, which rasterio's get_tag_item (GDALGetMetadataItem, rasterio 1.5.2) would make holding
    the GIL. The same GDAL function, so the same values: None for a tile without bytes (sparse) or outside the file,
    and None with an error GDAL signals (net.gdal_errors sees it: its handler is rasterio's) when the array's bytes
    could not be fetched (a timeout, an answer cut short; a later lookup asks again)."""

    def __init__(self, lib: ctypes.CDLL, path: str):
        lib.GDALOpenEx.restype = ctypes.c_void_p
        lib.GDALOpenEx.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        lib.GDALGetRasterBand.restype = ctypes.c_void_p
        lib.GDALGetRasterBand.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.GDALGetMetadataItem.restype = ctypes.c_char_p
        lib.GDALGetMetadataItem.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.GDALClose.restype = ctypes.c_int
        lib.GDALClose.argtypes = [ctypes.c_void_p]
        self.lib = lib
        self.handle = lib.GDALOpenEx(path.encode("utf-8"), 0x02 | 0x40, None, None, None)  # raster, verbose errors
        if not self.handle:
            raise RuntimeError(f"GDAL could not open {path}")
        self.band = lib.GDALGetRasterBand(self.handle, 1)

    def item(self, name: str) -> Optional[str]:
        value = self.lib.GDALGetMetadataItem(self.band, name.encode("ascii"), b"TIFF")
        return value.decode() if value is not None else None

    def close(self):
        if self.handle:
            self.lib.GDALClose(self.handle)
            self.handle = None


def predicted(layer, tiles: Sequence) -> Dict:
    """The bytes the files' internal tiles predict for the blocks (first file of each): summed per block
    and each tile once, from the files' headers (requests of their own: after the measurement), the tiles' sizes
    read with the GIL released (_TiffTags). A size GDAL could not read (it signalled an error: the bytes of its
    array not fetched) raises RuntimeError naming the file and the tile, never a 0 in the sum (the child process
    fails, as when the measurement fails: no table); a tile without bytes or outside the file counts 0 as ever."""
    import numpy as np
    import cache
    import rasterio as rio
    from rasterio.windows import from_bounds
    from sources import net
    lib = gdal_library()
    per_block, union, tile_px = 0, {}, set()
    with net._gdal_http():
        opened, tags = {}, {}
        try:
            for tile in tiles:
                r = layer.index.request(tile)
                if not r.files:
                    continue
                url = r.files[0][1]
                if url not in opened:
                    opened[url] = rio.open(net._remote(url))
                    tags[url] = _TiffTags(lib, net._remote(url))
                src = opened[url]
                h, w = r.shape
                left, top = r.transform.c, r.transform.f
                right, bottom = left + w * r.transform.a, top + h * r.transform.e
                bh, bw = src.block_shapes[0]
                tile_px.add(bw)
                win = from_bounds(left, bottom, right, top, src.transform)
                c1, r1 = max(0, math.floor(win.col_off)), max(0, math.floor(win.row_off))
                c2 = min(src.width, math.ceil(win.col_off + win.width))
                r2 = min(src.height, math.ceil(win.row_off + win.height))
                for ty in range(r1 // bh, (r2 - 1) // bh + 1):
                    for tx in range(c1 // bw, (c2 - 1) // bw + 1):
                        if (url, tx, ty) not in union:
                            with net.gdal_errors() as errors:
                                size = tags[url].item(f"BLOCK_SIZE_{tx}_{ty}")
                            if errors:
                                raise RuntimeError(f"{cache.clean_url(url)}: the size of its tile {tx}, {ty} not read: "
                                                   f"{cache.clean_error('; '.join(dict.fromkeys(errors)))}")
                            union[(url, tx, ty)] = int(size or 0)
                        per_block += union[(url, tx, ty)]
        finally:
            for src in opened.values():
                src.close()
            for t in tags.values():
                t.close()
    return {"per_block": per_block, "each_tile_once": sum(union.values()), "file_tiles": len(union),
            "tile_px": sorted(tile_px)}


def cached(folder: str) -> Dict:
    """Bytes of the cached blocks and the km² with data in them."""
    import numpy as np
    import rasterio as rio
    total, km2, files = 0, 0.0, 0
    for root, _, names in os.walk(folder):
        for name in names:
            if name.endswith(".tif"):
                path = os.path.join(root, name)
                total, files = total + os.path.getsize(path), files + 1
                with rio.open(path) as src:
                    band = src.read(1)
                    km2 += np.count_nonzero(np.isfinite(band)) * abs(src.transform.a * src.transform.e) / 1e6
    return {"bytes": total, "km2": km2, "files": files}


def peak_memory() -> int:
    import psutil
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):
        return info.peak_wset
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # macOS gives bytes, Linux KB


def measure_layer(layer, grid, cache_dir: str, mode: Dict, lib=None, predict: bool = True) -> Dict:
    """Download the layer's blocks over the grid into cache_dir in a mode (parse_mode; its cache size set in
    the environment before GDAL started) and measure it."""
    import sources
    lib = lib or gdal_library()
    if hasattr(layer, "_use"):  # an indexed layer (USGS, Scotland): its index's cache folder for tiles()
        layer._use(cache_dir)
    tiles = layer.tiles(grid)
    if mode.get("order") == "squares":
        squares = in_squares(layer, tiles)
        layer.tiles = lambda g: squares if g is grid else type(layer).tiles(layer, g)
    if "threads" in mode:
        sources.layer.DOWNLOAD_THREADS = mode["threads"]
    if "serial" in mode:
        layer.reader.serial = bool(mode["serial"])
    if "multirange" in mode or "gdalthreads" in mode:
        from sources import net
        from sources.readers import windows
        app_env = net._gdal_http

        def gdal_http(*args, **kwargs):
            env = app_env(*args, **kwargs)
            if "multirange" in mode:
                env.options["GDAL_HTTP_MULTIRANGE"] = mode["multirange"]
            if "gdalthreads" in mode:
                env.options["GDAL_NUM_THREADS"] = str(mode["gdalthreads"])
            return env
        net._gdal_http = windows._gdal_http = gdal_http
    # Our own range requests (the groups: sources/readers/ranges.py) besides GDAL's
    from sources.readers import ranges
    own = {"bytes": 0, "gets": 0}
    app_get_range = ranges.get_range

    def get_range(url, first, last):
        data, size = app_get_range(url, first, last)
        own["bytes"], own["gets"] = own["bytes"] + len(data), own["gets"] + 1
        return data, size
    ranges.get_range = get_range
    lib.VSINetworkStatsReset()
    started = time.monotonic()
    if mode.get("order") == "tasks":
        _square_tasks(layer, tiles, cache_dir)
    else:
        sources.download_layers([(layer, "terrain")], grid, cache_dir, None, group_m=mode.get("group"))
    seconds = time.monotonic() - started
    ranges.get_range = app_get_range
    network = downloaded(network_stats(lib))
    network["bytes"] += own["bytes"]
    network["gets"] += own["gets"]
    result = {"mode": slug(mode), "blocks": len(tiles), "seconds": seconds,
              "network": network, "peak_memory": peak_memory(),
              "cache": cached(os.path.join(cache_dir, layer.folder))}
    if predict:
        result["predicted"] = predicted(layer, tiles)
    return result


def child(spec: Dict):
    """One mode in this process (its environment set by the parent): the data folder, the plan, the layer."""
    import cache
    import params as pm
    import search
    import sources
    data = spec["data"]
    os.makedirs(os.path.join(data, "cache"), exist_ok=True)
    with open(os.path.join(data, "cache", "LAYOUT"), "w") as f:
        f.write(str(cache.LAYOUT))
    (params,), _ = pm.parse_cli(["--lat", str(spec["lat"]), "--lon", str(spec["lon"]), "--radius",
                                 str(spec["radius"]), "--source", spec["source"], "--resolution",
                                 str(spec["resolution"])])
    plan = search.plan_search(params, search.Paths(data, cache.new_work(data)))
    layer = getattr(sources.SOURCES[spec["source"]], spec["layer"])
    result = measure_layer(layer, plan.grid, os.path.join(data, "cache"), spec["mode"], predict=spec["predict"])
    result.update(source=spec["source"], layer=spec["layer"])
    with open(os.path.join(data, "result.json"), "w") as f:
        json.dump(result, f, indent=1)


def table(results: List[Dict]) -> str:
    lines = ["| Source | Mode | Blocks | Downloaded MB | MB/km² | GET | HEAD | Cached MB | Down/cache | Seconds | "
             "Peak MB | Predicted per block / each tile once MB |", "|" + " --- |" * 12]
    for r in results:
        km2 = r["cache"]["km2"] or float("nan")
        mb = r["network"]["bytes"] / 1e6
        p = r.get("predicted")
        pred = f"{p['per_block'] / 1e6:.1f} / {p['each_tile_once'] / 1e6:.1f}" if p else "-"
        lines.append(f"| {r['source']} | {r['mode']} | {r['blocks']} | {mb:.1f} | {mb / km2:.2f} | "
                     f"{r['network']['gets']} | {r['network']['heads']} | {r['cache']['bytes'] / 1e6:.1f} | "
                     f"{r['network']['bytes'] / max(r['cache']['bytes'], 1):.2f} | {r['seconds']:.1f} | "
                     f"{r['peak_memory'] / 2 ** 20:.0f} | {pred} |")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None):
    if argv is None and sys.argv[1:2] == ["_child"]:
        return child(json.loads(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="folder for the data folders of the modes and results.json")
    parser.add_argument("--source", required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=float, default=800, help="metres (800: 12 blocks of 1 km)")
    parser.add_argument("--layer", choices=("nmt", "nmpt"), default="nmt")
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--mode", action="append", default=[], help="see the modes above (repeatable)")
    parser.add_argument("--no-predict", action="store_true", help="skip the prediction from the files' headers")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    modes = [parse_mode(m) for m in (args.mode or ["blocks"])]
    results = []
    for mode in modes:
        data = os.path.join(args.out, f"{args.source}-{args.layer}-{slug(mode)}")
        if os.path.exists(data):
            raise SystemExit(f"{data} exists: a new --out or delete it")
        env = dict(os.environ, CPL_VSIL_NETWORK_STATS_ENABLED="YES", PYTHONIOENCODING="utf-8")
        if "cache" in mode:
            env["CPL_VSIL_CURL_CACHE_SIZE"] = str(mode["cache"] * 2 ** 20)
        spec = dict(vars(args), mode=mode, data=data, predict=not args.no_predict)
        print(f"--- {args.source} {args.layer}: {slug(mode)}", flush=True)
        subprocess.run([sys.executable, os.path.abspath(__file__), "_child", json.dumps(spec)], env=env, check=True)
        with open(os.path.join(data, "result.json")) as f:
            results.append(json.load(f))
    with open(os.path.join(args.out, f"results-{args.source}-{args.layer}.json"), "w") as f:
        json.dump(results, f, indent=1)
    print(table(results))


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
