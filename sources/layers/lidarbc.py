"""LidarBcBlocks: British Columbia's LidarBC DEM and DSM, found through the LidarBC index (an ArcGIS FeatureServer),
confirmed by a listing of GeoBC's S3 bucket, read in blocks and composed newest survey first."""

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from rasterio.warp import transform_bounds

import grid
import osm

from ..indexes.arcgis import query_features, ring_bounds
from ..indexes.cached import CachedIndex, Listing
from ..indexes.s3listing import S3Object, list_objects
from ..indexes.versions import ComposedBlocks
from ..readers.windows import Windows
from .indexed import IndexedTiles
from .s3blocks import S3Blocks

# NAD83(CSRS) / UTM zones 7-12 (the files of zones 8-11 name them; 2023+ files the compound CRS of zones 9-11 with
# CGVD2013 height, EPSG:6652-6654, whose horizontal part is this: readers.windows._same_crs)
CSRS_UTM = {7: "EPSG:3154", 8: "EPSG:3155", 9: "EPSG:3156", 10: "EPSG:3157", 11: "EPSG:2955", 12: "EPSG:2956"}
BC_ALBERS = "EPSG:3005"  # NAD83 / BC Albers: 38 tiles of BCTS 2016 (2 m), projection "bcalb"
# The files reach a little beyond their BCGS sheet or tile (a 1:2 500 tile of 1.81 x 1.39 km is a file of
# 1890 x 1481 px): the listed extent is the footprint's box in the file's CRS with this margin, whole metres outwards
EXTENT_MARGIN = 100.0
LIDARBC_FIELDS = ("maptile", "year", "projection", "s3Url")
BCGS_SHEET = re.compile(r"\d{3}[a-p]\d{3}", re.I)  # a BCGS 1:20 000 sheet (082e023), the start of its tiles' names


