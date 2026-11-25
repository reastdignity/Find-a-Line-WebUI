"""Regione Toscana's cartoteca (Tuscany's lidar sheets of 1:2000): its WFS feature type `rt_cartoteca.lidar2k`, which
the capabilities do not name but which answers (CartotecaSheets), and the versions of a sheet a grid uses
(CartotecaVersions): every survey of a sheet whose footprint adds data to the newer ones, newest first.

A sheet (`foglio`, 1600 x 1200 m in EPSG:3003) has one entry per survey (`lotto`, `anno`, `risoluz` 1x1 or 2x2), each
a file of the whole sheet with a 20 m buffer that holds data only within the survey's footprint (the feature's
geometry, in EPSG:3003; a survey often covers part of a sheet and an older one the rest: 22d35 near Carrara, 14 % by
the RT survey of 2012, 93 % by MATTM's of 2010). The files' URLs carry a hash the index does not give: the reader
asks a GetFeatureInfo at one of the `points` of an entry (sources/readers/cartoteca.py)."""

import contextlib
import glob
import io
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from rasterio.warp import transform_bounds

import cache
import osm
import servicecounts
from grid import Grid

from .. import net
from .cached import CachedIndex, IndexUnavailable, Listing, Versions, index_tiles
from .listings import XML_ROOT, ows_exception
from .versions import _answers

CARTOTECA_CRS = "EPSG:3003"  # Monte Mario / Italy zone 1 (Gauss-Boaga, fuso Ovest): the sheets', the files'
BUFFER_M = 20.0              # each file holds its sheet and 20 m around it (the neighbours' data, the same values)
# A sheet whose newer surveys' footprints cover this share of it needs no older one (the footprints lie about 0.4 m
# off the sheets' edges, transformed from another CRS: a whole sheet is covered to 0.9992)
SHEET_COVERED = 0.995
# A survey after the first one kept is used where it adds at least this share of its sheet (19 200 m² at 1:2000) to
# the ones kept before it: below it, the file is downloaded for a sliver along an edge (22d54's survey of 2010 adds
# 56 m² to that of 2012). The newest survey (or a sole one) is always kept, however small
MIN_ADDED = 0.01
# The most features one answer may hold (MAXFEATURES asked): a 0.25° tile holds at most about 700 entries (the Apuan
# Alps, 2026-11-15); an answer of exactly this many may be cut, an error
FEATURES_MAX = 5000
# The most bytes one answer may have (the footprints are polygons of up to thousands of vertices: 1.8 MB for the
# 471 entries of the tile at Carrara, 2026-11-15)
ANSWER_BYTES = 200_000_000
# Where a GetFeatureInfo is asked within a survey's own part of its sheet: this far inside its edge (metres), the
# label point found to this tolerance (shapely.ops.polylabel)
POINT_INSET_M = 2.0
POINT_TOLERANCE_M = 2.0
# The entries' names: <foglio>_<res>x<res>_<dtm|dsm>_<lotto>_<anno>_<srid> (the attribute dtmname, dsmname)
ENTRY_NAME = re.compile(r"^(?P<foglio>[0-9a-z]+)_(?P<res>\d+)x\d+_(?P<kind>dtm|dsm)_(?P<lot>\d+)_(?P<year>\d{4})_3003$",
                  re.IGNORECASE)
# The attributes asked (the geometry is the survey's footprint; eg_bsw..ng_bne the sheet, 0 for the surveys of
# 2016 and 2017, whose sheet is then that of another survey or the footprint's box)
PROPERTIES = "GEOMETRY,foglio,dtmname,dsmname,eg_bsw,ng_bsw,eg_bne,ng_bne"


@dataclass(frozen=True)
class LidarSheet:
    """One survey of one sheet: its files' names (the DTM's and the DSM's, without their hash), where its data lie
    (extent, in EPSG:3003: its footprint's box within its file) and where a GetFeatureInfo finds it (points, its
    own part of the sheet first)."""
    year: int
    lot: str
    res: float
    godlo: str  # the sheet (foglio), lower case
    dtm: str
    dsm: str
    extent: Tuple[float, float, float, float]
    points: Tuple[Tuple[float, float], ...] = ()
    crs: str = CARTOTECA_CRS

    @property
    def version(self) -> str:
        """The survey's folder in the cache: <lotto>-<anno>."""
        return f"{self.lot}-{self.year}"

    @property
    def name(self) -> str:
        return f"{self.godlo}_{self.res:g}m"


