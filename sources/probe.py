"""The source probe (`findaline.py sources check [ID ...] [--deep]`): whether every source's services
still answer, a few small requests each.

Per source and layer, at the source's sample point (Source.sample) on a tiny grid:
- index: the layer's own index asked (Layer.estimate into a temporary cache): no answer (the
  layer falls back to its cached files, tiles() is None) or no tile there fails; a WCS gets its
  DescribeCoverage, an ArcGIS ImageServer its description (f=json); fixed tilings (1° tiles, our
  own grid tiles, blocks) have no index;
- read: the first tile's file asked for one byte (Range: bytes=0-0); a WCS a GetCoverage of
  16 x 16 pixels, an ImageServer an exportImage of 16 x 16 pixels (a TIFF, not an error); blocks
  of big fixed files (FileBlocks) a window of 16 x 16 pixels of the first block's file; a local
  mirror is looked for on disk;
- --deep: the first tile downloaded (Layer.download_tile into the temporary folder) and checked
  for data;
- the orthophoto: one base tile at the sample, or the WMS's GetCapabilities.

Nothing is written to the cache: index answers and files go to a temporary folder, deleted at
the end; the requests of the probe itself take a slot of their host in the real data folder
(host_slot; its lock files are not data) and wait for their turn where the host has a rate
(net.rate_turn). Sources are probed one after another, each within
TIMEOUT_S (two minutes: swisstopo's STAC pages alone take about 40 s at its rate of 36 a
minute, longer while another search downloads from it). Skipped: a source that cannot be used here (Slovakia without its mirror), one without
a sample point, and nasadem unless named and an OpenTopography key is set (its calls are
limited to 50 a day).
"""

import contextlib
import io
import sys
import math
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
import requests
from rasterio.warp import transform as warp

import cache
from grid import make_grid

from . import net
from .net import _gdal_http, _remote, host_slot
from .layer import Layer
from .source import OrthoService, Source
from .layers.wcs import WcsTiles
from .layers.imageserver import ImageServerTiles
from .readers.imageserver import TIFF_MAGIC, service_error
from .layers.degree import DegreeTiles, OpenTopographyTiles
from .layers.indexed import IndexedTiles
from .layers.blocks import DegreeBlocks
from .layers.fileblocks import FileBlocks
from .readers.windows import _forget, _read_window, _same_crs
from .layers.gridtiles import GridTiles
from .readers.tilebases import grid_tile_name
from .layers.files import FileLayer
from .catalogue import SOURCES
from .choose import source_unavailable

TIMEOUT_S = 120         # per source (the turns of hosts with a rate included: net.HOST_RATES_OF)
REQUEST_TIMEOUT_S = 30  # per request of the probe itself
GRID_HALF_M = 50        # the tiny grid: this many metres around the sample, at least two pixels
ORTHO_ZOOM = 15         # the zoom of the orthophoto's base tile asked for

# How each kind of layer is probed; a new kind needs its entry (tests/test_probe.py)
STRATEGIES: Sequence[Tuple[type, str]] = (
    (WcsTiles, "wcs"), (OpenTopographyTiles, "api"), (IndexedTiles, "index"), (DegreeTiles, "tiles"),
    (DegreeBlocks, "tiles"), (FileBlocks, "window"), (GridTiles, "tiles"), (FileLayer, "file"),
    (ImageServerTiles, "imageserver"))
WINDOW_PX = 16          # the window read of a FileBlocks layer
OK, FAILED, NONE, SKIPPED = "ok", "FAIL", "-", "skip"


class _PerThread(io.TextIOBase):
    """sys.stdout during a probe: what a thread captures (_captured) goes to its buffer, the rest
    through. contextlib.redirect_stdout would also take the table's lines while the thread of a
    source that ran out of time still prints."""

    def __init__(self, out):
        self.out, self.buffers = out, {}

    def write(self, text: str) -> int:
        buffer = self.buffers.get(threading.get_ident())
        return (buffer or self.out).write(text)

    def flush(self):
        if not getattr(self.out, "closed", False):  # also called when this is collected, maybe after out was closed
            self.out.flush()


@contextlib.contextmanager
def _captured(buffer: io.StringIO):
    """What this thread prints, into buffer (the reason a layer gives for not using its index)."""
    out = sys.stdout
    if not isinstance(out, _PerThread):
        with contextlib.redirect_stdout(buffer):
            yield
        return
    out.buffers[threading.get_ident()] = buffer
    try:
        yield
    finally:
        out.buffers.pop(threading.get_ident(), None)


