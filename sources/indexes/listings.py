"""Listings: how an index service is asked for the versions in one 0.25° tile (a WFS sheet index, a STAC
API, The National Map's products), as cached by CachedIndex."""

import contextlib
import io
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

import requests

import cache
import osm
import servicecounts

from .. import net
from ..net import RETRIES
from .cached import IndexUnavailable, Listing

# Coordinate systems named in the uklad_xy attribute of the geoportal.gov.pl sheet indexes
SHEET_CRS = {"PL-1992": "EPSG:2180", "PL-2000:S5": "EPSG:2176", "PL-2000:S6": "EPSG:2177",
             "PL-2000:S7": "EPSG:2178", "PL-2000:S8": "EPSG:2179"}
SHEET_FORMATS = ("ARC/INFO ASCII GRID", "ASCII XYZ GRID")
# GetFeature requests of one WFS listing at a time (the year layers of a tile; each also under a
# slot of its host, net.HOST_SLOTS_OF, so the cap holds across layers and processes), and the
# 0.25° tiles of one grid asked at a time (NewestPerSheet.query: tiles_at_once)
WFS_THREADS = 4
# Days the year layers of a WFS sheet index (its GetCapabilities) are taken from the disk: those
# of the tile answers (cache.TTL_DAYS), so a new year layer is found as late as a new survey
CAPABILITIES_DAYS = cache.TTL_DAYS["sheet-index"]

# The root element of an XML answer (after its declaration, comments and doctype)
XML_ROOT = re.compile(rb"\s*(?:<\?.*?\?>\s*|<!--.*?-->\s*|<!DOCTYPE[^>]*>\s*)*<(?:[\w.-]+:)?([\w.-]+)", re.DOTALL)
# OGC exception reports: OWS 1.x/2.0 (WFS 2.0) and the older WFS/WMS ones
EXCEPTION_ROOTS = (b"ExceptionReport", b"ServiceExceptionReport")


def ows_exception(body: bytes) -> Optional[str]:
    """The text of an OGC exception report (None if body is no such report): a service may answer an
    error with HTTP 200."""
    root = XML_ROOT.match(body)
    if not root or root.group(1) not in EXCEPTION_ROOTS:
        return None
    text = re.search(rb"<(?:[\w.-]+:)?(?:ExceptionText|ServiceException)(?:\s[^>]*)?>([^<]*)<", body)
    return text.group(1).decode("utf-8", "replace").strip() if text else "an exception report"


def _gml_features(gml: bytes) -> List[Tuple[Dict, Optional[Tuple[float, float, float, float]]]]:
    """The features of a GML FeatureCollection (a WFS GetFeature answer), read by GDAL's GML
    driver through pyogrio: their attributes and the bounds of their geometry (None without
    one), easting first (GDAL swaps the axes of a CRS like EPSG:2180, whose EPSG order is
    northing, easting). The schema the answer names (DescribeFeatureType) is not downloaded:
    the attributes are typed from their values. An answer that is no GML lists nothing, as
    the regular expressions read it before."""
    # Imported here: the web process imports sources (the about page) and needs none of it
    import shapely
    from pyogrio import raw
    from pyogrio.errors import DataLayerError, DataSourceError

    try:
        meta, _, geometry, values = raw.read(io.BytesIO(gml), layer=0, DOWNLOAD_SCHEMA="NO")
    except DataLayerError:  # an empty collection has no layer when its schema is not read
        return []
    except DataSourceError:  # not GML (an error page)
        return []
    names = list(meta["fields"])
    features = []
    for k in range(len(geometry)):
        shape = shapely.from_wkb(geometry[k]) if geometry[k] is not None else None
        bounds = tuple(float(v) for v in shape.bounds) if shape is not None and not shape.is_empty else None
        features.append(({name: values[i][k] for i, name in enumerate(names)}, bounds))
    return features


def _text(value) -> str:
    """An attribute as text ("" when it is missing)."""
    return "" if value is None else str(value)