def sheet_rank(sheet) -> tuple:
    """Newer surveys first; within a year 1 m before 2 m, then the later lot; the sheet's name last (no ties)."""
    return (sheet["year"], -sheet["res"], sheet["lot"], sheet["godlo"]) if isinstance(sheet, dict) else \
        (sheet.year, -sheet.res, sheet.lot, sheet.godlo)


def _capped(response, limit: int) -> bytes:
    """The body of a streamed answer, at most limit bytes (more is an error: the connection is closed)."""
    chunks, size = [], 0
    try:
        for chunk in response.iter_content(65536):
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise IndexUnavailable(f"WFS GetFeature: the answer has more than {limit} bytes")
    finally:
        response.close()
    return b"".join(chunks)


def _features(gml: bytes) -> List[Tuple[Dict, object]]:
    """The features of a GML FeatureCollection as (attributes, shapely geometry or None), read by GDAL's GML
    driver through pyogrio; an empty collection has none. An answer that is no FeatureCollection is
    IndexUnavailable (an error page is never cached as a tile without sheets)."""
    import shapely
    from pyogrio import raw
    from pyogrio.errors import DataLayerError, DataSourceError

    root = XML_ROOT.match(gml)
    if not root or root.group(1) != b"FeatureCollection":
        raise IndexUnavailable(f"WFS GetFeature: not a FeatureCollection ({gml[:80]!r})")
    try:
        meta, _, geometry, values = raw.read(io.BytesIO(gml), layer=0, DOWNLOAD_SCHEMA="NO")
    except DataLayerError:  # an empty collection has no layer when its schema is not read
        return []
    except DataSourceError as e:
        raise IndexUnavailable(f"WFS GetFeature: the answer cannot be read ({e})") from e
    names = list(meta["fields"])
    out = []
    for k in range(len(geometry)):
        shape = shapely.from_wkb(geometry[k]) if geometry[k] is not None else None
        if shape is not None and not shape.is_valid:
            shape = shapely.make_valid(shape)
        out.append(({name: values[i][k] for i, name in enumerate(names)}, shape))
    return out


def _attribute_number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rectangle(attributes: Dict) -> Optional[Tuple[float, float, float, float]]:
    """The sheet of an entry from eg_bsw..ng_bne (None where they are 0: the surveys of 2016 and 2017)."""
    left, bottom, right, top = (_attribute_number(attributes.get(k)) for k in ("eg_bsw", "ng_bsw", "eg_bne", "ng_bne"))
    return (left, bottom, right, top) if right > left > 0 and top > bottom > 0 else None


def _label(geometry) -> Optional[Tuple[float, float]]:
    """A point well inside the largest part of a polygonal geometry (POINT_INSET_M from its edge), or None when
    nothing of it is left so far inside."""
    import shapely
    from shapely.ops import polylabel
    if geometry is None or geometry.is_empty:
        return None
    inner = geometry.buffer(-POINT_INSET_M)
    parts = [p for p in shapely.get_parts(inner) if p.geom_type == "Polygon" and not p.is_empty]
    if not parts:
        return None
    point = polylabel(max(parts, key=lambda p: p.area), POINT_TOLERANCE_M)
    return round(point.x, 1), round(point.y, 1)


