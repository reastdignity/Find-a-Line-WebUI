"""InegiSheets: INEGI's 1:10 000 sheets (Mexico's 5 m lidar terrain and surface models), each found through the
download viewer's JSON of one sheet and downloaded whole as a ZIP holding an ArcInfo GRID."""

import json
import math
import os
import re
import shutil
import zipfile
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np
from affine import Affine
import rasterio as rio
import requests
from rasterio.features import geometry_mask

import cache
import servicecounts
from grid import Grid

from .. import net
from ..composed import ComposedLayer, Reader
from ..indexes.tilings import GeoCellTiling
from ..layer import Fetched, _write_tile, float_band
from ..net import _part, tile_lock

# INEGI's 1:10 000 grid: cells of 3'20" of longitude x 3'45" of latitude in a global lattice from 180° W and the
# equator (cell (i, j) = (floor((lon + 180) * 18), floor(lat * 16)), j northwards). A sheet's name is its place in
# the International Map of the World's sheets: the 1:1 000 000 sheet (a letter for its band of 4° of latitude, A
# at the equator, and its zone of 6° of longitude, the UTM zone), the 1:250 000 quarter (A-D: 2° x 3°, A north-
# west, B north-east, C south-west, D south-east), the 1:50 000 sheet (two digits, the row 1-8 from its north and
# the column 1-9 from its west: 15' x 20'), the 1:20 000 sixth (A-F, three columns in two rows from the north-west:
# 7'30" x 6'40") and the 1:10 000 quarter (1-4, two columns in two rows). G14C15B2 is El Potrero Chico. Checked
# against every sheet of the viewer's lists of the 5 m terrain and surface models (getFormato10k.do: 26 334 and
# 26 333 sheets, their centroids in Web Mercator; all names equal, tools/mx_sheets.py, 2026-11-15)
INEGI_CELL = (1 / 18, 1 / 16)
INEGI_ORIGIN = (-180.0, 0.0)
_BANDS = "ABCDEFGHIJKLMNOPQRSTUV"  # 4° bands of latitude from the equator northwards
_SIXTHS = "ABCDEF"
_NAME = re.compile(r"([A-V])(\d\d)([ABCD])([1-8])([1-9])([A-F])([1-4])")