class WfsSheets(Listing):
    """Map sheets of a WFS sheet index (geoportal.gov.pl): one layer per year
    (`<prefix><year>`), every sheet linking to a file (ASCII grid or XYZ, sometimes zipped).
    The requests are ours (requests: GetCapabilities, GetFeature per year), the GML answers
    are read by pyogrio; an exception report is IndexUnavailable, also with HTTP 200. Sheets with a resolution between min_res and native_res are listed;
    extents in EPSG:2180 (the bounds of the sheet outline).

    The GetFeature requests of a tile (one per year layer) go `threads` at a time, each under a
    slot of the host (net.host_slot) on a keep-alive session of its thread (net.session); their
    answers are read in the order of the layers, so the cached answer is byte for byte the one
    of the requests one after another. The year layers (the capabilities) are kept in a small
    file next to the tile answers (`<top>/sheet-index/<prefix>.capabilities.json`: the layers
    and when they were asked, no row in index.sqlite, so `cache status` and `cache update`
    never see it) for CAPABILITIES_DAYS, so a new process asks only for the features; they are
    asked again after that, with the update "all" (`cache update`: once per process), and when
    a GetFeature fails on layers read from the file (a layer renamed). use() gives the folder."""
    threads = WFS_THREADS  # GetFeature requests at once (1: one after another, as recorded)
    tiles_at_once = WFS_THREADS  # 0.25° tiles NewestPerSheet.query asks at once

    def __init__(self, url: str, prefix: str, native_res: float, min_res: float):
        self.url, self.prefix, self.native_res, self.min_res = url, prefix, native_res, min_res
        self._years: Optional[List[str]] = None  # the year layers (set by hand: used as they are)
        self._years_from: Optional[str] = None   # "file" or "asked" (by this process), None: set by hand
        self._years_at: Optional[str] = None     # when they were asked (cache.now_iso)
        self._renew = False                      # ask the service, not the file, for them next
        self._cache_dir: Optional[str] = None    # of the host slots and the capabilities file (use)
        self._capabilities: Optional[str] = None
        self._lock = threading.Lock()            # one capabilities request for all the threads
        self._pool: Optional[ThreadPoolExecutor] = None

    def use(self, index, cache_dir: str, update: Optional[str] = None):
        """The data folder of the index asking (a CachedIndex: its top folder and prefix name
        the capabilities file) and its update mode, before it asks for tiles (NewestPerSheet)."""
        with self._lock:
            self._cache_dir = cache_dir
            self._capabilities = os.path.join(cache_dir, index.top, "sheet-index",
                                              f"{index.prefix}.capabilities.json")
            if update == "all" and (self._years is None or self._years_from == "file"):
                self._years, self._years_from, self._renew = None, None, True

    def _wfs(self, **params) -> bytes:
        slot = net.host_slot(self._cache_dir, self.url) if self._cache_dir else contextlib.nullcontext()
        with slot:
            response = servicecounts.call(self.url, lambda: net.session().get(
                self.url, timeout=300, headers=cache.http_headers(),
                params={"SERVICE": "WFS", "VERSION": "2.0.0", **params}))
        response.raise_for_status()
        error = ows_exception(response.content)
        if error:  # answered with HTTP 200: not an answer to cache
            raise IndexUnavailable(f"WFS {params.get('REQUEST')}: {error}")
        return response.content

    def _year_layers(self) -> List[str]:
        with self._lock:
            if self._years is not None and (self._years_from is None
                                            or cache.age_days(self._years_at) <= CAPABILITIES_DAYS):
                return self._years
            if not self._renew and self._read_capabilities():
                return self._years
            capabilities = self._wfs(REQUEST="GetCapabilities").decode("utf-8")
            names = re.findall(rf"<Name>(gugik:{self.prefix}\d{{4}})</Name>", capabilities)
            self._years, self._years_from, self._years_at = sorted(set(names)), "asked", cache.now_iso()
            self._renew = False
            if self._capabilities:
                os.makedirs(os.path.dirname(self._capabilities), exist_ok=True)
                tmp = net._part(self._capabilities)
                with open(tmp, "w", encoding="utf-8") as out:
                    json.dump({"url": self.url, "asked_at": self._years_at, "layers": self._years}, out)
                os.replace(tmp, self._capabilities)
            return self._years

    def _read_capabilities(self) -> bool:
        """The year layers from the capabilities file, when it is there, of this index and recent."""
        try:
            with open(self._capabilities or "", encoding="utf-8") as f:
                kept = json.load(f)
        except (OSError, ValueError):
            return False
        if kept.get("url") != self.url or cache.age_days(kept.get("asked_at")) > CAPABILITIES_DAYS:
            return False
        self._years, self._years_from, self._years_at = list(kept["layers"]), "file", kept["asked_at"]
        return True

    def _from_file(self, layers: List[str]) -> bool:
        """After a failed GetFeature: whether these layers came from the file (then they are asked
        for again: a layer may have been renamed)."""
        with self._lock:
            if self._years_from != "file" or self._years is not layers:
                return False
            self._years, self._years_from, self._renew = None, None, True
            return True

    def _features(self, layers: List[str], lat: float, lon: float) -> List[bytes]:
        """The GetFeature answers of the year layers over a tile, in the order of the layers."""
        def features(layer: str) -> bytes:
            return self._wfs(REQUEST="GetFeature", TYPENAMES=layer, COUNT=10000,
                             PROPERTYNAME="godlo,akt_rok,char_przestrz,format,uklad_xy,url_do_pobrania,msGeometry",
                             BBOX=f"{lat},{lon},{lat + osm.TILE_DEG},{lon + osm.TILE_DEG},urn:ogc:def:crs:EPSG::4326")
        if self.threads <= 1 or len(layers) <= 1:
            return [features(layer) for layer in layers]
        with self._lock:  # kept for the next tiles: the threads' sessions keep their connections
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=self.threads, thread_name_prefix="wfs-sheets")
        return list(self._pool.map(features, layers))  # the first error in the order of the layers

    def fetch(self, lat: float, lon: float) -> Dict:
        layers = self._year_layers()
        try:
            answers = self._features(layers, lat, lon)
        except requests.RequestException:
            if not self._from_file(layers):
                raise
            layers = self._year_layers()
            answers = self._features(layers, lat, lon)
        sheets = []
        for gml in answers:
            for f, bounds in _gml_features(gml):
                res = re.match(r"[\d.]+", _text(f.get("char_przestrz")))
                url = _text(f.get("url_do_pobrania"))
                if not (res and url and f.get("format") in SHEET_FORMATS and f.get("uklad_xy") in SHEET_CRS):
                    continue
                if not self.min_res - 1e-6 <= float(res.group()) <= self.native_res + 1e-6:
                    continue
                if bounds is None:
                    continue
                sheets.append({"year": int(f["akt_rok"]), "godlo": _text(f.get("godlo")), "url": url,
                               "crs": SHEET_CRS[f["uklad_xy"]], "res": float(res.group()),
                               "extent": list(bounds)})
        return {"layers": layers, "sheets": sheets}


