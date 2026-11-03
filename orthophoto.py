"""
Caching orthophoto tiles (from the WMS of a data source) for offline use of the interactive map.

Tiles follow the Web Mercator XYZ scheme used by the map ({z}/{x}/{y}.jpg) and are
requested from the WMS with exactly the same bounding box the map would use, so
cached and online tiles look the same. Detailed zoom levels are only fetched in a
strip around the found lines; the whole search area is fetched for an overview.
"""

import io
import math
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import requests
from PIL import Image
from pyproj import Transformer
from shapely.geometry import LineString, box
from shapely.ops import unary_union
from shapely.prepared import prep

import cache
import servicecounts
from progress import progress
from sources import net

TILE_PX = 256
OVERVIEW_ZOOMS = range(10, 17)  # whole search area
DETAIL_ZOOMS = range(17, 22)    # only around lines (up to mapping.MAX_ZOOM)
BUFFER_M = 30                   # strip width on each side of a line
APPROX_TILE_KB = 15
DOWNLOAD_THREADS = 4
RETRIES = 3
BACKOFF_MAX_S = 64  # the longest wait between attempts (swisstopo's advice on retries)
JPEG_MAGIC = b"\xff\xd8\xff"

_EARTH = 20037508.342789244  # half of the Web Mercator world width in metres
_to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

Tile = Tuple[int, int, int]  # (z, x, y)


def cache_folder(cache_dir: str, service) -> str:
    """Folder of a service's tiles ({z}/{x}/{y}.jpg); service is a sources.OrthoService."""
    return os.path.join(cache_dir, service.folder, "wm256")


def tile_path(folder: str, z: int, x: int, y: int) -> str:
    return os.path.join(folder, str(z), str(x), f"{y}.jpg")


def _tile_size(z: int) -> float:
    return 2 * _EARTH / 2 ** z


def _tiles_in(area, zooms: Iterable[int]) -> Set[Tile]:
    """Tiles (any zoom in zooms) intersecting a shape in Web Mercator metres."""
    tiles = set()
    prepared = prep(area)
    minx, miny, maxx, maxy = area.bounds
    for z in zooms:
        size = _tile_size(z)
        for x in range(math.floor((minx + _EARTH) / size), math.floor((maxx + _EARTH) / size) + 1):
            for y in range(math.floor((_EARTH - maxy) / size), math.floor((_EARTH - miny) / size) + 1):
                left, top = x * size - _EARTH, _EARTH - y * size
                if prepared.intersects(box(left, top - size, left + size, top)):
                    tiles.add((z, x, y))
    return tiles


def tiles_to_cache(lines: List[Dict], area, max_zoom: int = DETAIL_ZOOMS[-1]) -> Set[Tile]:
    """Tiles for the overview of the search area (area.Area) and the strips around lines,
    up to max_zoom (a service of tiles only: its last zoom, the map enlarges it)."""
    # Web Mercator stretches distances by 1/cos(latitude)
    scale = 1 / math.cos(math.radians(area.center[0]))
    tiles = _tiles_in(area.shape_mercator(), OVERVIEW_ZOOMS)

    strips = []
    for line in lines:
        (lat1, lon1), (lat2, lon2) = line["anchor1"], line["anchor2"]
        strips.append(LineString([_to_mercator.transform(lon1, lat1),
                                  _to_mercator.transform(lon2, lat2)]).buffer(BUFFER_M * scale))
    if strips:
        tiles |= _tiles_in(unary_union(strips), range(DETAIL_ZOOMS[0], max_zoom + 1))
    return tiles


def missing_tiles(tiles: Iterable[Tile], folder: str, cache_dir: Optional[str] = None,
                  update: Optional[str] = None, ttl: Optional[int] = None) -> List[Tile]:
    """Tiles not cached yet, and with update ("stale" or "all") the ones due for a check."""
    if update and ttl is not None:
        return sorted(t for t in tiles if cache.due(cache_dir, tile_path(folder, *t), update=update, ttl=ttl))
    return sorted(t for t in tiles if not os.path.exists(tile_path(folder, *t)))