def select_versions(entries: List[Dict]) -> List[Dict]:
    """The surveys of one sheet worth reading, best first (sheet_rank), each with its points: the first is always
    kept; a later one while the ones kept before it cover less than SHEET_COVERED of the sheet
    and it adds at least MIN_ADDED of it (an entry without a footprint covers the whole sheet). An entry is
    {"year", "lot", "res", "godlo", "dtm", "dsm", "rectangle", "footprint"}; the answer's are {..., "extent",
    "points"} without the shapes."""
    import shapely
    from shapely.geometry import box
    rectangle = next((e["rectangle"] for e in entries if e["rectangle"]), None)
    if rectangle is None:  # no survey names its sheet: the box of all footprints, on whole metres
        footprints = [e["footprint"] for e in entries if e["footprint"] is not None and not e["footprint"].is_empty]
        if not footprints:
            return []
        left, bottom, right, top = shapely.union_all(footprints).bounds
        rectangle = (math.floor(left), math.floor(bottom), math.ceil(right), math.ceil(top))
    sheet = box(*rectangle)
    area = sheet.area
    ordered = sorted(entries, key=sheet_rank, reverse=True)
    shapes = [sheet if e["footprint"] is None or e["footprint"].is_empty else e["footprint"].intersection(sheet)
              for e in ordered]
    used, covered = [], None
    for k, (entry, shape) in enumerate(zip(ordered, shapes)):
        if covered is not None and covered.area >= SHEET_COVERED * area:
            break
        added = shape if covered is None else shape.difference(covered)
        if added.is_empty or (covered is not None and added.area < MIN_ADDED * area):
            continue
        others = [s for j, s in enumerate(shapes) if j != k]
        own = shape.difference(shapely.union_all(others)) if others else shape
        points = [p for p in (_label(own), _label(added), _label(shape)) if p is not None]
        if not points:  # narrower than twice POINT_INSET_M: a point on it all the same
            inside = added.representative_point()
            points = [(round(inside.x, 1), round(inside.y, 1))]
        # Its data: the footprint's box grown by the buffer, within the file (the sheet and its buffer)
        f_left, f_bottom, f_right, f_top = shape.bounds
        extent = (max(rectangle[0] - BUFFER_M, math.floor(f_left - BUFFER_M)),
                  max(rectangle[1] - BUFFER_M, math.floor(f_bottom - BUFFER_M)),
                  min(rectangle[2] + BUFFER_M, math.ceil(f_right + BUFFER_M)),
                  min(rectangle[3] + BUFFER_M, math.ceil(f_top + BUFFER_M)))
        used.append({k2: entry[k2] for k2 in ("year", "lot", "res", "godlo", "dtm", "dsm")}
                    | {"extent": [float(v) for v in extent], "points": [list(p) for p in dict.fromkeys(points)]})
        covered = shape if covered is None else covered.union(shape)
    return used


class CartotecaSheets(Listing):
    """The sheets of the cartoteca's lidar over a 0.25° tile: one WFS 1.1.0 GetFeature (MapServer, GML 3.1.1) with
    the box in EPSG:4326 (lat, lon), the footprints in EPSG:3003 (SRSNAME), only the attributes used (PROPERTIES);
    per sheet the surveys select_versions keeps, each with its extent and points (cached as
    {"sheets": [{"year", "lot", "res", "godlo", "dtm", "dsm", "crs", "extent", "points"}]}, by sheet_rank). An
    exception report (also with HTTP 200), an answer that is no FeatureCollection, one of FEATURES_MAX features (it
    may be cut) or of more than ANSWER_BYTES is IndexUnavailable, an HTTP error a RequestException: nothing is
    cached then. The request takes a slot of its host (net.host_slot, once use() gave the data folder) and a turn
    (net.rate_turn)."""

    def __init__(self, url: str, typename: str):
        self.url, self.typename = url, typename
        self._cache_dir: Optional[str] = None

    def use(self, index, cache_dir: str, update: Optional[str] = None):
        """The data folder of the index asking (the host slots)."""
        self._cache_dir = cache_dir

    def fetch(self, lat: float, lon: float) -> Dict:
        params = {"SERVICE": "WFS", "VERSION": "1.1.0", "REQUEST": "GetFeature", "TYPENAME": self.typename,
                  "SRSNAME": CARTOTECA_CRS, "PROPERTYNAME": PROPERTIES, "MAXFEATURES": str(FEATURES_MAX),
                  "BBOX": f"{lat},{lon},{lat + osm.TILE_DEG},{lon + osm.TILE_DEG},urn:ogc:def:crs:EPSG::4326"}
        slot = net.host_slot(self._cache_dir, self.url) if self._cache_dir else contextlib.nullcontext()
        with slot:
            net.rate_turn(self.url)
            with servicecounts.request(self.url) as counted:
                response = counted.got(net.session().get(self.url, timeout=300, headers=cache.http_headers(),
                                                         params=params, verify=net.verify(self.url), stream=True),
                                       read=False)
                if response.status_code != 200:
                    response.close()
                response.raise_for_status()
                body = _capped(response, ANSWER_BYTES)
                counted.add(len(body))
        error = ows_exception(body)
        if error:  # answered with HTTP 200: not an answer to cache
            raise IndexUnavailable(f"WFS GetFeature: {error}")
        features = _features(body)
        if len(features) >= FEATURES_MAX:
            raise IndexUnavailable(f"WFS GetFeature: {len(features)} features, the most asked (a cut listing)")
        per_sheet: Dict[str, List[Dict]] = {}
        for attributes, footprint in features:
            dtm, dsm = str(attributes.get("dtmname") or ""), str(attributes.get("dsmname") or "")
            name = ENTRY_NAME.match(dtm)
            if not name or name.group("kind").lower() != "dtm":
                continue
            other = ENTRY_NAME.match(dsm)
            if not other or other.group("kind").lower() != "dsm" or \
                    other.group("foglio", "res", "lot", "year") != name.group("foglio", "res", "lot", "year"):
                dsm = ""
            godlo = name.group("foglio").lower()
            per_sheet.setdefault(godlo, []).append({
                "year": int(name.group("year")), "lot": name.group("lot"), "res": float(name.group("res")),
                "godlo": godlo, "dtm": dtm, "dsm": dsm, "rectangle": _rectangle(attributes), "footprint": footprint})
        sheets = [dict(s, crs=CARTOTECA_CRS) for entries in per_sheet.values() for s in select_versions(entries)]
        return {"sheets": sorted(sheets, key=sheet_rank, reverse=True)}