# The item ids of swisstopo's collections: <product>_<year>_<E>-<N>, E and N in km
SWISSTOPO_ITEM = r"_(?P<year>\d{4})_(?P<east>\d+)-(?P<north>\d+)$"


class StacItems(Listing):
    """Items of a STAC collection, one per tile and survey year, searched with pystac-client
    (GET, pages of 100 following the `next` links). The tile and the year come from the item
    id (item: a regular expression with the groups year, east and north, in tile_m units;
    swisstopo's `<product>_<year>_<E>-<N>` by default). Every GeoTIFF asset at a resolution of
    sizes (its gsd) is listed, or with asset only the asset of that key (LGLN's items name no
    gsd: it is then the finest of sizes), with the sha256 of its file:checksum (a multihash)
    when there is one and the tile's extent in crs."""

    def __init__(self, url: str, crs: str, sizes: Dict[float, float], tile_m: float,
                 asset: Optional[str] = None, item: str = SWISSTOPO_ITEM):
        self.url, self.crs, self.sizes, self.tile_m = url, crs, sizes, tile_m
        self.asset, self.item = asset, re.compile(item)

    def _pages(self, lat: float, lon: float) -> List[Dict]:
        """The answers of the search, page by page; IndexUnavailable when one cannot be had."""
        # Imported here: the web process imports sources (the about page) and needs none of it
        from pystac_client.exceptions import APIError
        from pystac_client.item_search import ItemSearch
        from pystac_client.stac_api_io import StacApiIO

        stac_io = StacApiIO(headers=cache.http_headers(), timeout=120, max_retries=0)
        send = stac_io.session.send  # each page in its turn (net.rate_turn) and counted (servicecounts), as our own requests

        def counted_send(prepared, **kwargs):
            net.rate_turn(prepared.url)
            return servicecounts.call(prepared.url, lambda: send(prepared, **kwargs))
        stac_io.session.send = counted_send
        search = ItemSearch(self.url, method="GET", bbox=(lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG),
                            limit=100, stac_io=stac_io)
        try:
            return list(search.pages_as_dicts())
        # APIError is no RequestException; a RuntimeError: no turn of net.rate_turn in time
        except (APIError, requests.RequestException, ValueError, RuntimeError) as e:
            raise IndexUnavailable(f"STAC API: {e}") from e

    def fetch(self, lat: float, lon: float) -> Dict:
        sheets = []
        for page in self._pages(lat, lon):
            for item in page["features"]:
                name = self.item.search(item["id"])
                if not name:
                    continue
                year, east, north = int(name.group("year")), int(name.group("east")), int(name.group("north"))
                if self.asset is None:
                    assets = list(item["assets"].values())
                else:
                    assets = [item["assets"][self.asset]] if self.asset in item["assets"] else []
                for asset in assets:
                    res = float(asset.get("gsd") or (min(self.sizes) if self.asset else 0))
                    if "tiff" not in asset.get("type", "") or res not in self.sizes:
                        continue
                    checksum = asset.get("file:checksum", "").lower()
                    sheets.append({"year": year, "godlo": f"{east}-{north}", "url": asset["href"],
                                   "crs": self.crs, "res": res,
                                   "sha256": checksum[4:] if checksum.startswith("1220") else None,
                                   "extent": [east * self.tile_m, north * self.tile_m,
                                              (east + 1) * self.tile_m, (north + 1) * self.tile_m]})
        return {"sheets": sheets}


