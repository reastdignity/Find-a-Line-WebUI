"""GeoJsonTiles: square tiles of plain XYZ files listed by a GeoJSON document of a whole Land (LVermGeo SH's DGM1)."""

import glob
import os
import threading
import time
from typing import Callable, NamedTuple, Optional, Sequence

import requests

import cache
import servicecounts

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..indexes.geojsonfiles import GeoJsonFiles
from ..indexes.metalink import MetalinkIndex, ShaPerTile
from ..readers.sheetfile import SheetFile, _xyz_grid
from .indexed import IndexedTiles
from .metalink import MetalinkTiles

# How long the index read again after an outdated link serves the other outdated links of a pass (one read of
# LVermGeo SH's 9 MB document, not one per stale tile; its five tiles of 2007 in the outer Flensburg Fjord)
STALE_REREAD_SECONDS = 600


class XyzSheet(NamedTuple):
    """What XyzFile needs to fetch one tile: its URL, its name in messages, CRS and pixel size, and its place
    ("<east>_<north>", the godlo without the year) for the index's answer after an outdated link."""
    url: str
    godlo: str
    crs: str
    res: float
    place: str = ""


class XyzPerTile(ShaPerTile):
    """ShaPerTile whose tiles are fetched by XyzFile (a request with the CRS and pixel size)."""

    def __init__(self, folder: str, crs: str, res: float, tile_m: float = 1000):
        super().__init__(folder, crs, tile_m)
        self.res = res

    def request(self, tile) -> XyzSheet:
        year = f" ({tile.year})" if tile.year else ""
        return XyzSheet(tile.url, f"{tile.godlo}{year}", self.crs, self.res, tile.godlo)


class StaleLink(RuntimeError):
    """The server answered a link with a page saying it is out of date (a newer survey replaced the file)."""


class XyzFile(SheetFile):
    """A plain "x y z" file of cell centres (no ZIP) per tile, one GET: the answer must be text/plain
    (an HTML page is never cached: LVermGeo SH answers an outdated link with HTTP 200 and a page
    "Die verwendete Massendownload-Datei ist veraltet", also for a file it simply no longer has;
    then on_stale(sheet) is called, which reads the index again and tells the link it names now for
    the tile: the same link, and the tile is no data (the server has no such file: the five tiles of
    2007 in the outer Flensburg Fjord, 2026-11-08); another, or none, and the tile is an error, the
    newer file used by the next search) and at most max_bytes, read streamed and given up beyond it
    (the server sends no Content-Length). Other failures are tried again (net.RETRIES); a 404 is no
    data."""

    def __init__(self, description: str, max_bytes: int = 60_000_000,
                 on_stale: Optional[Callable[[XyzSheet], Optional[str]]] = None):
        super().__init__(description, max_bytes=max_bytes)
        self.on_stale = on_stale

    def _get(self, url: str):
        """(body, response) of one attempt; (None, response) for a 404."""
        net.rate_turn(url)
        with servicecounts.request(url) as counted, \
                requests.get(url, timeout=300, headers=cache.http_headers(), verify=net.verify(url),
                             stream=True) as response:
            counted.got(response, read=False)
            kind = response.headers.get("content-type", "")
            if response.status_code == 404:
                return None, response
            if response.status_code != 200 or "html" in kind:
                text = " ".join(response.raw.read(2000, decode_content=True).decode("utf-8", "replace").split())
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {text[:300]}")
                counted.outcome = "other"
                raise StaleLink(f"an HTML page instead of the file ({text[:200]})")
            if not kind.startswith("text/plain"):
                counted.outcome = "other"
                raise RuntimeError(f"{kind or 'no content type'}, text/plain expected")
            body = bytearray()
            for chunk in response.iter_content(1 << 20):
                counted.add(len(chunk))
                body += chunk
                if len(body) > self.max_bytes:
                    raise RuntimeError(f"more than {self.max_bytes} bytes")
            return bytes(body), response

    def fetch(self, tile, path: str) -> Fetched:
        where = f"{self.description} tile {tile.godlo}"
        last = None
        for attempt in range(net.RETRIES):
            try:
                body, response = self._get(tile.url)
                break
            except StaleLink as e:
                current = self.on_stale(tile) if self.on_stale else None
                if current is not None and current == tile.url:
                    print(f"{where}: the index names a file the server no longer has ({e}); no data")
                    return Fetched(0, tile.url)
                told = ("the index now names another file, used by the next search" if current
                        else "the index is read again by the next search")
                raise RuntimeError(f"Could not download {where}: {e}; {told}") from None
            except (requests.RequestException, RuntimeError) as e:
                last = e
                net._sleep(attempt)
        else:
            raise RuntimeError(f"Could not download {where}: {cache.clean_error(last)}")
        if body is None:
            return Fetched(0, tile.url)
        try:
            band, transform = _xyz_grid(body, tile.res)
        except (ValueError, IndexError) as e:
            raise RuntimeError(f"{where}: not an XYZ grid ({str(e)[:100]})") from None
        _write_tile(path, _clean(band), tile.crs, transform)
        return Fetched(len(body), tile.url, response.headers.get("ETag"), response.headers.get("Last-Modified"))


