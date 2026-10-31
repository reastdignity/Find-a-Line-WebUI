"""Listings: how an index service is asked for the versions in one 0.25° tile (a WFS sheet index, a STAC
API, The National Map's products), as cached by CachedIndex."""

import re
from typing import Callable, Dict, List, Optional

import requests

import cache
import osm

from .. import net
from ..net import RETRIES
from .cached import Listing

# Coordinate systems named in the uklad_xy attribute of the geoportal.gov.pl sheet indexes
SHEET_CRS = {"PL-1992": "EPSG:2180", "PL-2000:S5": "EPSG:2176", "PL-2000:S6": "EPSG:2177",
             "PL-2000:S7": "EPSG:2178", "PL-2000:S8": "EPSG:2179"}
SHEET_FORMATS = ("ARC/INFO ASCII GRID", "ASCII XYZ GRID")


class WfsSheets(Listing):
    """Map sheets of a WFS sheet index (geoportal.gov.pl): one layer per year
    (`<prefix><year>`), every sheet linking to a file (ASCII grid or XYZ, sometimes zipped).
    Sheets with a resolution between min_res and native_res are listed; extents in EPSG:2180
    (from the sheet outline; EPSG:2180 lists northing before easting)."""

    def __init__(self, url: str, prefix: str, native_res: float, min_res: float):
        self.url, self.prefix, self.native_res, self.min_res = url, prefix, native_res, min_res
        self._years: Optional[List[str]] = None

    def _wfs(self, **params) -> str:
        response = requests.get(self.url, timeout=300, headers=cache.http_headers(),
                                params={"SERVICE": "WFS", "VERSION": "2.0.0", **params})
        response.raise_for_status()
        return response.text

    def _year_layers(self) -> List[str]:
        if self._years is None:
            names = re.findall(rf"<Name>(gugik:{self.prefix}\d{{4}})</Name>", self._wfs(REQUEST="GetCapabilities"))
            self._years = sorted(set(names))
        return self._years

    def fetch(self, lat: float, lon: float) -> Dict:
        sheets = []
        for layer in self._year_layers():
            text = self._wfs(REQUEST="GetFeature", TYPENAMES=layer, COUNT=10000,
                             PROPERTYNAME="godlo,akt_rok,char_przestrz,format,uklad_xy,url_do_pobrania,msGeometry",
                             BBOX=f"{lat},{lon},{lat + osm.TILE_DEG},{lon + osm.TILE_DEG},urn:ogc:def:crs:EPSG::4326")
            for member in text.split("<wfs:member>")[1:]:
                f = dict(re.findall(r"<gugik:(\w+)>([^<]*)</gugik:\1>", member))
                res = re.match(r"[\d.]+", f.get("char_przestrz", ""))
                url = f.get("url_do_pobrania", "")
                if not (res and url and f.get("format") in SHEET_FORMATS and f.get("uklad_xy") in SHEET_CRS):
                    continue
                if not self.min_res - 1e-6 <= float(res.group()) <= self.native_res + 1e-6:
                    continue
                values = [float(v) for v in " ".join(re.findall(r"<gml:posList[^>]*>([^<]*)<", member)).split()]
                north, east = values[0::2], values[1::2]
                if not north:
                    continue
                sheets.append({"year": int(f["akt_rok"]), "godlo": f.get("godlo", ""), "url": url,
                               "crs": SHEET_CRS[f["uklad_xy"]], "res": float(res.group()),
                               "extent": [min(east), min(north), max(east), max(north)]})
        return {"layers": self._year_layers(), "sheets": sheets}


class StacItems(Listing):
    """Items of a STAC collection (swisstopo), one per tile and survey year
    (`<product>_<year>_<E>-<N>`, E and N in tile_m units), in pages of 100 following the
    `next` links; every GeoTIFF asset at a resolution of sizes is listed, with the sha256 of
    its file:checksum (a multihash) and the tile's extent in crs."""

    def __init__(self, url: str, crs: str, sizes: Dict[float, float], tile_m: float):
        self.url, self.crs, self.sizes, self.tile_m = url, crs, sizes, tile_m

    def fetch(self, lat: float, lon: float) -> Dict:
        sheets = []
        url = self.url
        params = {"bbox": f"{lon},{lat},{lon + osm.TILE_DEG},{lat + osm.TILE_DEG}", "limit": 100}
        while url:  # pages of 100 items
            response = requests.get(url, params=params, timeout=120, headers=cache.http_headers())
            response.raise_for_status()
            page = response.json()
            for item in page["features"]:
                name = re.search(r"_(\d{4})_(\d+)-(\d+)$", item["id"])
                if not name:
                    continue
                year, east, north = int(name.group(1)), int(name.group(2)), int(name.group(3))
                for asset in item["assets"].values():
                    res = float(asset.get("gsd") or 0)
                    if "tiff" not in asset.get("type", "") or res not in self.sizes:
                        continue
                    checksum = asset.get("file:checksum", "").lower()
                    sheets.append({"year": year, "godlo": f"{east}-{north}", "url": asset["href"],
                                   "crs": self.crs, "res": res,
                                   "sha256": checksum[4:] if checksum.startswith("1220") else None,
                                   "extent": [east * self.tile_m, north * self.tile_m,
                                              (east + 1) * self.tile_m, (north + 1) * self.tile_m]})
            url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
            params = None  # the next link carries them
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
                    response = requests.get(self.url, timeout=120, headers=cache.http_headers(), params={
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