class TnmProducts(Listing):
    """Products of a dataset of The National Map Access API (USGS 3DEP), in pages of up to
    500, asked again (RETRIES, with backoff) while the API is slow or down; item(product)
    gives a product as cached, or None if it is not used."""

    def __init__(self, url: str, dataset: str, item: Callable[[Dict], Optional[Dict]]):
        self.url, self.dataset, self.item = url, dataset, item

    def fetch(self, lat: float, lon: float) -> Dict:
        items: Dict[str, Dict] = {}
        offset, total = 0, 1
        while offset < total:  # pages of up to 500 products
            for attempt in range(RETRIES):
                try:
                    response = servicecounts.get(self.url, timeout=120, headers=cache.http_headers(), params={
                        "datasets": self.dataset, "max": 500, "offset": offset,
                        "bbox": f"{lon},{lat},{lon + osm.TILE_DEG},{lat + osm.TILE_DEG}"})
                    response.raise_for_status()
                    page = response.json()
                    break
                except (requests.RequestException, ValueError) as e:  # the API is sometimes slow or down
                    if attempt == RETRIES - 1:
                        raise requests.RequestException(f"TNM API: {e}")
                    net._sleep(attempt)
            products = page.get("items") or []
            for product in products:
                item = self.item(product)
                if item:
                    items[item["url"]] = item
            offset, total = offset + len(products), (page.get("total") or 0) if products else 0
        return {"sheets": list(items.values())}