def tile_of(path: str) -> Optional[Tile]:
    """(z, x, y) of a cached tile (a path ending in z/x/y.jpg)."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) < 3 or not parts[-1].endswith(".jpg"):
        return None
    try:
        return int(parts[-3]), int(parts[-2]), int(parts[-1][:-4])
    except ValueError:
        return None


def bounds_wgs84(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """(west, south, east, north) of an XYZ tile."""
    south, west, north, east = map(float, _wms_bbox(z, x, y).split(","))
    return west, south, east, north


def _wms_bbox(z: int, x: int, y: int) -> str:
    """WGS84 bounding box of an XYZ tile, in WMS 1.3.0 axis order (lat, lon)."""
    n = 2 ** z
    west, east = x / n * 360 - 180, (x + 1) / n * 360 - 180
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return f"{south!r},{west!r},{north!r},{east!r}"


def _backoff(attempt: int, slow_down: bool = False) -> float:
    """Seconds before the next attempt: truncated exponential backoff with jitter, as swisstopo asks
    (https://docs.geo.admin.ch/get-started/retry.html): 0.5-1.5 times 2^attempt s, from 2^(attempt + 3)
    after a 429 or 503 (the server asks us to slow down), at most BACKOFF_MAX_S."""
    return min(BACKOFF_MAX_S, 2 ** (attempt + 3 * slow_down) * (0.5 + random.random()))


def _get(url: str, params: Optional[Dict], z: int, x: int, y: int) -> bytes:
    """A tile; every attempt in its turn of the host's rate (net.rate_turn) and counted."""
    last_error = None
    for attempt in range(RETRIES):
        slow_down = False
        try:
            net.rate_turn(url)
            with servicecounts.request(url) as counted:  # every attempt
                response = counted.got(requests.get(url, params=params, timeout=60, headers=cache.http_headers()))
                if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/"):
                    return response.content
                if response.status_code == 200:
                    counted.outcome = "other"  # an error page instead of an image
            last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
            slow_down = response.status_code in (429, 503)
        except (requests.RequestException, RuntimeError) as e:  # RuntimeError: no turn in time
            last_error = e
        time.sleep(_backoff(attempt, slow_down))
    raise RuntimeError(f"Could not download orthophoto tile {z}/{x}/{y}: {cache.clean_error(last_error)}")


def mercator_box(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """(left, bottom, right, top) of an XYZ tile in Web Mercator metres (EPSG:3857)."""
    size = _tile_size(z)
    return x * size - _EARTH, _EARTH - (y + 1) * size, (x + 1) * size - _EARTH, _EARTH - y * size


def _get_map(url: str, layer: str, z: int, x: int, y: int, png: bool = False, version: str = "1.3.0",
             crs: str = "EPSG:4326") -> bytes:
    """One tile from a WMS: JPEG, or with png a PNG transparent where the service has no imagery.
    WMS 1.3.0 asks EPSG:4326 in its lat-lon axis order, 1.1.1 (OrthoService.wms_version) as SRS in
    lon-lat order. With crs EPSG:3857 (OrthoService.wms_crs) the tile's Mercator box is asked, x
    before y in both versions."""
    params = {"SERVICE": "WMS", "VERSION": version, "REQUEST": "GetMap", "LAYERS": layer, "STYLES": ""}
    if version not in ("1.1.1", "1.3.0"):
        raise ValueError(f"WMS version {version}: 1.3.0 or 1.1.1 expected")
    key = "SRS" if version == "1.1.1" else "CRS"
    if crs == "EPSG:3857":
        params.update({key: crs, "BBOX": ",".join(repr(v) for v in mercator_box(z, x, y))})
    elif crs != "EPSG:4326":
        raise ValueError(f"WMS CRS {crs}: EPSG:4326 or EPSG:3857 expected")
    elif version == "1.1.1":
        south, west, north, east = _wms_bbox(z, x, y).split(",")
        params.update(SRS="EPSG:4326", BBOX=f"{west},{south},{east},{north}")
    else:
        params.update(CRS="EPSG:4326", BBOX=_wms_bbox(z, x, y))
    params.update(WIDTH=TILE_PX, HEIGHT=TILE_PX, FORMAT="image/png" if png else "image/jpeg")
    if png:
        params["TRANSPARENT"] = "TRUE"
    return _get(url, params, z, x, y)


def _base_tile(service, z: int, x: int, y: int) -> Image.Image:
    """A tile of the base service; above its last zoom, a part of its tile there, enlarged."""
    up = max(0, z - service.base_max_zoom)
    url = service.base_url.format(z=z - up, x=x >> up, y=y >> up)
    tile = Image.open(io.BytesIO(_get(url, None, z, x, y))).convert("RGBA")
    if up:
        part, n = TILE_PX >> up, 1 << up
        left, top = (x % n) * part, (y % n) * part
        tile = tile.crop((left, top, left + part, top + part)).resize((TILE_PX, TILE_PX), Image.BILINEAR)
    return tile


def _jpeg(tile: Image.Image) -> bytes:
    out = io.BytesIO()
    tile.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def _on_white(image: bytes) -> Image.Image:
    """An image (any format PIL reads) laid over white."""
    tile = Image.open(io.BytesIO(image)).convert("RGBA")
    white = Image.new("RGBA", tile.size, (255, 255, 255, 255))
    white.alpha_composite(tile)
    return white


def _white_blocks(jpeg: bytes) -> Tuple[bool, bool]:
    """(all white, any white 8x8 block): how a WMS answering in JPEG shows where it has no imagery."""
    white = (np.asarray(Image.open(io.BytesIO(jpeg)).convert("L")) == 255)
    h, w = white.shape
    blocks = white[:h // 8 * 8, :w // 8 * 8].reshape(h // 8, 8, w // 8, 8).all(axis=(1, 3))
    return bool(white.all()), bool(blocks.any())


def tile_content(service, z: int, x: int, y: int) -> bytes:
    """A tile as cached (JPEG). With a base service, the parts of the service without imagery
    (white) come from the base: a tile wholly outside its coverage is the base's tile, a tile
    on the edge of the coverage is the service (transparent PNG) laid over the base. Without
    a WMS the tile is the base's."""
    if not service.url:
        if z <= service.base_max_zoom:
            return _get(service.base_url.format(z=z, x=x, y=y), None, z, x, y)
        return _jpeg(_base_tile(service, z, x, y))
    version, crs = service.wms_version, service.wms_crs
    content = _get_map(service.url, service.layer, z, x, y, version=version, crs=crs)
    if not content.startswith(JPEG_MAGIC):
        # A WMS that answers PNG although JPEG was asked (gis.natt.is): cached as JPEG like every
        # tile, its transparent parts (no imagery: the sea) white
        content = _jpeg(_on_white(content))
    if not service.base_url:
        return content
    empty, partly = _white_blocks(content)
    if empty:
        if z <= service.base_max_zoom:  # the base's own tile, as it sent it
            return _get(service.base_url.format(z=z, x=x, y=y), None, z, x, y)
        return _jpeg(_base_tile(service, z, x, y))
    if not partly:
        return content
    top = _get_map(service.url, service.layer, z, x, y, png=True, version=version, crs=crs)
    top = Image.open(io.BytesIO(top)).convert("RGBA")
    tile = _base_tile(service, z, x, y)
    tile.alpha_composite(top)
    return _jpeg(tile)


def _download_tile(service, z: int, x: int, y: int, path: str):
    content = tile_content(service, z, x, y)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.part"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, path)
    return len(content)


def download(service, tiles: List[Tile], folder: str, cache_dir: str):
    """Download tiles (in parallel) into the cache and its index. Failed tiles are skipped."""
    if not tiles:
        return
    errors, done = [], []
    received = 0
    progress.download.start("orthophoto tiles", len(tiles), unit="tile")
    with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
        futures = {pool.submit(_download_tile, service, *t, tile_path(folder, *t)): t for t in tiles}
        for future in as_completed(futures):
            try:
                received += future.result()
                done.append(tile_path(folder, *futures[future]))
            except RuntimeError as e:
                errors.append(e)
            progress.download.update(1, MB=f"{received / 1e6:.0f}", failed=len(errors))
    progress.download.finish(f"{received / 1e6:.0f} MB")
    cache.record_many(cache_dir, done, url=service.url or service.base_url)
    if errors:
        print(f"  {len(errors)} tiles failed (e.g. {str(errors[0])[:200]})")
        print("  The map loads them online instead; run again to retry them.")