def _sheet_of(item: Dict) -> LidarSheet:
    return LidarSheet(item["year"], item["lot"], item["res"], item["godlo"], item["dtm"], item["dsm"],
                      tuple(item["extent"]), tuple(tuple(p) for p in item.get("points", ())), item["crs"])


@dataclass(frozen=True)
class CartotecaRequest:
    """What the reader needs to fetch one file of a survey of a sheet: its name (the DTM's or the DSM's, without
    the hash), the points of its GetFeatureInfo and the file of its resolved URLs (urls)."""
    sheet: LidarSheet
    name: str
    urls: str

    @property
    def godlo(self) -> str:
        return self.sheet.godlo

    @property
    def crs(self) -> str:
        return self.sheet.crs

    @property
    def res(self) -> float:
        return self.sheet.res


class CartotecaVersions(Versions):
    """Every survey of a sheet the listing keeps (select_versions), newest first (sheet_rank), so the mosaic takes a
    sheet's newest data and the older ones only where they have no data: a file of a model (kind "dtm" or "dsm")
    cached as <folder>/<lotto>-<anno>/<foglio>_<res>m.tif, its resolved URLs as
    <urls_folder>/<lotto>-<anno>/<foglio>_<res>m.json (one file for both models). A survey listed once is never
    deleted (prune: none): a newer one over a sheet only comes first."""

    def __init__(self, folder: str, kind: str, urls_folder: str):
        self.folder, self.kind, self.urls_folder = folder, kind, urls_folder
        self._cache_dir: Optional[str] = None  # where request() puts the resolved URLs (query, update_tile)

    def _sheets(self, items: Sequence[Dict]) -> List[LidarSheet]:
        """The listed surveys with a file of this model, each once (a sheet across two index tiles is in both)."""
        found: Dict[Tuple, LidarSheet] = {}
        for item in items:
            sheet = _sheet_of(item)
            if not getattr(sheet, self.kind):
                continue
            key = (sheet.godlo, sheet.version, sheet.res)
            old = found.get(key)
            if old is not None:  # the points of both answers (the tiles may see different parts of the sheet)
                sheet = LidarSheet(*[getattr(old, f) for f in ("year", "lot", "res", "godlo", "dtm", "dsm")],
                                   tuple(min(a, b) if i < 2 else max(a, b)
                                         for i, (a, b) in enumerate(zip(old.extent, sheet.extent))),
                                   tuple(dict.fromkeys(old.points + sheet.points)), old.crs)
            found[key] = sheet
        return list(found.values())

    def query(self, index: CachedIndex, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        """The surveys over the grid (their extents meet its box and its outline), best first."""
        self._cache_dir = cache_dir
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, CARTOTECA_CRS, *grid.bounds)
        shape = None
        if grid.area_shape is not None:
            import shapely
            from area import project
            from shapely.geometry import box
            shape = project(grid.area_shape, grid.crs, CARTOTECA_CRS).intersection(
                box(g_left, g_bottom, g_right, g_top))
            shapely.prepare(shape)
        items = [item for answer in _answers(index, cache_dir, index_tiles(grid), update) for item in answer]
        sheets = []
        for sheet in self._sheets(items):
            left, bottom, right, top = sheet.extent
            if not (left < g_right and right > g_left and bottom < g_top and top > g_bottom):
                continue
            if shape is not None:
                from shapely.geometry import box
                if not shape.intersects(box(left, bottom, right, top)):
                    continue
            sheets.append(sheet)
        return sorted(sheets, key=sheet_rank, reverse=True)

    def path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.folder, tile.version, f"{tile.name}.tif")

    def urls_path(self, cache_dir: str, tile) -> str:
        return os.path.join(cache_dir, self.urls_folder, tile.version, f"{tile.name}.json")

    def request(self, tile) -> CartotecaRequest:
        return CartotecaRequest(tile, getattr(tile, self.kind), self.urls_path(self._cache_dir or "", tile))

    def _cached_sheet(self, path: str, extent: bool = True) -> Optional[LidarSheet]:
        """The survey of a cached file by its path (no names or points), with the file's own extent (else 0s)."""
        version = re.fullmatch(r"(\d+)-(\d{4})", os.path.basename(os.path.dirname(path)))
        name = re.fullmatch(r"([0-9a-z]+)_(\d+(?:\.\d+)?)m\.tif", os.path.basename(path), re.IGNORECASE)
        if not version or not name:
            return None
        bounds = (0.0, 0.0, 0.0, 0.0)
        if extent:
            import rasterio as rio
            with rio.open(path) as src:
                bounds = tuple(src.bounds)
        return LidarSheet(int(version.group(2)), version.group(1), float(name.group(2)), name.group(1).lower(), "",
                          "", bounds)

    def cached(self, grid: Grid, cache_dir: str) -> list:
        """The cached surveys over the grid, best first (when the index cannot be reached)."""
        g_left, g_bottom, g_right, g_top = transform_bounds(grid.crs, CARTOTECA_CRS, *grid.bounds)
        sheets = []
        for path in glob.glob(os.path.join(glob.escape(cache_dir), self.folder, "*", "*.tif")):
            sheet = self._cached_sheet(path)
            if sheet is None:
                continue
            left, bottom, right, top = sheet.extent
            if left < g_right and right > g_left and bottom < g_top and top > g_bottom:
                sheets.append(sheet)
        return sorted(sheets, key=sheet_rank, reverse=True)

    def prune(self, cache_dir: str, tiles: list) -> int:
        return 0  # the older surveys fill the newer ones' gaps: none is replaced

    def update_tile(self, index: CachedIndex, cache_dir: str, lat: float, lon: float) -> Tuple[list, list]:
        """After the index of one tile was asked again: the surveys listed for the sheets with a cached file that
        are not cached yet (a new survey, or an older one now worth reading); nothing is deleted."""
        self._cache_dir = cache_dir
        listed = self._sheets(_answers(index, cache_dir, [(lat, lon)], "all")[0])
        cached = {s.godlo for s in self.cached_sheets(cache_dir)}
        todo = [s for s in listed if s.godlo in cached and not os.path.exists(self.path(cache_dir, s))]
        return sorted(todo, key=sheet_rank, reverse=True), []

    def cached_sheets(self, cache_dir: str) -> List[LidarSheet]:
        """Every cached survey of this model (names, points and extents unknown)."""
        paths = glob.glob(os.path.join(glob.escape(cache_dir), self.folder, "*", "*.tif"))
        found = (self._cached_sheet(p, extent=False) for p in paths)
        return [s for s in found if s is not None]
