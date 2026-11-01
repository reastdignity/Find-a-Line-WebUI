"""Listings: how an index service is asked for the versions in one 0.25° tile (a WFS sheet index, a STAC
API, The National Map's products), as cached by CachedIndex."""

import io
import re
from typing import Callable, Dict, List, Optional, Tuple

import requests

import cache
import osm

from .. import net
from ..net import RETRIES
from .cached import IndexUnavailable, Listing

# Coordinate systems named in the uklad_xy attribute of the geoportal.gov.pl sheet indexes
SHEET_CRS = {"PL-1992": "EPSG:2180", "PL-2000:S5": "EPSG:2176", "PL-2000:S6": "EPSG:2177",
             "PL-2000:S7": "EPSG:2178", "PL-2000:S8": "EPSG:2179"}
SHEET_FORMATS = ("ARC/INFO ASCII GRID", "ASCII XYZ GRID")


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
    are read by pyogrio. Sheets with a resolution between min_res and native_res are listed;
    extents in EPSG:2180 (the bounds of the sheet outline)."""

    def __init__(self, url: str, prefix: str, native_res: float, min_res: float):
        self.url, self.prefix, self.native_res, self.min_res = url, prefix, native_res, min_res
        self._years: Optional[List[str]] = None

    def _wfs(self, **params) -> bytes:
        response = requests.get(self.url, timeout=300, headers=cache.http_headers(),
                                params={"SERVICE": "WFS", "VERSION": "2.0.0", **params})
        response.raise_for_status()
        return response.content

    def _year_layers(self) -> List[str]:
        if self._years is None:
            capabilities = self._wfs(REQUEST="GetCapabilities").decode("utf-8")
            names = re.findall(rf"<Name>(gugik:{self.prefix}\d{{4}})</Name>", capabilities)
            self._years = sorted(set(names))
        return self._years

    def fetch(self, lat: float, lon: float) -> Dict:
        sheets = []
        for layer in self._year_layers():
            gml = self._wfs(REQUEST="GetFeature", TYPENAMES=layer, COUNT=10000,
                            PROPERTYNAME="godlo,akt_rok,char_przestrz,format,uklad_xy,url_do_pobrania,msGeometry",
                            BBOX=f"{lat},{lon},{lat + osm.TILE_DEG},{lon + osm.TILE_DEG},urn:ogc:def:crs:EPSG::4326")
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
        return {"layers": self._year_layers(), "sheets": sheets}


class StacItems(Listing):
    """Items of a STAC collection (swisstopo), one per tile and survey year
    (`<product>_<year>_<E>-<N>`, E and N in tile_m units), searched with pystac-client
    (GET, pages of 100 following the `next` links); every GeoTIFF asset at a resolution of
    sizes is listed, with the sha256 of its file:checksum (a multihash) and the tile's extent
    in crs."""

    def __init__(self, url: str, crs: str, sizes: Dict[float, float], tile_m: float):
        self.url, self.crs, self.sizes, self.tile_m = url, crs, sizes, tile_m

    def _pages(self, lat: float, lon: float) -> List[Dict]:
        """The answers of the search, page by page; IndexUnavailable when one cannot be had."""
        # Imported here: the web process imports sources (the about page) and needs none of it
        from pystac_client.exceptions import APIError
        from pystac_client.item_search import ItemSearch
        from pystac_client.stac_api_io import StacApiIO

        stac_io = StacApiIO(headers=cache.http_headers(), timeout=120, max_retries=0)
        search = ItemSearch(self.url, method="GET", bbox=(lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG),
                            limit=100, stac_io=stac_io)
        try:
            return list(search.pages_as_dicts())
        except (APIError, requests.RequestException, ValueError) as e:  # APIError is no RequestException
            raise IndexUnavailable(f"STAC API: {e}") from e

    def fetch(self, lat: float, lon: float) -> Dict:
        sheets = []
        for page in self._pages(lat, lon):
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