def strategy(layer: Layer) -> Optional[str]:
    return next((name for cls, name in STRATEGIES if isinstance(layer, cls)), None)


@dataclass
class Row:
    """One line of the table: a layer (or the orthophoto) of a source."""
    source: str
    what: str              # terrain, surface, orthophoto
    index: str = NONE
    read: str = NONE
    seconds: float = 0.0
    notes: List[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return FAILED in (self.index, self.read)


def _http(url: str, params=None, headers: Optional[Dict] = None) -> Tuple[int, str, bytes]:
    """GET (streamed): status, content type and the first KB of the body. Patched by the tests."""
    with requests.get(url, params=params, headers={**cache.http_headers(), **(headers or {})},
                      timeout=REQUEST_TIMEOUT_S, stream=True) as response:
        return response.status_code, response.headers.get("content-type", ""), next(response.iter_content(1024), b"")


def _ask(cache_dir: str, url: str, params=None, headers: Optional[Dict] = None) -> Tuple[int, str, bytes]:
    with host_slot(cache_dir, url):
        net.rate_turn(url)
        return _http(url, params, headers)


def _grid(source: Source):
    lat, lon = source.sample
    crs = source.working_crs(lat, lon)
    (x,), (y,) = warp("EPSG:4326", crs, [lon], [lat])
    res = source.default_resolution
    half = max(GRID_HALF_M, 2 * res)
    return make_grid((x - half, y - half, x + half, y + half), res, crs, source.grid_origin)


def _first_url(layer: Layer, tile) -> Optional[str]:
    url = layer.tile_url(tile)
    if isinstance(layer, GridTiles) and url:
        url = f"{url}/{grid_tile_name(*tile)}"  # tile_url gives the base (a host or the mirror)
    return url


def _read(cache_dir: str, url: Optional[str]) -> str:
    """One byte of a file, or that a local copy exists; raises with the reason."""
    if not url:
        raise RuntimeError("no address for the first tile")
    if not url.startswith(("http://", "https://")):
        if not os.path.exists(url):
            raise RuntimeError(f"{url} does not exist")
        return "local copy"
    status, kind, _ = _ask(cache_dir, url, headers={"Range": "bytes=0-0"})
    if status not in (200, 206):
        raise RuntimeError(f"HTTP {status} for {cache.clean_url(url)}")
    return ""


def _window(cache_dir: str, layer: FileBlocks, tile) -> str:
    """WINDOW_PX x WINDOW_PX pixels at the top left of a block, from its first file; raises with the
    reason. A read GDAL could not complete although it returned (net.gdal_errors: what it could not
    fetch comes back as nodata or zeros) fails with GDAL's error, never as a share of the window."""
    request = layer.index.request(tile)
    if not request.files:
        raise RuntimeError("no file for the first block")
    name, url, _ = request.files[0]
    try:
        with host_slot(cache_dir, url), _gdal_http(), net.gdal_errors() as errors:
            net.rate_turn(url)  # the window read counts as one request (net.HOST_RATES_OF)
            with rio.open(_remote(url)) as remote:
                if remote.crs is not None and not _same_crs(remote.crs, request.crs):
                    raise RuntimeError(f"{name} is in {remote.crs.to_string()}, not {request.crs}")
                values = _read_window(remote, request.transform, (WINDOW_PX, WINDOW_PX))
        if errors:
            raise RuntimeError(f"{name} not read completely: " + "; ".join(dict.fromkeys(errors)))
    except (RuntimeError, rio.errors.RasterioError):
        _forget(url)  # not the short answer again from GDAL's cache, should this process read it later
        raise
    share = float(np.isfinite(values).mean())
    if not share:
        raise RuntimeError(f"no data in a window of {name}")
    return f"window {100 * share:.0f}% with data"


def _coverage(cache_dir: str, layer: WcsTiles, lat: float, lon: float) -> Tuple[str, str]:
    """DescribeCoverage, then a GetCoverage of 16 x 16 pixels at the point, as the layer's reader
    asks them (its WCS version, its parameters and keys: WcsReader.describe_params, coverage_params)."""
    status, _, body = _ask(cache_dir, layer.url, layer.reader.describe_params())
    if status != 200 or b"Exception" in body:
        raise RuntimeError(f"DescribeCoverage: HTTP {status} {body[:200].decode('utf-8', 'replace').strip()}")
    (x,), (y,) = warp("EPSG:4326", layer.crs, [lon], [lat])
    x, y = x - layer.shift[0], y - layer.shift[1]  # where the service puts the data
    res = layer.fetch_res or layer.native_res
    half = 8 * res
    status, kind, body = _ask(cache_dir, layer.url, layer.reader.coverage_params(x - half, y - half, x + half,
                                                                                y + half, res))
    if status != 200 or "xml" in kind.split(";")[0]:
        raise RuntimeError(f"GetCoverage: HTTP {status} {body[:200].decode('utf-8', 'replace').strip()}")
    return OK, OK


def _image_service(cache_dir: str, layer: ImageServerTiles, lat: float, lon: float) -> Tuple[str, str]:
    """The service's description (f=json), then an exportImage of 16 x 16 pixels at the point on the
    layer's pixels, as its reader asks it (ImageServerReader.export_params): a TIFF, never an error (ArcGIS
    sends those with HTTP 200 as an image)."""
    status, _, body = _ask(cache_dir, layer.url, {"f": "json"})
    if status != 200 or not body.lstrip().startswith(b"{") or b'"error"' in body:
        raise RuntimeError(f"description: HTTP {status} {body[:200].decode('utf-8', 'replace').strip()}")
    (x,), (y,) = warp("EPSG:4326", layer.crs, [lon], [lat])
    res, (ox, oy) = layer.native_res, layer.origin
    left, bottom = math.floor((x - ox) / res - 8) * res + ox, math.floor((y - oy) / res - 8) * res + oy
    reader = layer.reader
    status, _, body = _ask(cache_dir, reader.export_url,
                           reader.export_params(left, bottom, left + 16 * res, bottom + 16 * res, res))
    if status != 200 or body[:4] not in TIFF_MAGIC:
        raise RuntimeError(f"exportImage: HTTP {status} {service_error(body)[1]}")
    return OK, OK


def _deep(cache_dir: str, layer: Layer, tile, folder: str) -> str:
    path = os.path.join(folder, "deep", "tile.tif")
    with host_slot(cache_dir, layer.tile_url(tile)):
        fetched = layer.download_tile(tile, path)
    if not os.path.exists(path):
        raise RuntimeError(f"the first tile has no data ({fetched.received} bytes)")
    with rio.open(path) as raster:
        values = raster.read(1, masked=True).filled(np.nan).astype(np.float32)
    share = float(np.isfinite(values).mean())
    os.remove(path)
    if not share:
        raise RuntimeError("the first tile has no data")
    return f"tile {fetched.received / 1e6:.1f} MB, {100 * share:.0f}% with data"


def probe_layer(source: Source, layer: Layer, what: str, cache_dir: str, folder: str, deep: bool) -> Row:
    """Index and read of one layer; errors go into the notes."""
    row = Row(source.id, what)
    start = time.monotonic()
    kind = strategy(layer)
    lat, lon = source.sample
    try:
        if kind is None:
            raise RuntimeError(f"no probe for a {type(layer).__name__}")
        if kind == "file":
            return row
        if kind in ("wcs", "imageserver"):
            try:
                ask = _coverage if kind == "wcs" else _image_service
                row.index, row.read = ask(cache_dir, layer, lat, lon)
            except (requests.RequestException, RuntimeError) as e:
                row.index = FAILED
                row.notes.append(cache.clean_error(e))
            if deep and row.index == OK:
                tiles = layer.tiles(_grid(source))
                row.notes.append(_deep(cache_dir, layer, tiles[0], folder))
            return row
        grid = _grid(source)
        printed = io.StringIO()
        try:
            with _captured(printed):
                layer.estimate(grid, os.path.join(folder, "cache"), None)
            tiles = layer.tiles(grid)
        except (requests.RequestException, RuntimeError, ValueError, OSError) as e:
            tiles = None
            printed.write(cache.clean_error(e))
        if kind == "index":
            row.index = OK if tiles else FAILED
            if not tiles:
                row.notes.append(printed.getvalue().strip() or "no tile at the sample point")
                return row
        elif not tiles:
            row.read = FAILED
            row.notes.append(printed.getvalue().strip() or "no tile at the sample point")
            return row
        if kind == "api" and not deep:
            row.notes.append("read only with --deep (the key's calls are limited)")
            return row
        try:
            if deep:
                row.notes.append(_deep(cache_dir, layer, tiles[0], folder))
            elif kind == "window":
                row.notes.append(_window(cache_dir, layer, tiles[0]))
            else:
                note = _read(cache_dir, _first_url(layer, tiles[0]))
                if note:
                    row.notes.append(note)
            row.read = OK
        except (requests.RequestException, RuntimeError, ValueError, OSError, rio.errors.RasterioError) as e:
            row.read = FAILED
            row.notes.append(cache.clean_error(e))
        return row
    finally:
        row.seconds = time.monotonic() - start


def _ortho_tile(ortho: OrthoService, lat: float, lon: float) -> str:
    z = min(ORTHO_ZOOM, ortho.base_max_zoom)
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return ortho.base_url.format(z=z, x=x, y=y)


def probe_ortho(source: Source, cache_dir: str) -> Row:
    row = Row(source.id, "orthophoto")
    start = time.monotonic()
    ortho = source.ortho
    try:
        if ortho.base_url:
            url = _ortho_tile(ortho, *source.sample)
            status, kind, _ = _ask(cache_dir, url)
            if status != 200 or "image" not in kind:
                raise RuntimeError(f"base tile: HTTP {status} {kind}")
        else:
            status, _, body = _ask(cache_dir, ortho.url, {"SERVICE": "WMS", "REQUEST": "GetCapabilities"})
            if status != 200 or b"Capabilit" not in body:
                raise RuntimeError(f"GetCapabilities: HTTP {status}")
        row.read = OK
    except (requests.RequestException, RuntimeError) as e:
        row.read = FAILED
        row.notes.append(cache.clean_error(e))
    row.seconds = time.monotonic() - start
    return row


def skip_reason(source: Source, named: bool, key: Optional[str]) -> Optional[str]:
    """Why a source is not probed, or None."""
    if source.sample is None:
        return "no sample point with data"
    if isinstance(source.nmt, OpenTopographyTiles) and not (named and key):
        return "only when named, with an OpenTopography key (50 calls a day)"
    return source_unavailable(source)


def probe_source(source: Source, cache_dir: str, folder: str, deep: bool,
                 done: Dict[int, Row]) -> List[Row]:
    """The rows of a source; a layer or orthophoto probed already (shared by sources) is not asked again."""
    rows = []
    for what, part in (("terrain", source.nmt), ("surface", source.nmpt), ("orthophoto", source.ortho)):
        if part is None:
            continue
        if id(part) in done:
            first = done[id(part)]
            rows.append(Row(source.id, what, first.index, first.read, 0.0, [f"as {first.source}"]))
            continue
        row = probe_ortho(source, cache_dir) if what == "orthophoto" else \
            probe_layer(source, part, what, cache_dir, folder, deep)
        done[id(part)] = row
        rows.append(row)
    return rows


def _within(fn: Callable[[], List[Row]], seconds: float) -> Optional[List[Row]]:
    """fn's result, or None when it takes longer (left running in a daemon thread)."""
    result: List = []
    thread = threading.Thread(target=lambda: result.append(fn()), daemon=True)
    thread.start()
    thread.join(seconds)
    return result[0] if result else None


def run(cache_dir: str, ids: Sequence[str] = (), deep: bool = False, key: Optional[str] = None,
        sources: Optional[Dict[str, Source]] = None, timeout: float = TIMEOUT_S) -> int:
    """Probe the sources (all, or those of ids), print the table; the exit code (1: something failed)."""
    sources = SOURCES if sources is None else sources
    unknown = [i for i in ids if i not in sources]
    if unknown:
        raise ValueError(f"unknown source: {', '.join(unknown)} (one of {', '.join(sources)})")
    OpenTopographyTiles.api_key = key or OpenTopographyTiles.api_key
    folder = tempfile.mkdtemp(prefix="findaline-probe-")
    done: Dict[int, Row] = {}
    checked = failed = skipped = 0
    out = sys.stdout
    sys.stdout = _PerThread(out)
    print(f"{'Source':<15} {'Layer':<11} {'Index':<5} {'Read':<5} {'Time':>6}  Note")
    try:
        for sid in ids or list(sources):
            source = sources[sid]
            why = skip_reason(source, sid in ids, key)
            if why:
                skipped += 1
                print(f"{sid:<15} {'':<11} {SKIPPED:<5} {SKIPPED:<5} {'':>6}  {cache.clean_error(why)}")
                continue
            checked += 1
            rows = _within(lambda source=source: probe_source(source, cache_dir, folder, deep, done), timeout)
            if rows is None:
                rows = [Row(sid, "", FAILED, FAILED, timeout, [f"no answer within {timeout:g} s"])]
            failed += any(r.failed for r in rows)
            for r in rows:
                print(f"{r.source:<15} {r.what:<11} {r.index:<5} {r.read:<5} {r.seconds:>5.1f}s  "
                      + "; ".join(cache.clean_error(n) for n in r.notes))
    finally:
        sys.stdout = out
        shutil.rmtree(folder, ignore_errors=True)
    print(f"\n{checked} checked, {failed} failed, {skipped} skipped")
    return 1 if failed else 0