class GeoJsonTiles(MetalinkTiles):
    """Square tiles of tile_m on a metric grid, plain XYZ files of a download service listed by GeoJSON
    documents that cover the region (GeoJsonFiles: a feature per file, its URL the property link):
    name, a regular expression of the file names with the groups east and north (in tile_m units of
    crs) and year if they carry one. The documents are read once per TTL and kept; the newest year of
    each tile is used, a file known by its URL (XyzPerTile: a newer survey has another link). Read by
    XyzFile; an outdated link makes the index be read again at once (the kept files and the 0.25°
    answers forgotten, once per STALE_REREAD_SECONDS for every stale link of a pass): the tile is no
    data when the index still names that link, an error when it names another (_stale). Cached in
    <folder>/<east // 10>_<north // 10>/<east>_<north>[_<year>]_<key>.tif."""

    def __init__(self, description: str, documents: Sequence[str], name: str, folder: str, crs: str,
                 prefix: str, native_res: float = 1.0, tile_m: float = 1000, bytes_per_tile: float = 27e6,
                 link: str = "link_data", max_bytes: int = 60_000_000):
        IndexedTiles.__init__(self, description, documents[0], prefix, folder, native_res=native_res,
                              bytes_per_tile=bytes_per_tile)
        self.metalinks, self.name, self.index_crs, self.crs, self.tile_m = tuple(documents), name, crs, crs, tile_m
        self.average, self.force_crs = 1, None
        top = folder.split("/")[0]
        self.listing = GeoJsonFiles(documents, name, crs, native_res, top, prefix, tile_m, link)
        self.index = MetalinkIndex(description, self.listing, XyzPerTile(folder, crs, native_res, tile_m), prefix, top)
        self.reader = XyzFile(description, max_bytes=max_bytes, on_stale=self._stale)
        self._stale_lock = threading.Lock()
        self._reread_at: Optional[float] = None  # when the documents were last read again after an outdated link

    def _stale(self, sheet: XyzSheet) -> Optional[str]:
        """A link of the index is out of date: forget the kept documents and every 0.25° answer and read the
        documents again (at most once per STALE_REREAD_SECONDS: the stale links of one pass meet the same
        index), then the link the index names now for the sheet's tile, or None when it lists the tile no
        more or cannot be had (the tile is an error then, as before)."""
        cache_dir = self.index.cache_dir
        if not cache_dir:
            return None
        with self._stale_lock:
            now = time.monotonic()
            if self._reread_at is None or now - self._reread_at >= STALE_REREAD_SECONDS:
                answers = glob.glob(os.path.join(cache_dir, self.listing.top, "sheet-index", self.prefix, "*.json"))
                try:
                    self.listing.forget(cache_dir)
                    cache.forget(cache_dir, answers)
                except OSError:  # another process forgot them now
                    pass
                self.index._listed.clear()
                self._reread_at = now
            self.listing.cache_dir = cache_dir
            try:
                items = [item for item in self.listing.table() if item["godlo"] == sheet.place]
            except requests.RequestException:
                return None
            newest = self.index.versions._newest(items)
            return next(iter(newest.values())).url if newest else None