def inegi_sheet(i: int, j: int) -> Optional[str]:
    """The name of the 1:10 000 sheet of cell (i, j) (G14C15B2), None outside the northern hemisphere's lattice."""
    if not (0 <= i < 360 * 18 and 0 <= j < len(_BANDS) * 64):
        return None
    zone, col = i // 108 + 1, i % 108        # 108 cells of a 6° zone, from its west
    band, row = j // 64, 63 - j % 64         # 64 cells of a 4° band, its rows from its north
    quarter = "ABCD"[(row // 32) * 2 + col // 54]
    row50, col50 = (row % 32) // 4 + 1, (col % 54) // 6 + 1
    sixth = _SIXTHS[((row % 4) // 2) * 3 + (col % 6) // 2]
    return f"{_BANDS[band]}{zone:02d}{quarter}{row50}{col50}{sixth}{(row % 2) * 2 + col % 2 + 1}"


def inegi_cell(name: str) -> Optional[Tuple[int, int]]:
    """The cell (i, j) of a sheet's name, None when it is not one."""
    match = _NAME.fullmatch(name.upper())
    if not match:
        return None
    band, zone, quarter, row50, col50, sixth, part = match.groups()
    q, s, p = "ABCD".index(quarter), _SIXTHS.index(sixth), int(part) - 1
    row = (q // 2) * 32 + (int(row50) - 1) * 4 + (s // 3) * 2 + p // 2
    col = (q % 2) * 54 + (int(col50) - 1) * 6 + (s % 3) * 2 + p % 2
    cell = (int(zone) - 1) * 108 + col, _BANDS.index(band) * 64 + 63 - row
    return cell if inegi_sheet(*cell) == name.upper() else None


def inegi_crs(name: str) -> str:
    """The CRS of a sheet's GRID, which names none: Mexico ITRF92 / UTM of the zone of its 1:1 000 000 sheet
    (zones 11-16, EPSG:4484-4489; INEGI's metadata: "ITRF92 Época 1988.0", the GRID's edges on whole 5 m of that
    zone)."""
    zone = int(name[1:3])
    if not 11 <= zone <= 16:
        raise ValueError(f"sheet {name}: zone {zone} is not one of Mexico's (11-16)")
    return f"EPSG:{4484 + zone - 11}"


class InegiSheet(NamedTuple):
    """A sheet of one model as its JSON gives it: its cell, name, edition (one per sheet), ZIP and CRS."""
    i: int
    j: int
    name: str
    edition: int
    url: str
    crs: str


def grid_entry(items: List[Dict], mod: str, url_prefix: str) -> Optional[Tuple[int, str]]:
    """(edition, URL of the ZIP) of the GRID product (archivo "|_gr.zip,<size>") of a model (mod "T" terrain, "S"
    surface) among a sheet's JSON items, the newest edition of several; None when the sheet has none (an empty
    answer: no such sheet). A URL that does not start with url_prefix is refused (RuntimeError): only INEGI's own
    file server is asked."""
    found = []
    for item in items:
        archivo = str(item.get("archivo") or "").lstrip("|").split(",", 1)[0].strip()
        if str(item.get("mod")) != mod or archivo != "_gr.zip":
            continue
        url = f"{str(item.get('url_descarga') or '').rstrip('/')}{archivo}"
        if not url.startswith(url_prefix):
            raise RuntimeError(f"a download outside {url_prefix}: {cache.clean_url(url)}")
        try:
            edition = int(item.get("edicion"))
        except (TypeError, ValueError):
            raise RuntimeError(f"an edition that is no year: {item.get('edicion')!r}") from None
        found.append((edition, url))
    return max(found) if found else None


class InegiIndex(GeoCellTiling):
    """The sheets of one model (mod "T" or "S") over a grid: the cells of INEGI's lattice under the grid whose sheet
    the static mask lists (cells, the .npz of tools/mx_sheets.py: `<mod>_bits` packed, `shape` rows x columns and
    `origin` (i, j) of its first cell), each asked of the viewer's JSON (index_url?res=5&mod=<mod>&cve=<sheet>) for
    its edition and ZIP. The answers are cached per sheet in <top>/sheet-index/<mod>/<sheet>.json and asked again
    only by an update after ttl_days; a sheet whose answer holds no GRID product is no tile. When the JSON cannot be
    asked, a cached answer is used however old; without one the sheet is left out (said once per grid). The
    sheet's ZIP is cached as <folder>/<edition>_<sheet>.tif (a new edition is a new file: the older one is deleted
    once it is downloaded, prune)."""

    def __init__(self, folder: str, mod: str, index_url: str, url_prefix: str, cells: str, top: str,
                 ttl_days: int):
        super().__init__("EPSG:4326", folder, INEGI_CELL, INEGI_ORIGIN)
        self.mod, self.index_url, self.url_prefix, self.cells, self.top = mod, index_url, url_prefix, cells, top
        self.ttl_days = ttl_days
        self.cache_dir: Optional[str] = None
        self.update: Optional[str] = None
        self._mask = None
        self._listed: Dict[tuple, List[InegiSheet]] = {}

    def use(self, cache_dir: str, update: Optional[str] = None):
        """What tiles() needs (it gets only the grid)."""
        self.cache_dir, self.update = cache_dir, update

    def mask(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        """(mask of the cells with a sheet, rows j0.. by columns i0..; (i0, j0)), loaded once."""
        if self._mask is None:
            with np.load(self.cells) as stored:
                rows, cols = (int(n) for n in stored["shape"])
                bits = stored[f"{self.mod.lower()}_bits"]
                i0, j0 = (int(n) for n in stored["origin"])
            self._mask = (np.unpackbits(bits, count=rows * cols).reshape(rows, cols).astype(bool), (i0, j0))
        return self._mask

    def listed(self, i: int, j: int) -> bool:
        mask, (i0, j0) = self.mask()
        r, c = j - j0, i - i0
        return 0 <= r < mask.shape[0] and 0 <= c < mask.shape[1] and bool(mask[r, c])

    def has_data_near(self, lat: float, lon: float, cache_dir: str, metres: float = 2000) -> Optional[bool]:
        """Whether a sheet of the mask lies within metres of the point (a square of +-metres in degrees)."""
        (w, h), (x0, y0) = self.cell, self.origin
        dlat = metres / 111_320.0
        dlon = metres / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        i0, i1 = math.floor((lon - dlon - x0) / w), math.floor((lon + dlon - x0) / w)
        j0, j1 = math.floor((lat - dlat - y0) / h), math.floor((lat + dlat - y0) / h)
        return any(self.listed(i, j) for j in range(j0, j1 + 1) for i in range(i0, i1 + 1))

    def answer_path(self, cache_dir: str, name: str) -> str:
        return os.path.join(cache_dir, self.top, "sheet-index", self.mod.lower(), f"{name}.json")

    def _ask(self, name: str) -> List[Dict]:
        """The JSON items of a sheet (an empty list: INEGI has no product of it); RuntimeError when it cannot be
        asked, answers 404 (only cells of the mask are asked: a 404 is a moved or broken endpoint, never "no
        sheet"), is no JSON list, or names a GRID that grid_entry refuses (a download elsewhere, an edition that is
        no year): such an answer is never cached."""
        url = f"{self.index_url}?res=5&mod={self.mod}&cve={name}"
        response = net._get(url, timeout=60, binary_types=("text", "json"))
        if response is None:
            raise RuntimeError(f"sheet {name}: the index answered 404 for a sheet of the mask")
        try:
            items = json.loads(response.content)
        except ValueError:
            raise RuntimeError(f"sheet {name}: the index answered no JSON ({response.content[:100]!r})") from None
        if not isinstance(items, list):
            raise RuntimeError(f"sheet {name}: the index answered {type(items).__name__}, a list expected")
        try:
            grid_entry(items, self.mod, self.url_prefix)
        except RuntimeError as e:
            raise RuntimeError(f"sheet {name}: {e}") from None
        return items

    def answer(self, cache_dir: str, name: str, update: Optional[str] = None) -> Optional[List[Dict]]:
        """A sheet's JSON items, asked when not cached (or stale with an update) under the answer's lock; the cached
        answer when asking fails, None without one."""
        path = self.answer_path(cache_dir, name)
        due = lambda: cache.due(cache_dir, path, update=update, ttl=self.ttl_days)  # noqa: E731
        if due():
            with tile_lock(cache_dir, path):  # another search may be asking for it now
                if due():
                    try:
                        items = self._ask(name)
                    except RuntimeError:
                        if not os.path.exists(path):
                            raise
                        items = None  # the cached answer, however old
                    if items is not None:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        tmp = _part(path)
                        with open(tmp, "w", encoding="utf-8") as out:
                            json.dump(items, out)
                        os.replace(tmp, path)
                        cache.record(cache_dir, path, url=self.index_url)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def sheets(self, cells: List[Tuple[int, int]], cache_dir: str, update: Optional[str]) -> List[InegiSheet]:
        """The sheets with a GRID product among the listed cells, in their order."""
        found, failed = [], []
        for i, j in cells:
            if not self.listed(i, j):
                continue
            name = inegi_sheet(i, j)
            try:
                items = self.answer(cache_dir, name, update)
                entry = grid_entry(items, self.mod, self.url_prefix)  # a cached answer of an older code too
            except RuntimeError as e:
                failed.append((name, e))
                continue
            if entry is not None:
                found.append(InegiSheet(i, j, name, entry[0], entry[1], inegi_crs(name)))
        if failed:
            name, error = failed[0]
            print(f"INEGI's sheet index ({self.mod}) not available for {len(failed)} sheet(s), left out "
                  f"(the first, {name}: {cache.clean_error(error)})")
        return found

    def tiles(self, grid: Grid) -> List[InegiSheet]:
        key = (str(grid.crs), tuple(grid.bounds), grid.res, self.update, id(grid.area_shape))
        if key not in self._listed:
            if self.cache_dir is None:
                raise RuntimeError("InegiIndex.use() first: the sheets' answers are cached in the data folder")
            self._listed = {key: self.sheets(super().tiles(grid), self.cache_dir, self.update)}
        return list(self._listed[key])

    def edges(self, tile) -> Tuple[float, float, float, float]:
        return super().edges((tile[0], tile[1]))

    def path(self, cache_dir: str, tile: InegiSheet) -> str:
        return os.path.join(cache_dir, self.folder, f"{tile.edition}_{tile.name}.tif")

    def tile_of(self, path: str):
        return None  # a frozen product: no update of its tiles (an edition is a new file)

    def prune(self, cache_dir: str, tiles: List[InegiSheet]) -> int:
        """Delete the cached files of other editions of the sheets whose file is cached; how many."""
        folder = os.path.join(cache_dir, self.folder)
        try:
            names = os.listdir(folder)
        except FileNotFoundError:
            return 0
        kept = {os.path.basename(self.path(cache_dir, t)) for t in tiles if os.path.exists(self.path(cache_dir, t))}
        sheets = {name.split("_", 1)[1] for name in kept}
        older = [os.path.join(folder, n) for n in names
                 if n.endswith(".tif") and "_" in n and n.split("_", 1)[1] in sheets and n not in kept]
        cache.forget(cache_dir, older)
        return len(older)


# The ArcInfo GRID's members a ZIP may hold at most, unpacked (a 5 m sheet's w001001.adf: 7 MB)
GRID_MEMBER_BYTES = 100_000_000


class InegiGrid(Reader):
    """A sheet's ZIP (one GET, streamed, at most max_bytes; a 404 is no data) holding an ArcInfo GRID
    (<MT|MS>_Grid/<sheet>_<mt|ms>/<sheet>_<mt|ms>/hdr.adf ...), saved next to the tile, its GRID unpacked into a
    temporary folder and read by GDAL's AIG driver (_read), in the sheet's CRS (the GRID names none). Each file
    reaches 100-400 m beyond its sheet's cell, and its last pixels there are the TIN's edge (up to 73 m off the
    neighbour's interior at G14C15B1/B2, 2026-11-15), so only the pixels whose centres lie within margin_m of the
    cell (in degrees, its edges projected densely) are kept: the neighbours' sheets meet without either's edge.
    Written through _write_tile with the sheet's edition and name as tags."""
    rewrites = True

    def __init__(self, description: str, max_bytes: int = 50_000_000, margin_m: float = 10.0):
        self.description, self.max_bytes, self.margin_m = description, max_bytes, margin_m

    def url(self, tile: InegiSheet) -> Optional[str]:
        return tile.url

    def _download(self, url: str, out: str) -> Optional[requests.Response]:
        """One attempt: the ZIP streamed into out; None for a 404."""
        net.rate_turn(url)
        with servicecounts.request(url) as counted, \
                net.session().get(url, timeout=300, headers=cache.http_headers(), verify=net.verify(url),
                                  stream=True) as response:
            counted.got(response, read=False)
            kind = response.headers.get("content-type", "")
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                text = " ".join(response.raw.read(300, decode_content=True).decode("utf-8", "replace").split())
                raise RuntimeError(f"HTTP {response.status_code}: {text[:200]}")
            if "zip" not in kind and "octet" not in kind:
                counted.outcome = "other"
                raise RuntimeError(f"{kind or 'no content type'}, a ZIP expected")
            size = 0
            with open(out, "wb") as f:
                for chunk in response.iter_content(1 << 20):
                    counted.add(len(chunk))
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise RuntimeError(f"more than {self.max_bytes} bytes")
                    f.write(chunk)
            return response

    def fetch(self, tile: InegiSheet, path: str) -> Fetched:
        where = f"{self.description} sheet {tile.name}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = _part(path + ".zip")
        try:
            last = None
            for attempt in range(net.RETRIES):
                try:
                    response = self._download(tile.url, raw)
                    break
                except (requests.RequestException, RuntimeError) as e:
                    last = e
                    net._sleep(attempt)
            else:
                raise RuntimeError(f"Could not download {where}: {cache.clean_error(last)}")
            if response is None:
                return Fetched(0, tile.url)
            band, transform = self._read(raw, tile, where)
            _write_tile(path, band, tile.crs, transform, tags={"INEGI_SHEET": tile.name,
                                                                "INEGI_EDITION": str(tile.edition)})
            return Fetched(os.path.getsize(raw), tile.url, response.headers.get("ETag"),
                           response.headers.get("Last-Modified"))
        finally:
            if os.path.exists(raw):
                os.remove(raw)

    def _read(self, raw: str, tile: InegiSheet, where: str) -> Tuple[np.ndarray, object]:
        """The GRID of the ZIP raw, cut to the sheet's cell (plus margin_m) and to the rows and columns it keeps. The
        GRID's own files (the folder of its hdr.adf) are unpacked by Python's zipfile into a temporary folder next to
        the tile and read from there: INEGI's member names use backslashes, which zipfile turns into folders on
        Windows only (GDAL's /vsizip/ would need the same on Linux, the worker's)."""
        folder = raw + ".d"
        try:
            try:
                archive = zipfile.ZipFile(raw)
            except zipfile.BadZipFile as e:
                raise RuntimeError(f"{where}: not a ZIP file ({e})") from None
            with archive:
                infos = [(i, i.filename.replace("\\", "/")) for i in archive.infolist() if not i.is_dir()]
                headers = [n for _, n in infos if n.lower().endswith("/hdr.adf") or n.lower() == "hdr.adf"]
                if len(headers) != 1:
                    raise RuntimeError(f"{where}: {len(headers)} ArcInfo GRIDs in the ZIP ({[n for _, n in infos][:6]})")
                grid = headers[0][:-len("hdr.adf")]
                for info, name in infos:
                    if not name.startswith(grid) or "/" in name[len(grid):]:
                        continue  # only the GRID's own files (its info/ folder holds no pixels)
                    if info.file_size > GRID_MEMBER_BYTES:
                        raise RuntimeError(f"{where}: {name} unpacks to more than {GRID_MEMBER_BYTES} bytes")
                    os.makedirs(folder, exist_ok=True)
                    with archive.open(info) as member, open(os.path.join(folder, name[len(grid):]), "wb") as out:
                        content = member.read(GRID_MEMBER_BYTES + 1)  # the header's size is not trusted
                        if len(content) > GRID_MEMBER_BYTES:
                            raise RuntimeError(f"{where}: {name} unpacks to more than {GRID_MEMBER_BYTES} bytes")
                        out.write(content)
            try:
                with rio.open(folder) as src:
                    if src.count != 1 or not (math.isclose(src.transform.a, 5.0) and math.isclose(src.transform.e, -5.0)):
                        raise RuntimeError(f"{where}: {src.count} band(s) of {src.transform.a} x {-src.transform.e} m, "
                                           "one of 5 m expected")
                    band, transform = float_band(src), src.transform
            except rio.errors.RasterioError as e:
                raise RuntimeError(f"{where}: {e}") from None
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        return self._cut(band, transform, tile)

    def _cut(self, band: np.ndarray, transform, tile: InegiSheet) -> Tuple[np.ndarray, object]:
        from area import project
        from shapely.geometry import box
        west, south, east, north = GeoCellTiling.edges(_CELLS, (tile.i, tile.j))
        cell = project(box(west, south, east, north).segmentize(0.002), "EPSG:4326", tile.crs).buffer(self.margin_m)
        outside = geometry_mask([cell], band.shape, transform)
        band[outside] = np.nan
        rows, cols = np.nonzero(~np.isnan(band))
        if rows.size == 0:  # never a tile without a pixel recorded as "ok" (the product is frozen)
            raise RuntimeError(f"sheet {tile.name}: no pixel of its GRID lies within its cell")
        r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
        return np.ascontiguousarray(band[r0:r1, c0:c1]), transform @ Affine.translation(int(c0), int(r0))


_CELLS = GeoCellTiling("EPSG:4326", "", INEGI_CELL, INEGI_ORIGIN)  # the lattice's edges for InegiGrid._cut


class InegiSheets(ComposedLayer):
    """One model of INEGI's 5 m lidar sheets (mod "T" terrain, "S" surface): InegiIndex finds a grid's sheets (a
    static mask of the cells with a sheet, the viewer's JSON per sheet for its edition and ZIP), InegiGrid
    downloads each whole. A frozen product: its tiles are never checked again; a new edition named by an updated
    answer is a new file (the older one deleted)."""

    def __init__(self, description: str, folder: str, mod: str, index_url: str, url_prefix: str, cells: str,
                 top: str, ttl_days: int = 365, bytes_per_tile: float = 4.2e6):
        self.description, self.folder, self.native_res, self._bytes = description, folder, 5.0, bytes_per_tile
        self.crs = "EPSG:4326"  # of the lattice; each sheet's tile is in its own zone's CRS
        self.index = InegiIndex(folder, mod, index_url, url_prefix, cells, top, ttl_days)
        self.reader = InegiGrid(description)

    def missing(self, grid: Grid, cache_dir: str, update: Optional[str]) -> list:
        self.index.use(cache_dir, update)
        return super().missing(grid, cache_dir, update)

    def estimate(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[int, int, float]:
        self.index.use(cache_dir, update)
        return super().estimate(grid, cache_dir, update)

    def to_download(self, grid: Grid, cache_dir: str, update: Optional[str]) -> Tuple[list, Optional[str]]:
        self.index.use(cache_dir, update)
        return super().to_download(grid, cache_dir, update)

    def files(self, grid: Grid, cache_dir: str) -> List[str]:
        if self.index.cache_dir != cache_dir:
            self.index.use(cache_dir, None)
        return super().files(grid, cache_dir)

    def downloaded(self, grid: Grid, cache_dir: str):
        pruned = self.index.prune(cache_dir, self.tiles(grid))
        if pruned:
            print(f"{self.description}: {pruned} older editions replaced by newer ones (deleted)")

    def source_date(self, tile) -> Optional[str]:
        return str(tile.edition)

    def has_data_near(self, lat: float, lon: float, cache_dir: str) -> Optional[bool]:
        return self.index.has_data_near(lat, lon, cache_dir)