def bc_utm_crs(lat: float, lon: float) -> str:
    """NAD83(CSRS) / UTM zone containing the point, e.g. EPSG:2955 (zone 11): the CRS of LidarBC's files (zones
    7-12 of British Columbia and its neighbours; elsewhere the WGS84 zone)."""
    zone = min(60, int((lon + 180) // 6) + 1)
    return CSRS_UTM[zone] if lat >= 0 and zone in CSRS_UTM else grid.utm_crs(lat, lon)


def file_crs(name: str, projection: str, west: float, south: float, east: float, north: float) -> str:
    """The horizontal CRS of a LidarBC file: the zone its name gives (`_utm10_`), else the index's `projection`
    (utm08, utm9, bcalb), else the zone of its footprint's centre (NDMP Okanagan 2017: no zone named, EPSG:2955)."""
    zone = re.search(r"_utm0?(\d{1,2})(?=_|\.|$)", name, re.I)
    if zone and int(zone.group(1)) in CSRS_UTM:
        return CSRS_UTM[int(zone.group(1))]
    projection = (projection or "").strip().lower()
    if projection == "bcalb":
        return BC_ALBERS
    zone = re.fullmatch(r"utm0?(\d{1,2})", projection)
    if zone and int(zone.group(1)) in CSRS_UTM:
        return CSRS_UTM[int(zone.group(1))]
    return bc_utm_crs((south + north) / 2, (west + east) / 2)


class LidarBcFiles(Listing):
    """The files of LidarBC's DEM or DSM in one 0.25° tile: the FeatureServer's layers of the model (a 1:20 000 and
    a 1:2 500 index) name each file with its BCGS footprint, survey year and address (s3Url); the bucket is then
    listed (ListObjectsV2) under the prefix of each sheet and survey year they name (`<NNN>/<NNNl>/<year>/<dem|dsm>/
    bc_<sheet>`: every file of that 1:20 000 sheet and its 1:2 500 tiles in that year's folder), and only the files
    listed are kept, with their ETag and LastModified from the listing. The index has wrong entries (LAZ point
    clouds named `.tif`, a few paths of a "2011" folder that does not exist): they are not listed, so they drop out.

    Items as ComposedBlocks caches them: {name: <stem>@<etag8>, url, crs (the file's horizontal CRS), extent (the
    footprint's box in it with EXTENT_MARGIN), year (the survey folder's), published (LastModified)}."""

    def __init__(self, url: str, layers: Sequence[int], bucket: str):
        self.url, self.layers, self.bucket = url, tuple(layers), bucket.rstrip("/")
        self.bucket_name = urlsplit(self.bucket).path.strip("/").split("/")[-1]

    def _key(self, s3url: str) -> Optional[str]:
        """The key in the bucket of an index entry's address (its host is not compared: the tests serve both)."""
        path = urlsplit(s3url or "").path.lstrip("/")
        head, _, key = path.partition("/")
        return key if head == self.bucket_name and key else None

    def fetch(self, lat: float, lon: float) -> Dict:
        box = (lon, lat, lon + osm.TILE_DEG, lat + osm.TILE_DEG)
        named: Dict[str, Dict] = {}  # key: the feature naming it (the first)
        for layer in self.layers:
            for feature in query_features(f"{self.url.rstrip('/')}/{layer}", box, LIDARBC_FIELDS):
                key = self._key(feature.get("attributes", {}).get("s3Url"))
                if key and key.lower().endswith(".tif") and feature.get("geometry"):
                    named.setdefault(key, feature)
        prefixes: List[str] = []
        for key in sorted({_prefix(key, f["attributes"].get("maptile")) for key, f in named.items()}):
            if not prefixes or not key.startswith(prefixes[-1]):  # one listing covers the longer prefixes
                prefixes.append(key)
        listed: Dict[str, S3Object] = {}
        for prefix in prefixes:
            for obj in list_objects(self.bucket, prefix):
                listed[obj.key] = obj
        items = []
        for key, feature in named.items():
            obj = listed.get(key)
            if obj is not None:
                items.append(self._item(key, obj, feature))
        return {"sheets": items}

    def _item(self, key: str, obj: S3Object, feature: Dict) -> Dict:
        attributes = feature["attributes"]
        west, south, east, north = ring_bounds(feature["geometry"])
        file = key.rsplit("/", 1)[-1]
        crs = file_crs(file, attributes.get("projection") or "", west, south, east, north)
        left, bottom, right, top = transform_bounds("EPSG:4326", crs, west, south, east, north, densify_pts=21)
        # Whole metres, outwards: PROJ's last digits differ between platforms, the cached index must not
        extent = [math.floor(left - EXTENT_MARGIN), math.floor(bottom - EXTENT_MARGIN),
                  math.ceil(right + EXTENT_MARGIN), math.ceil(top + EXTENT_MARGIN)]
        folders = key.split("/")
        year = int(folders[2]) if len(folders) > 2 and folders[2].isdigit() else int(attributes.get("year") or 0)
        return {"name": f"{file[:-4]}@{obj.etag[:8]}", "url": f"{self.bucket}/{key}", "crs": crs, "extent": extent,
                "year": year, "published": obj.last_modified}


def _prefix(key: str, maptile: Optional[str]) -> str:
    """The listing prefix of a file: its folder and `bc_<sheet>` (the 1:20 000 sheet of its maptile), or the key
    itself when its name does not start so."""
    folder, _, file = key.rpartition("/")
    sheet = BCGS_SHEET.match(maptile or "")
    if sheet and file.lower().startswith(f"bc_{sheet.group().lower()}"):
        return f"{folder}/{file[:3 + len(sheet.group())]}"
    return key


class LidarBcBlocks(S3Blocks):
    """Blocks of block_m on the pixels of LidarBC's files (GeoBC: DEM or DSM GeoTIFFs per BCGS 1:20 000 sheet or
    1:2 500 tile and survey year, in NAD83(CSRS) / UTM of their zone), found through LidarBcFiles (cached per 0.25°
    tile for ttl_days: new surveys are published monthly), read by HTTP range requests (Windows: tiled files, COGs,
    and the 2022+ files of one-row strips, whose rows are read whole) and composed newest survey first
    (ComposedBlocks): a sheet holds several partial surveys, each clipped to its flights, and an older file is read
    only while a block has holes. A file's ETag is part of its name: a file uploaded again changes its blocks' key.

    An S3Blocks for the tools (check_source compares its blocks with the files) and the probe, but with its own
    index: the bucket's prefixes come from the FeatureServer, not from names over a box. Files of 2 m (BCTS 2016)
    are read bilinearly onto the blocks' 1 m pixels; files whose pixel edges are off whole metres (NDMP 2017) too.
    The tie point of the "PixelIsPoint" files (2015-2018, 2021-2022) is read as GDAL reads it (see the source's
    comment in catalogue/canada.py)."""

    def __init__(self, description: str, featureserver: str, layers: Sequence[int], bucket: str, prefix: str,
                 folder: str, native_res: float = 1.0, block_m: float = 1000, bytes_per_tile: float = 4e6,
                 ttl_days: float = 30, serial: bool = False):
        IndexedTiles.__init__(self, description, featureserver, prefix, folder, native_res, bytes_per_tile)
        self.featureserver, self.layers, self.bucket, self.block_m = featureserver, tuple(layers), bucket, block_m
        self.index_crs = BC_ALBERS  # unused: every item names its own CRS
        self.index = CachedIndex(description, LidarBcFiles(featureserver, layers, bucket),
                                 ComposedBlocks(folder, block_m, native_res), prefix, folder.split("/")[0],
                                 ttl_days=ttl_days)
        self.reader = Windows(description, serial=serial)

    def _box(self, lat: float, lon: float) -> Tuple[float, float, float, float]:
        raise NotImplementedError("LidarBcFiles lists by the FeatureServer's footprints")
