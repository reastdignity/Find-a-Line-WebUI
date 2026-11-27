"""Japan: the sheets of the plane rectangular grid (sources/catalogue/japan.py), the metric tiling of non-square cells
(MetricCellTiling), Tokyo's grid sheets (CellSheetTiles: a static table, the wards' file without an EPSG code),
Shizuoka's LP grids (S3SheetSets: a bucket's listing, sheets composed newest survey first, two levels of sheets) and
the CSV variant of SheetFile's text grids.

Recorded files (tests/data/recorded/tokyo/, 2026-11-15): 09RD8410.zip, the publisher's island sheet off Mikurajima
(EPSG:6677, nodata 1.70141e38, 7 668 pixels of seabed at -12.2 to -6.5 m), and 09LD1649.zip, a ward sheet with its
header as published (a CRS without an EPSG code, AREA_OR_POINT=Point, nodata -32767) and its pixels replaced by
8 x 8 blocks of its heights and a 16 x 16 corner of no data (so the ZIP is small); the index tile of Tokyo's grid
sheets toushobu/12/3636/1637.pbf (the islands' set, Mikurajima)."""

import glob
import hashlib
import io
import math
import os
import sys
import zipfile
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.catalogue import japan  # noqa: E402
from sources.indexes.sheetsets import SheetSets  # noqa: E402
from sources.indexes.tilings import MetricCellTiling  # noqa: E402
from sources.readers.sheetfile import _xyz_points  # noqa: E402
from sources.readers.sheetsets import gave_pixels  # noqa: E402

RECORDED = os.path.join(HERE, "data", "recorded", "tokyo")
NS = "http://s3.amazonaws.com/doc/2006-03-01/"


# --- the sheet codes -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("code, box", [
    ("08OF0485", (58000, -122700, 58400, -122400)),     # Jogasaki (Shizuoka, FY2019)
    ("09KC6361", (-67600, -20100, -67200, -19800)),     # Okutama (Tokyo's Tama, the file's own bounds)
    ("09LD1649", (-12400, -34500, -12000, -34200)),     # Shinjuku (a ward's file, its bounds as GDAL reads them)
    ("09RD8410", (-24000, -234600, -23600, -234300)),   # off Mikurajima (the file's bounds)
    ("09XD0842", (-7200, -391500, -6800, -391200)),     # Aogashima: a row past T
    ("09UD5789", (-8400, -317700, -8000, -317400)),     # Hachijojima
])
def test_sheet_codes(code, box):
    """The 1/500 sheets of real files: code -> cell -> the file's box, and back."""
    zone = int(code[:2])
    i, j = japan.jp_cell(zone, code)
    assert (i * 400, j * 300, (i + 1) * 400, (j + 1) * 300) == box
    assert japan.jp_sheet(zone, i, j) == code
    assert japan.jp_cell(9 if zone == 8 else 8, code) is None  # another zone's code


def test_quadrant_sheet_codes():
    """FY2022's 1000 x 750 m sheets: north-west corners of 08LD3341 (-26 000, -40 500) and 08LD3343
    (-26 000, -41 250) (the members' first points are 0.25 m inside); the same eight characters are a 1/500 sheet
    elsewhere, so only the level tells them apart."""
    for code, corner in (("08LD3341", (-26000, -40500)), ("08LD3343", (-26000, -41250))):
        i, j = japan.jp_quad_cell(8, code)
        assert (i * 1000, (j + 1) * 750) == corner and japan.jp_quad_sheet(8, i, j) == code
        small = japan.jp_cell(8, code)
        assert small is not None and (small[0] * 400, (small[1] + 1) * 300) != corner
    assert japan.jp_quad_cell(8, "08LD3355") is None  # quadrant digits are 1-4
    # every quadrant cell of a 1/5000 sheet has its own code, and they tile it
    codes = {japan.jp_quad_sheet(8, i, j) for i in range(-28, -24) for j in range(-56, -52)}
    assert len(codes) == 16 and all(c.startswith("08LD33") for c in codes)


def test_sheet_names_outside_the_scheme():
    """Outside columns A-H and rows A-Z there is no sheet."""
    assert japan.jp_sheet(9, -401, 0) is None and japan.jp_sheet(9, 400, 0) is None   # x < -160 km, x >= 160 km
    assert japan.jp_sheet(9, 0, 1000) is None and japan.jp_sheet(9, 0, -2601) is None  # above +300 km, below Z
    assert japan.jp_cell(9, "09KI0000") is None and japan.jp_cell(9, "09KC636") is None


# --- the tiling --------------------------------------------------------------------------------------------------
def test_metric_cell_tiling():
    """Cells of 400 x 300 m: the cells over a grid, under an outline only within the grid's box; a path and its
    tile back; cells without a name are no tiles."""
    tiling = MetricCellTiling("EPSG:6676", "fake/s", (400, 300), lambda i, j: japan.sheet_name(japan.jp_sheet(8, i, j)),
                              lambda name: japan.jp_cell(8, japan.code_of_name(name)))
    cell = japan.jp_cell(8, "08OF0485")
    left, bottom, right, top = tiling.edges(cell)
    inside = make_grid((left + 10, bottom + 10, right - 10, top - 10), 1.0, "EPSG:6676")
    assert tiling.tiles(inside) == [cell]
    across = make_grid((left - 10, bottom - 10, right + 10, top + 10), 1.0, "EPSG:6676")
    around = [(cell[0] + di, cell[1] + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)]
    assert sorted(tiling.tiles(across)) == sorted(around)
    from shapely.geometry import box
    across.area_shape = box(left + 1, bottom + 1, right - 1, top + 50)   # reaches into the row above
    assert sorted(tiling.tiles(across)) == [cell, (cell[0], cell[1] + 1)]
    outside = make_grid((left - 10, bottom - 10, right + 10, top + 10), 1.0, "EPSG:6676")
    outside.area_shape = box(left + 5000, bottom + 5000, left + 6000, bottom + 6000)  # far beyond the grid's box
    assert tiling.tiles(outside) == []
    path = tiling.path("C:/c", cell).replace(os.sep, "/")
    assert path == "C:/c/fake/s/OF/04/08OF0485.tif"
    assert tiling.tile_of("fake/s/OF/04/08OF0485.tif") == cell
    assert tiling.tile_of("fake/s/OF/05/08OF0485.tif") is None and tiling.tile_of("fake/s/08OF0485.tif") is None
    west, south, east, north = tiling.bounds_wgs84(cell)
    assert 139.13 < west < east < 139.14 and 34.89 < south < north < 34.90
    far = make_grid((-200_000, 0, -199_000, 1000), 1.0, "EPSG:6676")  # west of column A: no names, no tiles
    assert tiling.tiles(far) == []


def test_metric_cell_tiling_far_edges_exclusive():
    """A grid ending exactly on a sheet's right or top edge takes no sheet beyond it (a download that gives no pixel);
    one reaching a metre over takes it. Both levels of the plane rectangular grid (Tokyo's and Shizuoka's sheets)."""
    for tiling, code in ((japan.TK_DTM.index, "09KC6361"), (japan.SZ_LEVELS["s"], "08OF0485"),
                         (japan.SZ_LEVELS["q"], "08LD3341")):
        zone = int(code[:2])
        cell = (japan.jp_quad_cell if tiling.cell == japan.SHEET_QUAD else japan.jp_cell)(zone, code)
        left, bottom, right, top = tiling.edges(cell)
        crs = tiling.crs
        assert tiling.cells(make_grid((left + 10, bottom + 10, right, top), 1.0, crs)) == [cell]
        assert tiling.cells(make_grid((left, bottom, right, top), 1.0, crs)) == [cell]
        assert tiling.cells(make_grid((left + 10, bottom + 10, right + 1, top), 1.0, crs)) == [cell, (cell[0] + 1,
                                                                                                         cell[1])]
        assert tiling.cells(make_grid((left + 10, bottom + 10, right, top + 1), 1.0, crs)) == [cell, (cell[0],
                                                                                                         cell[1] + 1)]


# --- Tokyo ----------------------------------------------------------------------------------------------------------
@pytest.fixture
def tokyo(http_server, monkeypatch):
    """The catalogue's Tokyo layer on the local server, with a table of three sheets."""
    for name in ("09RD8410.zip", "09LD1649.zip"):
        with open(os.path.join(RECORDED, name), "rb") as f:
            folder = 2024 if name.startswith("09LD") else 2023
            http_server.add(f"/{folder}/dig/grd50/{name}", f.read(), "application/x-zip-compressed")
    http_server.add("/2023/dig/grd50/09RD8411.zip", b"<Error><Code>AccessDenied</Code></Error>", "application/xml",
                    status=403)
    monkeypatch.setattr(japan, "TK_BUCKET", http_server.base)
    monkeypatch.setattr(japan, "_tk_table", lambda: {"09RD8410": (2023,), "09LD1649": (2024,), "09RD8411": (2023,),
                                                     "09RD8319": (2023,)})
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return japan.TK_DTM


@pytest.mark.parametrize("code, nodata", [("09RD8410", 1.70141e38), ("09LD1649", -32767)])
def test_tokyo_sheets_land_on_their_boxes(tokyo, tmp_path, code, nodata):
    """Both kinds of the publisher's sheets are written in EPSG:6677 on the sheet's own box (the wards' file names
    no EPSG code and is point-registered), their no data (1.70141e38, -32767) as NaN, the seabed of an island's
    coast kept as it is."""
    cell = japan.jp_cell(9, code)
    path = tokyo.tile_path(str(tmp_path), cell)
    assert path.replace(os.sep, "/").endswith(f"tokyo/grd50/2022-2023/{code[2:4]}/{code[4:6]}/{code}.tif")
    assert tokyo.tile_of(f"tokyo/grd50/2022-2023/{code[2:4]}/{code[4:6]}/{code}.tif") == cell
    os.makedirs(os.path.dirname(path), exist_ok=True)
    assert tokyo.download_tile(cell, path).received > 0
    left, bottom, right, top = tokyo.index.edges(cell)
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 6677 and tile.shape == (600, 800)
        assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5))
        values = tile.read(1)
    if code == "09RD8410":
        valid = values[~np.isnan(values)]
        assert valid.size == 7668 and -12.2 < valid.min() < valid.max() < -6.4  # seabed, kept
    else:
        assert np.isnan(values[:16, :16]).all() and not np.isnan(values[16:, 16:]).any()
        assert 32 < np.nanmin(values) < np.nanmax(values) < 44


def test_tokyo_table_decides(tokyo, tmp_path, http_server):
    """A sheet outside the table is no tile and never asked; a 403 or a 404 for a sheet in the table is an error
    of that tile, never recorded as missing."""
    cell = japan.jp_cell(9, "09RD8410")
    left, bottom, right, top = tokyo.index.edges(cell)
    grid = make_grid((left - 300, bottom + 10, right + 500, top - 10), 1.0, japan.TK_CRS)
    tiles = tokyo.tiles(grid)
    assert [japan.jp_sheet(9, *t) for t in tiles] == ["09RD8319", "09RD8410", "09RD8411"]  # not 09RD8412: not listed
    cache_dir = str(tmp_path)
    for code in ("09RD8411", "09RD8319"):  # 403 (as S3 answers a key it does not have), 404
        with pytest.raises(RuntimeError, match=code):
            tokyo._download_and_record(japan.jp_cell(9, code), cache_dir)
        assert cache.due(cache_dir, tokyo.tile_path(cache_dir, japan.jp_cell(9, code)))  # nothing recorded
    assert len(http_server.requests("/2023/dig/grd50/09RD8411.zip")) == 1  # a 403 is never asked again
    assert len(http_server.requests("/2023/dig/grd50/09RD8319.zip")) == 1
    assert not any("09RD8412" in r.path for r in http_server.requests())
    assert tokyo.tile_url(japan.jp_cell(9, "09RD8412")) is None


def test_tokyo_table_shipped():
    """The table in the catalogue holds the test places' sheets in their folders, every code a sheet of zone IX."""
    table = japan._tk_table()
    assert table["09KC6361"] == (2023,) and table["09RD8412"] == (2023,) and table["09LD1649"] == (2024,)
    assert table["09KD8388"] == (2024, 2023)  # on the line between Tama and the wards: both, the newer first
    assert all(japan.jp_cell(9, code) is not None for code in table)
    assert len(table) == 18891 and sum(len(f) == 2 for f in table.values()) == 85
    # every sheet lies in Tokyo's offline boxes (the islands' too: Kozushima's and the rocks west of Miyakejima)
    from rasterio.warp import transform
    cells = [japan.jp_cell(9, code) for code in table]
    lons, lats = transform(japan.TK_CRS, "EPSG:4326", [(i + 0.5) * 400 for i, _ in cells],
                           [(j + 0.5) * 300 for _, j in cells])
    boxes = [box for _, box in japan.TK_BOXES]
    assert all(any(s <= lat <= n and w <= lon <= e for s, n, w, e in boxes) for lat, lon in zip(lats, lons))
    assert japan.tk_files(*japan.jp_cell(9, "09LD1649")) == [
        ("2024_09LD1649", f"{japan.TK_BUCKET}/2024/dig/grd50/09LD1649.zip", 2024)]


def test_tokyo_sheets_tool_reads_a_saved_tile(tmp_path):
    """tools/tokyo_sheets.py: the features of a saved index tile (GDAL's MVT driver through pyogrio), checked
    codes and URLs, the table written; a code that is no sheet, or a URL of another folder, stops it."""
    import tokyo_sheets
    tile = os.path.join(RECORDED, "toushobu", "12", "3636", "1637.pbf")
    features = tokyo_sheets.read_tile(tile)
    assert "09RD8412" in {code for code, _ in features}
    found = tokyo_sheets.sheets((2023, code, url) for code, url in features)
    assert found["09RD8412"] == {2023}
    out = str(tmp_path / "t.npz")
    tokyo_sheets.save(out, {**found, "09LD1649": {2023, 2024}})
    with np.load(out) as table:
        saved = dict(zip((c.decode() for c in table["codes"]), table["folders"].tolist()))
    assert saved["09LD1649"] == 2023 and saved["09RD8412"] == 2023  # the last row of a code: its older folder
    assert table_rows(out)[:2] == [("09LD1649", 2024), ("09LD1649", 2023)]
    with pytest.raises(ValueError, match="URL"):
        tokyo_sheets.sheets([(2024, "09RD8412", tokyo_sheets.sheet_url(2023, "09RD8412"))])
    with pytest.raises(ValueError, match="zone IX"):
        tokyo_sheets.sheets([(2023, "08OF0485", tokyo_sheets.sheet_url(2023, "08OF0485"))])
    assert tokyo_sheets.tiles_of((35.8179, 35.8179, 139.0875, 139.0875)) == [(3630, 1610)]


def test_tokyo_sheets_tool_leaves_a_valid_cache(http_server, tmp_path, monkeypatch):
    """tools/tokyo_sheets.py's whole run on a fresh --data-dir: --count writes and asks nothing; a run that fetches a
    tile under the host's slots leaves a cache of the current layout (its lock files without the LAYOUT marker made
    the app refuse that cache before)."""
    import tokyo_sheets
    work, data, out = str(tmp_path / "work"), str(tmp_path / "data"), str(tmp_path / "t.npz")
    tokyo_sheets.main(["--count", "--work", work, "--data-dir", data, "--out", out])
    assert not any(os.path.exists(p) for p in (work, data, out))
    served = (2023, "toushobu", 3636, 1637)
    for folder, name, x, y in tokyo_sheets.asked():  # every other tile answered before (empty: none there)
        if (folder, name, x, y) != served:
            path = os.path.join(work, f"{folder}-{name}", str(tokyo_sheets.ZOOM), str(x), f"{y}.pbf")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").close()
    with open(os.path.join(RECORDED, "toushobu", "12", "3636", "1637.pbf"), "rb") as f:
        http_server.add("/tile.pbf", f.read(), "application/x-protobuf")
    monkeypatch.setattr(tokyo_sheets, "tile_url", lambda *a: http_server.url("/tile.pbf"))
    monkeypatch.setattr(tokyo_sheets, "PAUSE_S", 0)
    tokyo_sheets.main(["--work", work, "--data-dir", data, "--out", out])
    assert len(http_server.requests("/tile.pbf")) == 1
    assert "09RD8412" in {code for code, _ in table_rows(out)}
    data_cache = os.path.join(data, "cache")
    assert os.path.isdir(os.path.join(data_cache, "locks"))
    with open(os.path.join(data_cache, "LAYOUT")) as f:
        assert f.read().strip() == str(cache.LAYOUT)
    cache.check_layout(data_cache)  # no SystemExit


def table_rows(path):
    with np.load(path) as table:
        return [(c.decode(), int(f)) for c, f in zip(table["codes"], table["folders"])]


def test_tokyo_sheet_in_two_folders(tokyo, http_server, tmp_path, monkeypatch):
    """A sheet in both folders, each file partial (smaller than the sheet, on its pixels): the newer folder's file
    first, the older one filling the rest of the sheet's box."""
    code = "09KD8388"
    cell = japan.jp_cell(9, code)
    left, bottom, right, top = tokyo.index.edges(cell)
    from rasterio.io import MemoryFile

    def sheet(folder, rows, value):
        with MemoryFile() as memfile:
            with memfile.open(driver="GTiff", width=800, height=rows, count=1, dtype="float32", crs="EPSG:6677",
                              nodata=-32767, transform=from_origin(left, top - (600 - rows) * 0.5 * (folder == 2023),
                                                                   0.5, 0.5)) as dst:
                dst.write(np.full((rows, 800), value, dtype=np.float32), 1)
            http_server.add(f"/{folder}/dig/grd50/{code}.zip", _zip(f"{code}.tif", memfile.read()))
    sheet(2024, 100, 52.0)   # the northern 100 rows
    sheet(2023, 568, 50.5)   # the southern 568 rows
    monkeypatch.setattr(japan, "_tk_table", lambda: {code: (2024, 2023)})
    path = tokyo.tile_path(str(tmp_path), cell)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    assert tokyo.download_tile(cell, path).received > 0
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5)) and tile.shape == (600, 800)
    assert np.allclose(values[:100], 52.0) and np.allclose(values[100:], 50.5)
    assert [(n, y, p) for n, y, p in gave_pixels(path)] == [(f"2024_{code}", 2024, 80_000),
                                                             (f"2023_{code}", 2023, 400_000)]


# --- Tokyo's island floor (the user's decision of 2026-11-16) ---------------------------------------------------------
def _in_boxes(lats, lons, boxes):
    return [any(s <= lat <= n and w <= lon <= e for s, n, w, e in boxes) for lat, lon in zip(lats, lons)]


def test_tokyo_island_sheets_over_the_whole_table(tmp_path):
    """Every sheet of the table both ways, by the catalogue's own layer on the paths its files() gives: a sheet inside
    an island box of TK_BOXES has the floor -1 m, a sheet inside a mainland box none, and the two sets are the table.
    The constant northing lies in the sea between the mainland's southernmost sheet (y -55 500) and Oshima's
    northernmost (y -132 900); a file that is no sheet is an error, never a file without a floor."""
    from rasterio.warp import transform
    assert japan.TK_BOXES == tuple(("jp-13", b) for b in japan.TK_MAINLAND_BOXES + japan.TK_ISLAND_BOXES)
    table = japan._tk_table()
    cells = {code: japan.jp_cell(9, code) for code in table}
    lons, lats = transform(japan.TK_CRS, "EPSG:4326", [(i + 0.5) * 400 for i, _ in cells.values()],
                           [(j + 0.5) * 300 for _, j in cells.values()])
    mainland = {code for code, inside in zip(cells, _in_boxes(lats, lons, japan.TK_MAINLAND_BOXES)) if inside}
    islands = {code for code, inside in zip(cells, _in_boxes(lats, lons, japan.TK_ISLAND_BOXES)) if inside}
    assert not mainland & islands and mainland | islands == set(table)
    assert len(mainland) == 15637 and len(islands) == 3254
    cache_dir = str(tmp_path)
    floors = {code: japan.TK_DTM.floor_of(japan.TK_DTM.tile_path(cache_dir, cell)) for code, cell in cells.items()}
    assert {code for code, floor in floors.items() if floor == -1.0} == islands
    assert {code for code, floor in floors.items() if floor is None} == mainland
    assert min((j * 300 for code, (_, j) in cells.items() if code in mainland)) == -55_500       # 09LD8148's bottom
    assert max(((j + 1) * 300 for code, (_, j) in cells.items() if code in islands)) == -132_900  # 09OC4931's top
    assert -132_900 < japan.TK_ISLANDS_NORTH < -55_500
    assert japan.TK_DTM.nodata_below is None and japan.TK_ISLAND_FLOOR == -1.0
    with pytest.raises(ValueError, match="no sheet"):
        japan.TK_DTM.floor_of(os.path.join(cache_dir, "tokyo", "grd50", "2022-2023", "RD", "84", "x.tif"))


def _plain_tif(path, values, left, top, res, crs="EPSG:6677"):
    with rio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=np.nan, transform=from_origin(left, top, res, res)) as dst:
        dst.write(values.astype(np.float32), 1)
    return path


class _Floored(src.Layer):
    """Local files with a floor each (floor_of by the file), crediting by pixels: the mosaic's `wrote` kept."""
    description, credits_by_pixels = "floored files", True

    def __init__(self, floors):
        self.floors, self.wrote = floors, None

    def files(self, grid, cache_dir):
        return list(self.floors)

    def tiles(self, grid):
        return []

    def floor_of(self, path):
        return self.floors[path]

    def used_entries(self, grid, cache_dir, wrote=None):
        self.wrote = wrote
        return []


# The files of the per-file floor on a 16 x 12 m grid: the west half (floored at -1 m) and the east half (no floor),
# heights of -3 to 4 m, and a 4 x 4 m file of heights below -1 m only (floored) in the east half's north-east corner,
# under the east file (the file placed first wins): it writes no pixel; alone and without a floor it writes
_RNG = np.random.default_rng(11)
WEST, EAST = (_RNG.uniform(-3, 4, (12, 8)).astype(np.float32) for _ in range(2))
NOISE = _RNG.uniform(-0.2, 0.2, (24, 16)).astype(np.float32)


@pytest.mark.parametrize("rows", [None, 3])
@pytest.mark.parametrize("path", ["copied", "bilinear", "averaged"])
def test_a_floor_per_file_through_prepare_layer(tmp_path, path, rows):
    """prepare_layer gives build_mosaic each file's floor (Layer.floor_of): on every path (on the grid, half a pixel
    off, 0.5 m data averaged), whole and in strips, the mosaic has the bits of the same files floored first and
    mosaicked without a floor; the west file (floor -1 m) has nothing below it on the grid, the east file (none)
    keeps its heights below -1 m. `wrote` still says which files wrote a pixel: a file whose every height lies below
    its floor wrote none."""
    res = 0.5 if path == "averaged" else 1.0
    off = 0.5 if path == "bilinear" else 0.0
    grid = make_grid((-1000.0, -20012.0, -984.0, -20000.0), 1.0, "EPSG:6677")
    twice = np.ones((2, 2), np.float32)
    west, east = (WEST, EAST) if res == 1.0 else (np.kron(WEST, twice) + NOISE, np.kron(EAST, twice))
    deep = np.full((int(4 / res), int(4 / res)), -5.0, np.float32)
    raw = [_plain_tif(str(tmp_path / "w.tif"), west, -1000.0 - off, -20000.0 + off, res),
           _plain_tif(str(tmp_path / "e.tif"), east, -992.0 - off, -20000.0 + off, res),
           _plain_tif(str(tmp_path / "d.tif"), deep, -988.0 - off, -20000.0 + off, res)]
    floors = dict(zip(raw, (-1.0, None, -1.0)))
    first = [_plain_tif(str(tmp_path / f"f{k}.tif"), np.where(v < f, np.nan, v) if f is not None else v,
                        -1000.0 + 8 * (k > 0) + 4 * (k > 1) - off, -20000.0 + off, res)
             for k, (v, f) in enumerate(zip((west, east, deep), floors.values()))]
    layer = _Floored(floors)
    got = np.load(src.prepare_layer(layer, grid, str(tmp_path), str(tmp_path / "m.npy"), "t", download=False,
                                    rows=rows))
    reference = _Floored(dict.fromkeys(first))
    want = np.load(src.prepare_layer(reference, grid, str(tmp_path), str(tmp_path / "r.npy"), "t", download=False,
                                     rows=rows))
    assert np.array_equal(got.view(np.uint32), want.view(np.uint32)), path
    assert layer.wrote == dict(zip(raw, (True, True, False)))
    unfloored = np.load(src.prepare_layer(_Floored(dict.fromkeys(raw)), grid, str(tmp_path), str(tmp_path / "u.npy"),
                                          "t", download=False, rows=rows))
    cut = 7 if path == "bilinear" else 8  # the west file's columns (bilinear: the east file may fill its last)
    assert (unfloored[:, :cut] < -1).any() and not (got[:, :cut] < -1).any()
    assert (got[:, 9:] < -1).any()
    alone = _Floored({raw[2]: -1.0})
    assert np.isnan(np.load(src.prepare_layer(alone, grid, str(tmp_path), str(tmp_path / "a.npy"), "t",
                                              download=False, rows=rows))).all()
    assert alone.wrote == {raw[2]: False}
    kept = _Floored({raw[2]: None})
    np.load(src.prepare_layer(kept, grid, str(tmp_path), str(tmp_path / "k.npy"), "t", download=False, rows=rows))
    assert kept.wrote == {raw[2]: True}


def _sheet_tif(code, values):
    """A sheet of Tokyo's as published (800 x 600 float32 on its box, nodata -32767), zipped."""
    from rasterio.io import MemoryFile
    left, bottom, right, top = japan.TK_DTM.index.edges(japan.jp_cell(9, code))
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=800, height=600, count=1, dtype="float32", crs="EPSG:6677",
                          nodata=-32767, transform=from_origin(left, top, 0.5, 0.5)) as dst:
            dst.write(values.astype(np.float32), 1)
        return _zip(f"{code}.tif", memfile.read())


def test_tokyo_floors_the_islands_sheets_only(tokyo, http_server, tmp_path, monkeypatch):
    """The catalogue's layer on the local server: an island sheet's heights below -1 m are no data on the grid, its
    water above the floor and its land kept; a mainland sheet with the same heights keeps them all (the wards' land
    goes down to -4.42 m); the recorded sheet off Mikurajima (seabed only) gives the grid nothing. The cached files
    keep the provider's heights (the floor is applied when read)."""
    values = np.full((600, 800), 30.0, np.float32)
    values[:, :200] = -4.42    # below the floor
    values[:, 200:300] = -0.5  # above it
    island, mainland = "09RD8412", "09LD1648"
    http_server.add(f"/2023/dig/grd50/{island}.zip", _sheet_tif(island, values))
    http_server.add(f"/2024/dig/grd50/{mainland}.zip", _sheet_tif(mainland, values))
    monkeypatch.setattr(japan, "_tk_table", lambda: {island: (2023,), mainland: (2024,), "09RD8410": (2023,)})
    cache_dir = str(tmp_path / "cache")
    out = {}
    for code in (island, mainland, "09RD8410"):
        left, bottom, right, top = tokyo.index.edges(japan.jp_cell(9, code))
        grid = make_grid((left, bottom, right, top), 1.0, japan.TK_CRS)
        out[code] = np.load(src.prepare_layer(tokyo, grid, cache_dir, str(tmp_path / f"{code}.npy"), "terrain"))
        assert tokyo.files(grid, cache_dir) and len(tokyo.tiles(grid)) == 1
    assert np.isnan(out[island][:, :100]).all()
    assert np.allclose(out[island][:, 100:150], -0.5, atol=0.0051)
    assert np.allclose(out[island][:, 150:], 30.0, atol=0.0051)
    assert np.allclose(out[mainland][:, :100], -4.42, atol=0.0051)
    assert np.allclose(out[mainland][:, 100:150], -0.5, atol=0.0051)
    assert np.allclose(out[mainland][:, 150:], 30.0, atol=0.0051)
    assert np.isnan(out["09RD8410"]).all()
    for code in (island, "09RD8410"):  # cached as they came
        with rio.open(tokyo.tile_path(cache_dir, japan.jp_cell(9, code))) as cached:
            assert float(np.nanmin(cached.read(1))) < -4


# --- the CSV variant of the text grids -----------------------------------------------------------------------------
def test_csv_points():
    """ "n,x,y,z,flag" lines: columns 2-4, every row kept whatever its flag (0, 1, -9999); "x y z" lines as before."""
    text = (b"1,-52799.75,-82200.25,1301.80,0\r\n2,-52799.25,-82200.25,1302.00,1\r\n"
            b"3,-52798.75,-82200.25,117.6,-9999\r\n")
    xyz = _xyz_points(text)
    assert xyz.tolist() == [[-52799.75, -82200.25, 1301.8], [-52799.25, -82200.25, 1302.0],
                            [-52798.75, -82200.25, 117.6]]
    assert _xyz_points(b"58000.250 -122400.250 12.239\r\n58000.750 -122400.250 11.454\r\n").tolist() == \
        [[58000.25, -122400.25, 12.239], [58000.75, -122400.25, 11.454]]
    with pytest.raises(RuntimeError, match="n,x,y,z,flag"):
        _xyz_points(b"1,2,3,4,5\n1,2,3\n")


# --- Shizuoka -------------------------------------------------------------------------------------------------------
def _sheet_text(code: str, z: float, rows=None, csv: bool = False, level: str = "s") -> bytes:
    """A sheet's points as the publisher writes them (x fastest, rows north to south, .25/.75), only the rows given
    (row numbers from the north; None: all)."""
    cell = (japan.jp_quad_cell if level == "q" else japan.jp_cell)(8, code)
    w, h = japan.SHEET_QUAD if level == "q" else japan.SHEET_500
    left, top = cell[0] * w, (cell[1] + 1) * h
    rows = range(int(h * 2)) if rows is None else rows
    ys = top - 0.25 - 0.5 * np.array(list(rows))
    xs = left + 0.25 + 0.5 * np.arange(int(w * 2))
    xx, yy = np.meshgrid(xs, ys)
    zz = np.full(xx.shape, z)
    if csv:
        n = np.arange(1, xx.size + 1)
        flags = np.where(n % 7 == 0, -9999, n % 2)
        rows_of = zip(n, xx.ravel(), yy.ravel(), zz.ravel(), flags)
        lines = [f"{k},{x:.2f},{y:.2f},{v:.2f},{f}" for k, x, y, v, f in rows_of]
    else:
        lines = [f"{x:.3f} {y:.3f} {v:.3f}" for x, y, v in zip(xx.ravel(), yy.ravel(), zz.ravel())]
    return ("\r\n".join(lines) + "\r\n").encode()


def _zip(member: str, text: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, text)
    return buffer.getvalue()


def _etag(data: bytes) -> str:
    """A fake object's ETag: the MD5 of its bytes, as S3 gives a single-part upload's (fixed across processes, unlike
    hash(): a file's cached name ends in its ETag)."""
    return hashlib.md5(data).hexdigest()


def _bucket(http_server, objects, modified=None):
    """A bucket answering ListObjectsV2 (prefix, delimiter) and GET of its keys (LastModified from modified, by
    key)."""
    modified = {} if modified is None else modified
    def answer(request):
        query = dict(request.query)
        if request.path == "/" and query.get("list-type") == "2":
            prefix = query.get("prefix", "")
            keys = sorted(k for k in objects if k.startswith(prefix))
            body = f"<ListBucketResult xmlns='{NS}'><IsTruncated>false</IsTruncated>"
            if query.get("delimiter") == "/":
                rest = [k[len(prefix):] for k in keys]
                folders = sorted({prefix + r.split("/", 1)[0] + "/" for r in rest if "/" in r})
                body += "".join(f"<CommonPrefixes><Prefix>{escape(p)}</Prefix></CommonPrefixes>" for p in folders)
            else:
                body += "".join(f"<Contents><Key>{escape(k)}</Key><LastModified>"
                                f"{modified.get(k, '2026-11-04T07:00:00.000Z')}</LastModified><ETag>&quot;{_etag(objects[k])}&quot;</ETag>"
                                f"<Size>{len(objects[k])}</Size></Contents>" for k in keys)
            return Answer(200, (body + "</ListBucketResult>").encode(), {"Content-Type": "application/xml"})
        key = request.path.lstrip("/")
        if key in objects:
            return Answer(200, objects[key], {"Content-Type": "application/x-zip-compressed"})
        return Answer(404, b"<Error><Code>NoSuchKey</Code></Error>", {"Content-Type": "application/xml"})
    http_server.route("/", answer)


@pytest.fixture
def shizuoka(http_server, monkeypatch):
    """The catalogue's Shizuoka layer on the local server."""
    layer = japan.SZ_DTM
    monkeypatch.setattr(layer, "bucket", http_server.base)
    monkeypatch.setattr(layer.index.listing, "url", http_server.base)
    layer.index._listed.clear()  # the catalogue's object: no answers of another test's server
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return layer


def test_shizuoka_composes_newest_first(shizuoka, http_server, tmp_path):
    """08OF0485: FY2020 (the northern half) over FY2019 (whole); 08OF0486: FY2021's plain file (a few rows) and its
    fuller `_2` (whole, CSV) first, so FY2019 is never downloaded there; the bytes estimated are each sheet's newest
    survey's; the run's entries name the files that gave pixels."""
    objects = {
        "2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0)),
        "2020/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 20.0, range(300))),
        "2019/LP/Grid/08/OF/04/08OF0486.zip": _zip("08OF0486_DEM.txt", _sheet_text("08OF0486", 5.0)),
        "2021/LP/Grid/08/OF/04/08OF0486.zip": _zip("08OF0486_DEM.txt", _sheet_text("08OF0486", 30.0, range(10))),
        "2021/LP/Grid/08/OF/04/08OF0486_2.zip": _zip("08of0486_dem.txt", _sheet_text("08OF0486", 31.0, csv=True)),
        "2019/ALB/Grid/08/OF/04/08OF0485.zip": b"seabed",           # never listed: another prefix
        "2019/LP/Grid/08/OF/04/readme.txt": b"not a sheet",
    }
    _bucket(http_server, objects)
    a, b = japan.jp_cell(8, "08OF0485"), japan.jp_cell(8, "08OF0486")
    grid = make_grid((a[0] * 400 + 50, a[1] * 300 + 50, b[0] * 400 + 350, b[1] * 300 + 250), 0.5, japan.SZ_CRS)
    cache_dir = str(tmp_path)
    tiles, todo, mb = shizuoka.estimate(grid, cache_dir, None)
    newest = len(objects["2020/LP/Grid/08/OF/04/08OF0485.zip"]) + len(objects["2021/LP/Grid/08/OF/04/08OF0486.zip"]) \
        + len(objects["2021/LP/Grid/08/OF/04/08OF0486_2.zip"])
    assert (tiles, todo) == (2, 2) and mb == pytest.approx(newest / 1e6)
    shizuoka.download(grid, cache_dir, None, "terrain")
    files = shizuoka.files(grid, cache_dir)
    assert len(files) == 2
    by_code = {os.path.basename(p).split("_")[1]: p for p in files}
    with rio.open(by_code["08OF0485"]) as tile:
        values = tile.read(1)
        assert tile.crs.to_epsg() == 6676
        assert tile.transform.almost_equals(from_origin(a[0] * 400, (a[1] + 1) * 300, 0.5, 0.5))
    assert np.allclose(values[:300], 20.0) and np.allclose(values[300:], 10.0, atol=0.006)
    assert [(n.split("@")[0], y, p) for n, y, p in gave_pixels(by_code["08OF0485"])] == \
        [("2020_08OF0485", 2020, 240_000), ("2019_08OF0485", 2019, 240_000)]
    with rio.open(by_code["08OF0486"]) as tile:
        values = tile.read(1)
    assert np.allclose(values, 31.0, atol=0.006)  # the fuller `_2` first: the plain file's rows gave nothing
    assert [n.split("@")[0] for n, _, _ in gave_pixels(by_code["08OF0486"])] == ["2021_08OF0486_2"]
    asked = {r.path for r in http_server.requests() if r.path.endswith(".zip")}
    assert "/2019/LP/Grid/08/OF/04/08OF0486.zip" not in asked  # no hole left after FY2021
    assert os.path.basename(by_code["08OF0485"]).startswith("2020_")  # the year first (IndexedTiles.used)
    used = shizuoka.used_entries(grid, cache_dir)
    assert len(used) == 1 and used[0]["credit"]["data"] == japan.SZ_CREDIT.data
    assert used[0]["survey_years"] == [2019, 2021]
    # a sheet uploaded again in place (another ETag) gets another key: read again, the old file deleted
    objects["2019/LP/Grid/08/OF/04/08OF0485.zip"] = _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 11.0))
    shizuoka.index._listed.clear()
    lat, lon = osm_tile_of(shizuoka, a)
    new, _, deleted = shizuoka.update_index_tile(cache_dir, lat, lon)
    assert (new, deleted) == (1, 1)
    with rio.open(next(p for p in shizuoka.files(grid, cache_dir) if "08OF0485" in p)) as tile:
        assert np.allclose(tile.read(1)[300:], 11.0, atol=0.006)


def osm_tile_of(layer, cell):
    """The 0.25° index tile (south-west corner) holding a sheet's centre."""
    import math
    from rasterio.warp import transform
    left, bottom, right, top = layer.levels["s"].edges(cell)
    lons, lats = transform(japan.SZ_CRS, "EPSG:4326", [(left + right) / 2], [(bottom + top) / 2])
    return math.floor(lats[0] / 0.25) * 0.25, math.floor(lons[0] / 0.25) * 0.25


def test_shizuoka_listed_file_missing_is_an_error(shizuoka, http_server, tmp_path):
    """A listed key the bucket no longer gives (404) is an error of its sheet, not a sheet without data."""
    objects = {"2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0))}
    _bucket(http_server, objects)
    a = japan.jp_cell(8, "08OF0485")
    grid = make_grid((a[0] * 400 + 50, a[1] * 300 + 50, a[0] * 400 + 350, a[1] * 300 + 250), 0.5, japan.SZ_CRS)
    cache_dir = str(tmp_path)
    shizuoka._use(cache_dir)
    (sheet,) = shizuoka.tiles(grid)
    del objects["2019/LP/Grid/08/OF/04/08OF0485.zip"]
    with pytest.raises(RuntimeError, match="404"):
        shizuoka._download_and_record(sheet, cache_dir)
    assert cache.due(cache_dir, shizuoka.tile_path(cache_dir, sheet))


def test_shizuoka_two_levels(shizuoka, http_server, tmp_path):
    """A 400 x 300 m sheet of FY2021 and FY2025 under a FY2022 quadrant sheet is split in two, so the order is
    2025, 2022, 2021 and FY2021 never wins over FY2022; the run credits FY2022's approval when its sheet gave
    pixels."""
    quad = japan.jp_quad_cell(8, "08LD3341")
    left, bottom, right, top = japan.SZ_LEVELS["q"].edges(quad)
    small = japan.SZ_LEVELS["s"].cell_of(left + 450, top - 150)  # a 1/500 sheet inside the quadrant sheet
    code = japan.jp_sheet(8, *small)
    letters = f"{code[2:4]}/{code[4:6]}"
    objects = {
        "2022/LP/Grid/08/LD/33/08LD3341.zip": _zip("08LD3341.txt",
                                                    _sheet_text("08LD3341", 2022.0, range(20), level="q")),
        f"2021/LP/Grid/08/{letters}/{code}.zip": _zip(f"{code}_DEM.txt", _sheet_text(code, 2021.0)),
        f"2025/LP/Grid/08/{letters}/{code}.zip": _zip(f"{code}_0.5g.txt",
                                                       _sheet_text(code, 2025.0, range(100, 120), csv=True)),
    }
    _bucket(http_server, objects)
    sl, sb, sr, st = japan.SZ_LEVELS["s"].edges(small)
    grid = make_grid((sl + 10, sb + 10, sr - 10, st - 10), 0.5, japan.SZ_CRS)
    cache_dir = str(tmp_path)
    shizuoka._use(cache_dir)
    sheets = shizuoka.tiles(grid)
    assert [(s.level, s.year, [f[2] for f in s.files]) for s in sheets] == \
        [("s", 2025, [2025]), ("q", 2022, [2022]), ("s", 2021, [2021])]
    shizuoka.download(grid, cache_dir, None, "terrain")
    files = shizuoka.files(grid, cache_dir)
    assert [os.path.basename(p).split("_")[0] for p in files] == ["2025", "2022", "2021"]
    assert files[1].replace(os.sep, "/").endswith(f"shizuoka/lp-grid/q/LD/33/2022_08LD3341_{sheets[1].key}.tif")
    entries = shizuoka.used_entries(grid, cache_dir)
    assert [e["layer"] for e in entries] == [shizuoka.description, f"{shizuoka.description}, FY2022 Southern Alps"]
    assert "5関治第142号-1" in entries[1]["credit"]["attribution"]
    assert entries[0]["survey_years"] == [2021, 2025]
    for entry in entries:  # each entry's own files' stored checksums, parallel to its paths (the run's record)
        stored = [cache.info(cache_dir, os.path.join(cache_dir, p))["sha256"] for p in entry["paths"]]
        assert entry["identity"] == {"sha256": stored} and all(len(s) == 64 for s in stored)
    # a sheet of FY2022 that gave no pixel brings no FY2022 credit
    wrote = {p: "/q/" not in p.replace(os.sep, "/") for p in files}
    assert len(shizuoka.used_entries(grid, cache_dir, wrote)) == 1
    # the cached files are found again without the index
    assert [(s.level, s.year) for s in shizuoka.index.versions.cached(grid, cache_dir)] == \
        [("s", 2025), ("q", 2022), ("s", 2021)]


def test_shizuoka_keys_and_prefixes():
    """The keys the layer takes and the prefixes a box asks."""
    assert japan.sz_key("2019/LP/Grid/08/OF/04/08OF0485.zip") == (2019, "s", japan.jp_cell(8, "08OF0485"))
    assert japan.sz_key("2021/LP/Grid/08/ME/90/08ME9065_2.zip") == (2021, "s", japan.jp_cell(8, "08ME9065"))
    assert japan.sz_key("2022/LP/Grid/08/LD/33/08LD3341.zip") == (2022, "q", japan.jp_quad_cell(8, "08LD3341"))
    assert japan.sz_key("2019/ALB/Grid/08/OF/04/08OF0485.zip") is None
    assert japan.sz_key("2019/LP/Grid/08/OF/05/08OF0485.zip") is None  # a folder not of its code
    cell = japan.jp_cell(8, "08OF0485")
    box = (cell[0] * 400 - 30_000, cell[1] * 300, cell[0] * 400 + 100, cell[1] * 300 + 100)
    assert japan.sz_prefixes("2019/", box) == ["2019/LP/Grid/08/OE/", "2019/LP/Grid/08/OF/"]


def test_catalogue_entries():
    """The catalogue's own settings of both sources."""
    tokyo, shizuoka = src.SOURCES["tokyo"], src.SOURCES["shizuoka"]
    assert tokyo.regions == ("jp-13",) and shizuoka.regions == ("jp-22",)
    assert tokyo.crs == "EPSG:6677" and shizuoka.crs == "EPSG:6676" and tokyo.nmpt is None and shizuoka.nmpt is None
    assert tokyo.nmt.reader.sheet.listed and tokyo.nmt.members == r"\.tif$" and tokyo.nmt.native_res == 0.5
    assert japan.SZ_DTM.reader.sheet.listed
    assert japan.SZ_DTM.bucket == "https://virtual-shizuoka.s3.ap-northeast-1.amazonaws.com"
    assert japan.SZ_DTM.index.listing.url == japan.SZ_DTM.bucket and japan.SZ_DTM.members == r"\.txt$"
    assert set(japan.SZ_DTM.levels) == {"s", "q"} and japan.SZ_DTM.level_credits["q"][1] is japan.SZ_2022_CREDIT
    assert japan.SZ_DTM.credit is japan.SZ_CREDIT and japan.SZ_DTM.credits_by_pixels
    assert src.net.HOST_SLOTS_OF["gic-tokyo.s3.ap-northeast-1.amazonaws.com"] == 2
    assert src.net.HOST_SLOTS_OF["virtual-shizuoka.s3.ap-northeast-1.amazonaws.com"] == 2
    # the offline boxes of the two never overlap (the first holding a point would win)
    from shapely.geometry import box
    for _, (s1, n1, w1, e1) in tokyo.offline:
        for _, (s2, n2, w2, e2) in shizuoka.offline:
            assert box(w1, s1, e1, n1).intersection(box(w2, s2, e2, n2)).area == 0


# --- the fix round of 2026-11-16 -----------------------------------------------------------------------------------
def _sheet_grid(code, margin=50.0):
    cell = japan.jp_cell(8, code)
    left, bottom = cell[0] * 400, cell[1] * 300
    return make_grid((left + margin, bottom + margin, left + 400 - margin, bottom + 300 - margin), 0.5, japan.SZ_CRS)


def test_shizuoka_odd_members(shizuoka, http_server, tmp_path):
    """An empty (or whitespace) member is no data and the older survey fills the sheet; a sparse member (every other
    point of two rows 1 m apart) is gridded on the sheet's own 0.5 m pixels; a file whose points all lie off its
    sheet (x and y swapped) is an error naming the sheet, the file and both boxes, and nothing is recorded."""
    a = japan.jp_cell(8, "08OF0485")
    left, top = a[0] * 400, (a[1] + 1) * 300
    sparse = "".join(f"{left + 0.25 + 1.0 * k:.3f} {top - 0.25 - 1.0 * r:.3f} 40.000\r\n" for r in (0, 1) for k in range(0, 3))
    objects = {
        "2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0)),
        "2020/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", b"  \r\n\r\n"),
        "2021/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", sparse.encode()),
    }
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _sheet_grid("08OF0485")
    shizuoka.download(grid, cache_dir, None, "terrain")
    (path,) = shizuoka.files(grid, cache_dir)
    with rio.open(path) as tile:
        values = tile.read(1)
    assert values[0, 0] == pytest.approx(40.0) and values[0, 2] == pytest.approx(40.0)  # 1 m apart: pixels 0, 2
    assert values[2, 4] == pytest.approx(40.0) and values[0, 1] == pytest.approx(10.0, abs=0.006)
    assert [n.split("@")[0] for n, _, _ in gave_pixels(path)] == ["2021_08OF0485", "2019_08OF0485"]
    # x and y swapped: no point on the sheet
    b = japan.jp_cell(8, "08OF0486")
    swapped = "".join(f"{(b[1] + 1) * 300 - 0.25:.3f} {b[0] * 400 + 0.25 + k:.3f} 5.000\r\n" for k in range(3))
    objects["2019/LP/Grid/08/OF/04/08OF0486.zip"] = _zip("08OF0486_DEM.txt", swapped.encode())
    shizuoka.index._listed.clear()
    shizuoka._use(cache_dir)
    for f in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "**", "*.json"), recursive=True):
        os.remove(f)
    grid_b = _sheet_grid("08OF0486")
    shizuoka._use(cache_dir)
    (sheet,) = shizuoka.tiles(grid_b)
    with pytest.raises(RuntimeError, match=r"08OF0486 \(2019_08OF0486@\w+\).*none of its 3 points lies on the sheet"):
        shizuoka._download_and_record(sheet, cache_dir)
    assert cache.due(cache_dir, shizuoka.tile_path(cache_dir, sheet))


@pytest.mark.parametrize("name, key, code, first", [
    ("08MC4919_2025.zip", "2025/LP/Grid/08/MC/49/08MC4919.zip", "08MC4919", (-40000.25, -72441.75, 2414.6)),
    ("08OF0485_2019.zip", "2019/LP/Grid/08/OF/04/08OF0485.zip", "08OF0485", (58000.25, -122400.25, 12.239)),
])
def test_shizuoka_real_lines_land_on_their_sheet(shizuoka, http_server, tmp_path, name, key, code, first):
    """The publisher's own lines (the first 300 of a FY2025 CSV sheet and of a FY2019 "x y z" sheet, recorded
    2026-11-16) through the catalogue's layer: on their sheet of zone VIII, each point in the pixel holding it
    (x the column from the west, y the row from the north)."""
    with open(os.path.join(HERE, "data", "recorded", "shizuoka", name), "rb") as f:
        _bucket(http_server, {key: f.read()})
    cache_dir = str(tmp_path)
    grid = _sheet_grid(code, margin=1.0)
    shizuoka.download(grid, cache_dir, None, "terrain")
    (path,) = shizuoka.files(grid, cache_dir)
    cell = japan.jp_cell(8, code)
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.crs.to_epsg() == 6676 and tile.shape == (600, 800)
        assert tile.transform.almost_equals(from_origin(cell[0] * 400, (cell[1] + 1) * 300, 0.5, 0.5))
    x, y, z = first
    col, row = int((x - cell[0] * 400) // 0.5), int(((cell[1] + 1) * 300 - y) // 0.5)
    assert values[row, col] == pytest.approx(z, abs=0.006)
    assert np.count_nonzero(~np.isnan(values)) == 300


def test_shizuoka_prune_keeps_both_parts_of_a_split_sheet(shizuoka, http_server, tmp_path):
    """After a search over a split sheet (FY2025 and FY2021 parts), prune deletes neither part; a re-uploaded
    FY2021 file replaces only the FY2021 part."""
    quad = japan.jp_quad_cell(8, "08LD3341")
    left, _, _, top = japan.SZ_LEVELS["q"].edges(quad)
    small = japan.SZ_LEVELS["s"].cell_of(left + 450, top - 150)
    code = japan.jp_sheet(8, *small)
    letters = f"{code[2:4]}/{code[4:6]}"
    k21, k25 = f"2021/LP/Grid/08/{letters}/{code}.zip", f"2025/LP/Grid/08/{letters}/{code}.zip"
    objects = {k21: _zip(f"{code}_DEM.txt", _sheet_text(code, 2021.0)),
               k25: _zip(f"{code}_0.5g.txt", _sheet_text(code, 2025.0, range(100, 120), csv=True))}
    _bucket(http_server, objects)
    sl, sb, sr, st = japan.SZ_LEVELS["s"].edges(small)
    grid = make_grid((sl + 10, sb + 10, sr - 10, st - 10), 0.5, japan.SZ_CRS)
    cache_dir = str(tmp_path)
    shizuoka.download(grid, cache_dir, None, "terrain")
    sheets = shizuoka.tiles(grid)
    assert len(sheets) == 2 and shizuoka.index.prune(cache_dir, sheets) == 0
    assert len(shizuoka.files(grid, cache_dir)) == 2
    objects[k21] = _zip(f"{code}_DEM.txt", _sheet_text(code, 2021.5))
    for f in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "**", "*.json"), recursive=True):
        cache.forget(cache_dir, [f])
    shizuoka.index._listed.clear()
    shizuoka.download(grid, cache_dir, None, "terrain")
    now = shizuoka.tiles(grid)  # download_layers pruned (downloaded): the old FY2021 part only
    folder = os.path.dirname(shizuoka.files(grid, cache_dir)[0])
    assert sorted(os.listdir(folder)) == sorted(os.path.basename(shizuoka.tile_path(cache_dir, s)) for s in now)
    assert {s.key for s in now} & {s.key for s in sheets} == {s.key for s in sheets if s.year == 2025}
    names = sorted(os.path.basename(p).split("_")[0] for p in shizuoka.files(grid, cache_dir))
    assert names == ["2021", "2025"]


def test_shizuoka_has_data_near(shizuoka, http_server, tmp_path):
    """has_data_near: a listed sheet within 2 km of the point, none far away."""
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": b"x"})
    from rasterio.warp import transform
    cell = japan.jp_cell(8, "08OF0485")
    lons, lats = transform(japan.SZ_CRS, "EPSG:4326", [cell[0] * 400 + 200, cell[0] * 400 + 6000],
                           [cell[1] * 300 + 150, cell[1] * 300 + 150])
    shizuoka._use(str(tmp_path))
    assert shizuoka.has_data_near(lats[0], lons[0], str(tmp_path)) is True
    assert shizuoka.has_data_near(lats[1], lons[1], str(tmp_path)) is False


def test_common_prefixes_pages(http_server):
    """common_prefixes follows the continuation tokens, and a truncated page without a token is an error."""
    from sources.indexes.cached import IndexUnavailable
    from sources.indexes.s3listing import common_prefixes

    def answer(request):
        query = dict(request.query)
        if query.get("prefix") == "bad/":
            body = f"<ListBucketResult xmlns='{NS}'><IsTruncated>true</IsTruncated></ListBucketResult>"
        elif "continuation-token" not in query:
            body = (f"<ListBucketResult xmlns='{NS}'><IsTruncated>true</IsTruncated><CommonPrefixes><Prefix>2019/"
                    f"</Prefix></CommonPrefixes><NextContinuationToken>t1</NextContinuationToken></ListBucketResult>")
        else:
            body = (f"<ListBucketResult xmlns='{NS}'><IsTruncated>false</IsTruncated><CommonPrefixes><Prefix>2020/"
                    f"</Prefix></CommonPrefixes></ListBucketResult>")
        return Answer(200, body.encode(), {"Content-Type": "application/xml"})
    http_server.route("/", answer)
    assert common_prefixes(http_server.base, "") == ["2019/", "2020/"]
    assert dict(http_server.requests("/")[-1].query)["continuation-token"] == "t1"
    with pytest.raises(IndexUnavailable, match="token"):
        common_prefixes(http_server.base, "bad/")


def test_probe_reads_a_sheet_zip_head(shizuoka, tokyo, http_server, tmp_path, monkeypatch):
    """The probe's sheetset strategy: Shizuoka's index row from the bucket's listing, then the first KB of the
    first sheet's ZIP without a Range header; Tokyo's (a table, no index) the same; a page that is no ZIP fails."""
    from sources import probe
    assert probe.strategy(japan.SZ_DTM) == "sheetset" and probe.strategy(japan.TK_DTM) == "sheetset"
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", b"1 2 3\r\n" * 400)})
    from rasterio.warp import transform
    cell = japan.jp_cell(8, "08OF0485")
    lons, lats = transform(japan.SZ_CRS, "EPSG:4326", [cell[0] * 400 + 200], [cell[1] * 300 + 150])
    source = src.Source(id="fake_shizuoka", name="Fake", description="", nmt=japan.SZ_DTM, crs=japan.SZ_CRS,
                        sample=(lats[0], lons[0]))
    os.makedirs(tmp_path / "probe", exist_ok=True)
    row = probe.probe_layer(source, japan.SZ_DTM, "terrain", str(tmp_path), str(tmp_path / "probe"), False)
    assert (row.index, row.read) == (probe.OK, probe.OK), row.notes
    zips = [r for r in http_server.requests() if r.path.endswith(".zip")]
    assert zips and all("range" not in r.headers for r in zips)
    http_server.add("/s/page.zip", b"<html>no</html>", "text/html")
    with pytest.raises(RuntimeError, match="HTTP 200"):
        probe._zip_url_head(str(tmp_path), http_server.url("/s/page.zip"))


def test_metric_cell_tiling_edges_on_cell_edges():
    """A grid whose edges lie exactly on cell edges takes the cells it covers, plus those its closed edges touch
    (as MetricTiling counts a box: floor of each edge)."""
    tiling = japan.SZ_LEVELS["s"]
    cell = japan.jp_cell(8, "08OF0485")
    left, bottom, right, top = tiling.edges(cell)
    grid = make_grid((left, bottom, right, top), 1.0, japan.SZ_CRS)
    tiles = tiling.tiles(grid)
    assert cell in tiles and all(abs(i - cell[0]) <= 1 and abs(j - cell[1]) <= 1 for i, j in tiles)
    assert (cell[0] - 1, cell[1]) not in tiles and (cell[0], cell[1] - 1) not in tiles


# --- round 3 (2026-11-16): one owner index tile per sheet -----------------------------------------------------------
def _edge_sheets():
    """A 1/500 sheet (S, 08NF1133) whose box reaches across the 0.25 degree line at 139.0 E while its centre lies west
    of it, so before the owner rule it was in both tiles' answers, and a sheet (N) 2 km east, inside the east tile;
    their owners (the tiles of their centres, computed here, not by the code under test)."""
    from rasterio.warp import transform
    tiling = japan.SZ_LEVELS["s"]
    cell = japan.jp_cell(8, "08NF1133")
    left, bottom, right, top = tiling.edges(cell)
    lons, lats = transform(japan.SZ_CRS, "EPSG:4326", [left, left, right, right, (left + right) / 2],
                           [bottom, top, bottom, top, (bottom + top) / 2])
    assert max(lons[:2]) < 139.0 < min(lons[2:4]) and lons[4] < 139.0  # the box across the line, the centre west
    n_cell = tiling.cell_of((left + right) / 2 + 2000, (bottom + top) / 2)

    def owner(c):
        lo, la = transform(japan.SZ_CRS, "EPSG:4326", [(c[0] + 0.5) * 400], [(c[1] + 0.5) * 300])
        return math.floor(la[0] / 0.25) * 0.25, math.floor(lo[0] / 0.25) * 0.25
    owner_s, owner_n = owner(cell), owner(n_cell)
    assert owner_s[1] == 138.75 and owner_n[1] == 139.0
    return cell, n_cell, owner_s, owner_n


def _key_of(cell, year=2019):
    code = japan.jp_sheet(8, *cell)
    return code, f"{year}/LP/Grid/08/{code[2:4]}/{code[4:6]}/{code}.zip"


def _zips(http_server):
    return len([r for r in http_server.requests() if r.path.endswith(".zip")])


def _search(layer, grid, cache_dir):
    layer.index._listed.clear()
    layer.download(grid, cache_dir, None, "terrain")
    layer.downloaded(grid, cache_dir)


def _box_grid(cell, margin=1.0, other=None):
    tiling = japan.SZ_LEVELS["s"]
    left, bottom, right, top = tiling.edges(cell)
    if other is not None:
        o = tiling.edges(other)
        left, bottom, right, top = min(left, o[0]), min(bottom, o[1]), max(right, o[2]), max(top, o[3])
    return make_grid((left + margin, bottom + margin, right - margin, top - margin), 0.5, japan.SZ_CRS)


def test_acceptance_a_edge_sheet_one_key_by_turns(shizuoka, http_server, tmp_path):
    """A (a): a sheet within 250 m of the east tile, uploaded again between the two tiles' listings, searched alone
    and with the east tile's sheet by turns four times: one key throughout (its owner's answer), 2 downloads in all
    (the sheet and its neighbour once each), nothing pruned that a current key names."""
    cell, n_cell, owner_s, owner_n = _edge_sheets()
    code, key = _key_of(cell)
    n_code, n_key = _key_of(n_cell)
    objects = {key: _zip(f"{code}_DEM.txt", _sheet_text(code, 10.0)), n_key: _zip(f"{n_code}_DEM.txt",
                                                                               _sheet_text(n_code, 20.0))}
    modified = {key: "2026-11-04T07:00:00.000Z"}
    _bucket(http_server, objects, modified)
    cache_dir = str(tmp_path)
    alone, both = _box_grid(cell), _box_grid(cell, other=n_cell)
    _search(shizuoka, alone, cache_dir)  # lists the owner (and the east tile)
    first = [os.path.basename(p) for p in shizuoka.files(alone, cache_dir)]
    objects[key] = _zip(f"{code}_DEM.txt", _sheet_text(code, 11.0))  # uploaded again
    modified[key] = "2026-11-10T07:00:00.000Z"
    cache.forget(cache_dir, [shizuoka.index.index_path(cache_dir, *owner_n)])  # the east tile listed after it
    for grid in (both, alone, both, alone):
        _search(shizuoka, grid, cache_dir)
        assert [os.path.basename(p) for p in shizuoka.files(alone, cache_dir)] == first  # one key
    assert _zips(http_server) == 2
    folder = os.path.dirname(shizuoka.files(alone, cache_dir)[0])
    assert [f for f in os.listdir(folder) if code in f] == first


def test_acceptance_b_removed_object_three_rounds(shizuoka, http_server, tmp_path):
    """A (b): an object removed after the listing: the first search fails with the 404's message (the owner's
    answer dropped, a new search lists anew), the second succeeds with the older survey, the third reads nothing."""
    cell, _, owner, _ = _edge_sheets()
    code, k19 = _key_of(cell, 2019)
    _, k20 = _key_of(cell, 2020)
    objects = {k19: _zip(f"{code}_DEM.txt", _sheet_text(code, 10.0)),
               k20: _zip(f"{code}_DEM.txt", _sheet_text(code, 20.0, range(300)))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _box_grid(cell)
    shizuoka._use(cache_dir)
    (sheet,) = shizuoka.tiles(grid)  # listed with both surveys
    neighbour = shizuoka.index.index_path(cache_dir, owner[0], owner[1] + 0.25)  # the east tile's answer
    assert os.path.exists(neighbour)  # the grid reaches into the east tile: listed too
    del objects[k20]
    with pytest.raises(RuntimeError, match=r"404.*answer of its tile .* was dropped: a new search lists it anew"):
        shizuoka._download_and_record(sheet, cache_dir)
    assert not os.path.exists(shizuoka.index.index_path(cache_dir, *owner))
    assert os.path.exists(neighbour)  # only the owner's answer is dropped
    shizuoka.download(grid, cache_dir, None, "terrain")  # no clear of the listings here: the handler's own
    shizuoka.downloaded(grid, cache_dir)
    (path,) = shizuoka.files(grid, cache_dir)
    assert [n.split("@")[0] for n, _, _ in gave_pixels(path)] == [f"2019_{code}"]
    before = _zips(http_server)
    _search(shizuoka, grid, cache_dir)
    assert _zips(http_server) == before


def test_acceptance_c_update_and_search_by_turns(shizuoka, http_server, tmp_path):
    """A (c): after the newest object was removed, update_index_tile on the owner tile and a search by turns: the
    same key both ways, one download in all after the removal, the removed survey's file gone from the cache."""
    cell, _, owner, _ = _edge_sheets()
    code, k19 = _key_of(cell, 2019)
    _, k20 = _key_of(cell, 2020)
    objects = {k19: _zip(f"{code}_DEM.txt", _sheet_text(code, 10.0)),
               k20: _zip(f"{code}_DEM.txt", _sheet_text(code, 20.0, range(300)))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _box_grid(cell)
    _search(shizuoka, grid, cache_dir)
    (old,) = shizuoka.files(grid, cache_dir)
    assert os.path.basename(old).startswith("2020_")
    del objects[k20]
    before = _zips(http_server)
    new, _, deleted = shizuoka.update_index_tile(cache_dir, *owner)
    assert (new, deleted) == (1, 1) and not os.path.exists(old)
    (path,) = shizuoka.files(grid, cache_dir)
    for turn in range(2):
        _search(shizuoka, grid, cache_dir)
        assert shizuoka.files(grid, cache_dir) == [path]
        assert shizuoka.update_index_tile(cache_dir, *owner)[:2] == (0, 0)
    assert _zips(http_server) == before + 1 and os.path.basename(path).startswith("2019_")


def test_acceptance_b_one_owner_per_sheet_asked_by_query():
    """B: every sheet of both levels over Shizuoka's offline boxes has one owner tile, the tile holding its centre,
    and for every sheet whose box reaches across a tile line (the only ones another tile could hold) the owner is
    among the tiles query asks for a grid of that sheet alone (computed, no request)."""
    from rasterio.warp import transform
    versions = japan.SZ_DTM.index.versions
    checked = crossing = 0
    for level, tiling in japan.SZ_LEVELS.items():
        cells = set()
        for _, (s, n, w, e) in japan.SZ_BOXES:
            xs, ys = transform("EPSG:4326", japan.SZ_CRS, [w, e, w, e], [s, s, n, n])
            (i0, j0), (i1, j1) = tiling.cell_of(min(xs), min(ys)), tiling.cell_of(max(xs), max(ys))
            cells.update((i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1))
        cells = sorted(c for c in cells if tiling.name(*c) is not None)
        owners = versions.owners(level, cells)
        boxes = np.array([tiling.edges(c) for c in cells])
        lons, lats = transform(japan.SZ_CRS, "EPSG:4326", list((boxes[:, 0] + boxes[:, 2]) / 2),
                               list((boxes[:, 1] + boxes[:, 3]) / 2))
        assert owners == [(math.floor(a / 0.25) * 0.25, math.floor(o / 0.25) * 0.25) for a, o in zip(lats, lons)]
        wl, sl = transform(japan.SZ_CRS, "EPSG:4326", list(boxes[:, 0]), list(boxes[:, 1]))
        el, nl = transform(japan.SZ_CRS, "EPSG:4326", list(boxes[:, 2]), list(boxes[:, 3]))
        for cell, owner, w, s, e, n in zip(cells, owners, wl, sl, el, nl):
            checked += 1
            if math.floor(w / 0.25) == math.floor(e / 0.25) and math.floor(s / 0.25) == math.floor(n / 0.25):
                continue
            crossing += 1
            left, bottom, right, top = tiling.edges(cell)
            grid = make_grid((left + 0.5, bottom + 0.5, right - 0.5, top - 0.5), 0.5, japan.SZ_CRS)
            assert owner in versions.tiles_to_ask(grid), (level, cell)
    assert checked > 100_000 and crossing > 1000


def test_acceptance_c_update_and_status_over_a_listing(shizuoka, http_server, tmp_path, monkeypatch, capsys):
    """C: `cache update --all` (update.checks) and `cache status` (update.status) over a data folder holding a
    Shizuoka listing, fresh and aged past its lifetime: the folder list is no row of the index, every Shizuoka row
    is a tile answer whose check names it."""
    import sqlite3
    import update
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt",
                                                                     _sheet_text("08OF0485", 10.0))})
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir)
    _search(shizuoka, _sheet_grid("08OF0485"), cache_dir)
    assert os.path.exists(shizuoka.folders_path(cache_dir))
    rows = [r["path"] for r in cache.rows(cache_dir, "shizuoka")]
    assert not [r for r in rows if "folders" in r]
    found = update.checks(cache_dir, update="all")
    assert [c.what for c in found if c.path.startswith("shizuoka/sheet-index/")] == \
        ["VIRTUAL SHIZUOKA LP grid 0.5 m (terrain): sheet index"] * len([r for r in rows if "sheet-index" in r])
    db = sqlite3.connect(os.path.join(cache_dir, "shizuoka", "index.sqlite"))
    db.execute("UPDATE files SET checked_at = '2020-01-01T00:00:00+00:00'")
    db.commit()
    db.close()
    assert update.checks(cache_dir, update="stale")
    update.status(cache_dir, str(tmp_path / "runs"))
    assert "shizuoka" in capsys.readouterr().out


def test_survey_folders_lifetime_and_failure(shizuoka, http_server, tmp_path, monkeypatch, capsys):
    """The folder list: one delimiter listing kept FOLDERS_TTL_DAYS beside the index's folder; asked again when
    stale; a failed re-listing keeps the last list (said); with no list at all the index is not available and a
    search uses the cached sheets (said)."""
    from sources.layers import s3sheets
    objects = {"2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    shizuoka._use(cache_dir)

    def delimited():
        return len([r for r in http_server.requests("/") if dict(r.query).get("delimiter") == "/"])
    assert shizuoka.survey_folders() == ["2019/"] and delimited() == 1
    objects["2026/LP/Grid/08/OF/04/08OF0485.zip"] = b"y"
    assert shizuoka.survey_folders() == ["2019/"] and delimited() == 1
    monkeypatch.setattr(s3sheets, "FOLDERS_TTL_DAYS", -1)
    assert shizuoka.survey_folders() == ["2019/", "2026/"] and delimited() == 2
    monkeypatch.setattr(s3sheets, "common_prefixes", lambda *a: (_ for _ in ()).throw(
        src.indexes.cached.IndexUnavailable("down")))
    assert shizuoka.survey_folders() == ["2019/", "2026/"]
    assert "could not be listed again" in capsys.readouterr().out
    # no list at all and the bucket down: a search uses the cached sheets
    os.remove(shizuoka.folders_path(cache_dir))
    shizuoka.index._listed.clear()
    grid = _sheet_grid("08OF0485")
    for f in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "lp-grid", "*.json")):
        cache.forget(cache_dir, [f])
    assert shizuoka.tiles(grid) is None
    assert "index not available" in capsys.readouterr().out


def test_folder_lock_is_no_tile_lock(shizuoka, http_server, tmp_path, monkeypatch):
    """With one tile lock for every path (TILE_LOCKS 1) a tile's listing, which asks the folder list under the
    tile's lock, still ends: the folder list takes a lock of its own."""
    monkeypatch.setattr(src.net, "TILE_LOCKS", 1)
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": b"x"})
    shizuoka._use(str(tmp_path))
    assert len(shizuoka.tiles(_sheet_grid("08OF0485"))) == 1


def test_points_on_pixel_edges_are_an_error(shizuoka, http_server, tmp_path):
    """Text points off the sheet's pixel centres (on whole metres: the edges) are an error naming the source, the
    sheet, the file and the member, never binned half a pixel off."""
    cell = japan.jp_cell(8, "08OF0485")
    left, top = cell[0] * 400, (cell[1] + 1) * 300
    text = "".join(f"{left + k:.3f} {top - 1:.3f} 5.000\r\n" for k in range(1, 4))
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": _zip("08OF0485_DEM.txt", text.encode())})
    cache_dir = str(tmp_path)
    shizuoka._use(cache_dir)
    (sheet,) = shizuoka.tiles(_sheet_grid("08OF0485"))
    with pytest.raises(RuntimeError, match=r"VIRTUAL SHIZUOKA.*08OF0485 \(2019_08OF0485@\w+\) 08OF0485_DEM.txt: 3 "
                                           r"of its 3 points are not on the sheet's 0.5 m pixel centres"):
        shizuoka._download_and_record(sheet, cache_dir)


def test_tokyo_raster_off_its_sheet_is_an_error(tokyo, http_server, tmp_path, monkeypatch):
    """A GeoTIFF whose data lie off its sheet (another sheet's box) is an error of the tile, nothing recorded."""
    with open(os.path.join(RECORDED, "09RD8410.zip"), "rb") as f:
        http_server.add("/2023/dig/grd50/09RD8412.zip", f.read(), "application/x-zip-compressed")
    monkeypatch.setattr(japan, "_tk_table", lambda: {"09RD8412": (2023,)})
    cell = japan.jp_cell(9, "09RD8412")
    with pytest.raises(RuntimeError, match=r"09RD8412 \(2023_09RD8412\): its data lie off the sheet"):
        tokyo._download_and_record(cell, str(tmp_path))
    assert cache.due(str(tmp_path), tokyo.tile_path(str(tmp_path), cell))


@pytest.mark.parametrize("name, code", [("08MC4919_2025.zip", "08MC4919"), ("08OF0485_2019.zip", "08OF0485")])
def test_old_and_new_paths_equal_on_the_real_heads(name, code):
    """The sheet-set reader's gridding equals the old path's (SheetFile._parts as Saxony's, then pasted) on the
    publisher's own 300 lines of each format."""
    from types import SimpleNamespace
    from sources.readers.sheetsets import SheetSetFile, SheetSetRequest, paste
    with open(os.path.join(HERE, "data", "recorded", "shizuoka", name), "rb") as f:
        data = f.read()
    i, j = japan.jp_cell(8, code)
    at = from_origin(i * 400, (j + 1) * 300, 0.5, 0.5)
    reader = SheetSetFile("x", r"\.txt$")
    tile = SimpleNamespace(url="u", godlo=code, crs=japan.SZ_CRS, res=0.5)
    band, band_at = reader.sheet._parts(tile, data)
    old = np.full((600, 800), np.nan, dtype=np.float32)
    paste(old, at, band.astype(np.float32), band_at)
    new, new_at = reader.sheet._parts(tile, data, member_grid=reader._member(SheetSetRequest((), japan.SZ_CRS, at,
                                                                                               (600, 800), code)))
    assert new_at == at and np.array_equal(np.isnan(old), np.isnan(new)) and np.nanmax(np.abs(old - new)) == 0


def test_estimate_falls_back_to_bytes_per_tile(shizuoka, http_server, tmp_path, monkeypatch):
    """A sheet listed without a size counts bytes_per_tile in the estimate."""
    _bucket(http_server, {"2019/LP/Grid/08/OF/04/08OF0485.zip": b""})
    cache_dir = str(tmp_path)
    tiles, todo, mb = shizuoka.estimate(_sheet_grid("08OF0485"), cache_dir, None)
    assert (tiles, todo) == (1, 1) and mb == pytest.approx(shizuoka.bytes_per_tile() / 1e6)


# --- round 4 (2026-11-16) ------------------------------------------------------------------------------------------
def _three_sets(shizuoka, http_server, cache_dir):
    """A 1/500 sheet of FY2021 and FY2025 under the FY2022 quadrant sheet 08LD3341, searched: three cached sets."""
    quad = japan.jp_quad_cell(8, "08LD3341")
    left, _, _, top = japan.SZ_LEVELS["q"].edges(quad)
    small = japan.SZ_LEVELS["s"].cell_of(left + 450, top - 150)
    code = japan.jp_sheet(8, *small)
    letters = f"{code[2:4]}/{code[4:6]}"
    k25 = f"2025/LP/Grid/08/{letters}/{code}.zip"
    objects = {
        "2022/LP/Grid/08/LD/33/08LD3341.zip": _zip("08LD3341.txt",
                                                    _sheet_text("08LD3341", 2022.0, range(20), level="q")),
        f"2021/LP/Grid/08/{letters}/{code}.zip": _zip(f"{code}_DEM.txt", _sheet_text(code, 2021.0)),
        k25: _zip(f"{code}_0.5g.txt", _sheet_text(code, 2025.0, range(100, 120), csv=True)),
    }
    _bucket(http_server, objects)
    sl, sb, sr, st = japan.SZ_LEVELS["s"].edges(small)
    grid = make_grid((sl + 10, sb + 10, sr - 10, st - 10), 0.5, japan.SZ_CRS)
    _search(shizuoka, grid, cache_dir)
    return objects, k25, code, grid


def test_offline_order_by_survey(shizuoka, http_server, tmp_path):
    """Offline, the cached sets keep their order by survey (FY2025, FY2022, FY2021) when the owner's answer no longer
    names the FY2025 set (re-uploaded, its new download not cached yet): it is still read in its place by year. Once
    the new upload is cached too, it goes first and the old one right behind it (the same files, another ETag)."""
    cache_dir = str(tmp_path)
    objects, k25, code, grid = _three_sets(shizuoka, http_server, cache_dir)
    versions = shizuoka.index.versions
    assert [(s.level, s.year) for s in versions.cached(grid, cache_dir)] == [("s", 2025), ("q", 2022), ("s", 2021)]
    objects[k25] = _zip(f"{code}_0.5g.txt", _sheet_text(code, 2025.5, range(100, 120), csv=True))  # uploaded again
    for f in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "lp-grid", "*.json")):
        cache.forget(cache_dir, [f])
    shizuoka.index._listed.clear()
    now = shizuoka.tiles(grid)  # listed anew (its answer names the new upload), nothing downloaded
    old = [s for s in versions.cached(grid, cache_dir) if s.year == 2025]
    assert [(s.level, s.year) for s in versions.cached(grid, cache_dir)] == [("s", 2025), ("q", 2022), ("s", 2021)]
    assert old[0].key not in {s.key for s in now}
    new = next(s for s in now if s.year == 2025)
    shizuoka._download_and_record(new, cache_dir)  # the new upload cached, the old not pruned yet
    order = versions.cached(grid, cache_dir)
    assert [(s.year, s.key) for s in order[:2]] == [(2025, new.key), (2025, old[0].key)]
    assert [(s.level, s.year) for s in order[2:]] == [("q", 2022), ("s", 2021)]


def test_prune_with_a_current_set_without_data(shizuoka, http_server, tmp_path):
    """A sheet uploaded again as an empty member: its current set is recorded as missing (no data), which counts as
    in place for the prune, so the old upload's file is deleted and offline no longer read."""
    key = "2019/LP/Grid/08/OF/04/08OF0485.zip"
    objects = {key: _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _sheet_grid("08OF0485")
    _search(shizuoka, grid, cache_dir)
    assert len(shizuoka.files(grid, cache_dir)) == 1
    objects[key] = _zip("08OF0485_DEM.txt", b"\r\n")
    for f in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "lp-grid", "*.json")):
        cache.forget(cache_dir, [f])
    _search(shizuoka, grid, cache_dir)
    (sheet,) = shizuoka.tiles(grid)
    assert not os.path.exists(shizuoka.tile_path(cache_dir, sheet))
    assert not cache.due(cache_dir, shizuoka.tile_path(cache_dir, sheet))  # recorded: no data
    assert shizuoka.files(grid, cache_dir) == [] and shizuoka.index.versions.cached(grid, cache_dir) == []


@pytest.mark.parametrize("kind", ["strip", "ring"])
def test_tiles_to_ask_under_an_outline(kind):
    """With an outline (a strip across the 139.0 E tile line, a ring around a point on it), the owner of every sheet
    of both levels the outline keeps is among the tiles query asks (computed, no request)."""
    from rasterio.warp import transform
    from shapely.geometry import LineString, Point
    versions = japan.SZ_DTM.index.versions
    xs, ys = transform("EPSG:4326", japan.SZ_CRS, [139.0], [35.15])
    x, y = xs[0], ys[0]
    if kind == "strip":
        shape = LineString([(x - 3000, y - 40), (x + 3000, y + 40)]).buffer(15)
    else:
        shape = Point(x, y).buffer(1500).difference(Point(x, y).buffer(1450))
    left, bottom, right, top = shape.bounds
    grid = make_grid((left - 100, bottom - 100, right + 100, top + 100), 1.0, japan.SZ_CRS)
    grid.area_shape = shape
    asked = set(versions.tiles_to_ask(grid))
    for level, tiling in japan.SZ_LEVELS.items():
        cells = tiling.cells(grid)
        assert cells
        lons, lats = transform(japan.SZ_CRS, "EPSG:4326", [tiling.edges(c)[0] + tiling.cell[0] / 2 for c in cells],
                               [tiling.edges(c)[1] + tiling.cell[1] / 2 for c in cells])
        owners = {(math.floor(a / 0.25) * 0.25, math.floor(o / 0.25) * 0.25) for a, o in zip(lats, lons)}
        assert owners <= asked, (level, owners - asked)
    assert len({lon for _, lon in asked}) == 2  # both sides of the line


# --- Yamanashi --------------------------------------------------------------------------------------------------------
YM_RECORDED = os.path.join(HERE, "data", "recorded", "yamanashi")


def _ym_key(code, sequence="03", publication=2024):
    return f"Yamanashi/{publication}/{sequence}/LP/Grid/TIFF/08/{code[2:4]}/{code[4:6]}/{code}.zip"


def _ym_recorded(code):
    with open(os.path.join(YM_RECORDED, f"{code}.zip"), "rb") as f:
        return f.read()


@pytest.fixture
def yamanashi(http_server, monkeypatch):
    """The catalogue's two Yamanashi layers on the local server."""
    for layer in (japan.YM_DTM, japan.YM_DSM):
        monkeypatch.setattr(layer, "bucket", http_server.base)
        monkeypatch.setattr(layer.index.listing, "url", http_server.base)
        layer.index._listed.clear()
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return japan.YM_DTM


def _ym_grid(code, margin=1.0):
    left, bottom, right, top = japan.YM_DTM.levels["s"].edges(japan.jp_cell(8, code))
    return make_grid((left + margin, bottom + margin, right - margin, top - margin), 0.5, japan.YM_CRS)


def test_yamanashi_keys_and_prefixes():
    """The keys each product takes (its own sequence folder of the publication 2024, a sheet's own folders) and the
    prefixes a box asks: under Yamanashi/ only, never under another prefecture's top folder of the bucket."""
    cell = japan.jp_cell(8, "08KD3949")
    for sequence in ("03", "02", "01"):
        parse = japan.ym_key(sequence)
        assert parse(_ym_key("08KD3949", sequence)) == (2024, "s", cell)
        others = [s for s in ("01", "02", "03") if s != sequence]
        assert all(parse(_ym_key("08KD3949", other)) is None for other in others)
        assert parse(_ym_key("08KD3949", sequence, 2026)) is None  # another publication: set by hand
        assert parse(_ym_key("08KD3949", sequence).replace("/TIFF/", "/TXT/")) is None
        assert parse(_ym_key("08KD3949", sequence).replace("/39/08KD", "/38/08KD")) is None  # not its folder
        assert parse(_ym_key("08KD3949", sequence).replace("Yamanashi/", "Tokyo/")) is None
    box = (cell[0] * 400 - 50_000, cell[1] * 300, cell[0] * 400 + 100, cell[1] * 300 + 100)  # x -50 400..-300
    prefixes = japan.ym_prefixes("03")
    assert prefixes("Yamanashi/", box) == ["Yamanashi/2024/03/LP/Grid/TIFF/08/KC/",
                                            "Yamanashi/2024/03/LP/Grid/TIFF/08/KD/"]
    assert prefixes("Tokyo/", box) == [] and prefixes("Hyogo/", box) == []
    assert japan.ym_prefixes("02")("Yamanashi/", box)[1] == "Yamanashi/2024/02/LP/Grid/TIFF/08/KD/"


@pytest.mark.parametrize("sequence, product", [("02", "dsm2"), ("01", "dsm1")])
def test_yamanashi_surface_constant(sequence, product):
    """Both values of YM_SURFACE: the layer of each lists its own folder and keeps its own cache folder, index
    answers and description; the catalogue's surface model is DSM2 (the baselines rest on it)."""
    layer = japan.ym_layer(sequence)
    assert layer.folder == f"yamanashi/{product}/2024" and layer.index.prefix == product
    assert layer.index.top == "yamanashi" and layer.description.endswith(f"(surface, {product.upper()})")
    assert layer.prefixes("Yamanashi/", (0, -1, 1, 0)) == [f"Yamanashi/2024/{sequence}/LP/Grid/TIFF/08/KE/"]
    assert layer.parse(_ym_key("08KD3949", sequence)) is not None and layer.parse(_ym_key("08KD3949")) is None
    assert layer.levels["s"].cell == japan.SHEET_500 and layer.members == r"\.tif$"
    assert japan.YM_SURFACE == "02" and src.SOURCES["yamanashi"].nmpt is japan.YM_DSM
    assert japan.YM_DSM.folder == "yamanashi/dsm2/2024" and japan.YM_DTM.folder == "yamanashi/dem/2024"
    assert japan.YM_DTM.index.prefix == "dem" and "DSM2" in src.SOURCES["yamanashi"].description
    # the source built with this value: its surface layer and every text naming it follow the one value
    other = "DSM2" if product == "dsm1" else "DSM1"
    source = japan.ym_source(sequence)
    assert source.nmpt.folder == layer.folder and source.nmt is japan.YM_DTM
    assert source.name == "Yamanashi (lidar 0.5 m)"
    for text in (source.description, source.note, source.listing.surface):
        assert product.upper() in text and other not in text, text
    assert japan.YM_SURFACE_TEXT[sequence] in source.description and japan.YM_SURFACE_TEXT[sequence] in source.note
    assert ("without power lines" in source.note) == (sequence == "02")
    if sequence == japan.YM_SURFACE:  # the catalogue's entry is this builder's
        catalogue = src.SOURCES["yamanashi"]
        assert (catalogue.description, catalogue.note, catalogue.listing) == (source.description, source.note,
                                                                             source.listing)


@pytest.mark.parametrize("code, shape, valid", [
    ("08KD1638", (222, 158), 22877),   # on the prefecture's border: 158 x 222 px of its 800 x 600
    ("08LD4359", (3, 1), 3),           # a sliver: 1 x 3 px
])
def test_yamanashi_border_sheets_on_their_box(yamanashi, http_server, tmp_path, code, shape, valid):
    """The publisher's border sheets (recorded 2026-11-26) are composed on their sheet's box: 800 x 600 px in
    EPSG:6676, the file's pixels where the file has them (its own pixel edges on the sheet's lattice), the rest no
    data; only Yamanashi/ is listed, never another prefecture's folder."""
    import zipfile
    from rasterio.io import MemoryFile
    data = _ym_recorded(code)
    tokyo_key = "Tokyo/2023/01/LP/Grid/TIFF/09/KC/63/09KC6361.zip"
    _bucket(http_server, {_ym_key(code): data, tokyo_key: b"not asked"})
    cache_dir = str(tmp_path)
    grid = _ym_grid(code)
    _search(yamanashi, grid, cache_dir)
    (path,) = yamanashi.files(grid, cache_dir)
    assert path.replace(os.sep, "/").split("/yamanashi/dem/2024/s/")[1].startswith(f"{code[2:4]}/{code[4:6]}/2024_{code}_")
    cell = japan.jp_cell(8, code)
    left, top = cell[0] * 400, (cell[1] + 1) * 300
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.crs.to_epsg() == 6676 and tile.shape == (600, 800)
        assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5))
    with zipfile.ZipFile(io.BytesIO(data)) as z, MemoryFile(z.read(f"{code}.tif")) as mem, mem.open() as own:
        assert own.shape == shape
        mine = own.read(1)
        col, row = round((own.transform.c - left) / 0.5), round((top - own.transform.f) / 0.5)
    mine = np.where(mine > 1e30, np.nan, mine)
    part = values[row:row + shape[0], col:col + shape[1]]
    assert np.array_equal(np.isnan(part), np.isnan(mine)) and np.allclose(part, mine, atol=0.006, equal_nan=True)
    assert np.count_nonzero(~np.isnan(values)) == valid
    assert not any(r.path.startswith("/Tokyo") for r in http_server.requests())
    prefixes = {dict(r.query).get("prefix") for r in http_server.requests() if r.path == "/"}
    assert "" in prefixes and f"Yamanashi/2024/03/LP/Grid/TIFF/08/{code[2:4]}/" in prefixes
    assert all(p == "" or p.startswith("Yamanashi/2024/03/LP/Grid/TIFF/08/") for p in prefixes)
    assert yamanashi.used(grid, cache_dir)["credit"]["data"] == japan.YM_CREDIT.data


def test_yamanashi_lake_sheet_without_data(yamanashi, http_server, tmp_path):
    """A listed sheet whose file has no valid pixel (08LE9188, mid Lake Motosu, as published) is recorded as without
    data, never an error and never asked again by the next search; a sheet the listing lacks is never asked."""
    code = "08LE9188"
    _bucket(http_server, {_ym_key(code): _ym_recorded(code)})
    cache_dir = str(tmp_path)
    cell = japan.jp_cell(8, code)
    left, bottom, right, top = yamanashi.levels["s"].edges(cell)
    grid = make_grid((left + 1, bottom + 1, right + 399, top - 1), 0.5, japan.YM_CRS)  # and the unlisted east sheet
    _search(yamanashi, grid, cache_dir)
    (sheet,) = yamanashi.tiles(grid)
    assert (sheet.i, sheet.j) == cell
    assert not os.path.exists(yamanashi.tile_path(cache_dir, sheet))
    assert not cache.due(cache_dir, yamanashi.tile_path(cache_dir, sheet))  # recorded: no data
    _search(yamanashi, grid, cache_dir)
    assert _zips(http_server) == 1 and yamanashi.files(grid, cache_dir) == []


def test_yamanashi_listed_file_missing_is_an_error(yamanashi, http_server, tmp_path):
    """A listed key the bucket no longer gives (404 NoSuchKey) is an error of its sheet, nothing recorded."""
    code = "08KD1638"
    objects = {_ym_key(code): _ym_recorded(code)}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    yamanashi._use(cache_dir)
    (sheet,) = yamanashi.tiles(_ym_grid(code))
    del objects[_ym_key(code)]
    with pytest.raises(RuntimeError, match="404"):
        yamanashi._download_and_record(sheet, cache_dir)
    assert cache.due(cache_dir, yamanashi.tile_path(cache_dir, sheet))


def test_yamanashi_catalogue_entry():
    """The catalogue's own settings: region jp-19, zone VIII, the terrain from 03 and the surface from 02 in
    japan-pointcloud, two connections at once, the credit; its offline boxes meet neither Tokyo's nor Shizuoka's."""
    source = src.SOURCES["yamanashi"]
    assert source.regions == ("jp-19",) and source.countries == ("jp",) and source.crs == "EPSG:6676"
    assert source.nmt is japan.YM_DTM and source.nmpt is japan.YM_DSM and source.credits == (japan.YM_CREDIT,)
    assert japan.YM_DTM.bucket == japan.YM_DSM.bucket == "https://japan-pointcloud.s3.ap-northeast-1.amazonaws.com"
    assert japan.YM_DTM.index.listing.url == japan.YM_DTM.bucket and japan.YM_DTM.folders_pattern == "Yamanashi/"
    assert japan.YM_DTM.prefixes("Yamanashi/", (0, -1, 1, 0))[0].startswith("Yamanashi/2024/03/")
    assert japan.YM_DSM.prefixes("Yamanashi/", (0, -1, 1, 0))[0].startswith("Yamanashi/2024/02/")
    # the catalogue's own two layers: each takes its own folder's keys only, lists and caches apart
    key3, key2 = _ym_key("08KD3949", "03"), _ym_key("08KD3949", "02")
    assert japan.YM_DTM.parse(key3) == japan.YM_DSM.parse(key2) == (2024, "s", japan.jp_cell(8, "08KD3949"))
    assert japan.YM_DTM.parse(key2) is None and japan.YM_DSM.parse(key3) is None
    assert (japan.YM_DTM.folder, japan.YM_DTM.index.prefix) == ("yamanashi/dem/2024", "dem")
    assert (japan.YM_DSM.folder, japan.YM_DSM.index.prefix) == ("yamanashi/dsm2/2024", "dsm2")
    assert japan.YM_DTM.index.top == japan.YM_DSM.index.top == "yamanashi"
    assert japan.YM_DTM.reader.sheet.members == japan.YM_DSM.reader.sheet.members == r"\.tif$"
    assert japan.YM_DTM.credit is japan.YM_DSM.credit is japan.YM_CREDIT
    assert (japan.YM_DTM.bytes_per_tile(), japan.YM_DSM.bytes_per_tile()) == (0.95e6, 1.33e6)
    assert src.net.HOST_SLOTS_OF["japan-pointcloud.s3.ap-northeast-1.amazonaws.com"] == 2
    assert source.neighbours == ("tokyo", "shizuoka", "kanagawa")
    assert src.SOURCES["tokyo"].neighbours == src.SOURCES["shizuoka"].neighbours == ("yamanashi", "kanagawa")


def test_yamanashi_offline_boxes():
    """Yamanashi's offline boxes (region jp-19) come before Tokyo's and Shizuoka's (theirs hold its land south of the
    five lakes and on its eastern edge; the first box holding a point wins) and keep off their land: of the coverage
    map's outlines (viewer/src/coverage/shapes.json) they hold most of jp-19 and little of jp-13 and jp-22; the
    points of a few sheets' centres choose Yamanashi offline, and Tokyo and Shizuoka keep their own places."""
    import json
    import math
    from shapely.geometry import box, shape
    from shapely.ops import unary_union
    source = src.SOURCES["yamanashi"]
    assert all(region == "jp-19" for region, _ in source.offline) and source.border_boxes == japan.YM_BORDER_BOXES
    order = list(src.SOURCES)
    assert order.index("yamanashi") < order.index("tokyo") < order.index("shizuoka")
    with open(os.path.join(os.path.dirname(HERE), "viewer", "src", "coverage", "shapes.json"), encoding="utf-8") as f:
        outlines = {x["properties"]["id"]: shape(x["geometry"]) for x in json.load(f)["features"]
                    if x["properties"]["id"] in ("jp-13", "jp-19", "jp-22")}
    ours = unary_union([box(w, s, e, n) for _, (s, n, w, e) in source.offline])
    km2 = {k: g.intersection(ours).area * 111.32 ** 2 * math.cos(math.radians(35.6)) for k, g in outlines.items()}
    # measured 2026-11-26 (the boxes of the cells): a box grown or moved by a cell (0.01 x 0.05 degree, about 4.5
    # km²) changes one of them
    assert km2 == {"jp-19": pytest.approx(4377.98, abs=0.5), "jp-13": pytest.approx(13.92, abs=0.5),
                   "jp-22": pytest.approx(44.76, abs=0.5)}, km2
    from sources import choose

    def offline(lat, lon):
        return next((region for region, (s, n, w, e) in choose.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e),
                    None)
    # Yamanashi's own places (Mizugaki, Minobu, Kofu, Uenohara's east), two of them in a sister's box too (Minobu in
    # Shizuoka's, Uenohara's east, 1.4 km inside Yamanashi, in Tokyo's)
    for lat, lon in ((35.8946, 138.5948), (35.3700, 138.4400), (35.6622, 138.5683), (35.6700, 139.0600)):
        assert offline(lat, lon) == "jp-19", (lat, lon)
    # The neighbours' land next to Yamanashi's boxes (0.3-0.5 km outside them, at least 0.3 km inside the neighbour by
    # Natural Earth's admin-1 1:10m outlines, 2026-11-26): the cells its land did not win; a box grown over them takes
    # them. Tokyo's, Shizuoka's and Kanagawa's (since 2026-11-27) keep their own boxes; Nagano's and Saitama's have
    # none (Kanagawa's at Lake Yamanaka's south lies in a Shizuoka box, as before Yamanashi)
    for lat, lon, code in ((35.802, 138.972, "jp-13"), (35.676, 139.084, "jp-13"), (35.728, 139.004, "jp-13"),
                           (35.548, 138.228, "jp-22"), (35.348, 138.522, "jp-22"), (35.402, 138.228, "jp-22"),
                           (35.852, 138.198, None), (35.952, 138.328, None), (35.802, 138.178, None),  # Nagano
                           (35.854, 138.814, None), (35.854, 138.864, None), (35.904, 138.718, None),  # Saitama
                           (35.548, 139.112, "jp-14"), (35.398, 138.922, "jp-22"), (35.598, 139.122, "jp-14")):  # Kanagawa
        assert offline(lat, lon) == code, (lat, lon, offline(lat, lon))


def _sheet_tif_zip(code, value, zone=8, crs="EPSG:6676"):
    """A ZIP of one GeoTIFF of a whole 1/500 sheet (800 x 600 px of 0.5 m) holding one value, as Yamanashi's and
    Tokyo's sheets are published (float32, nodata 1.70141e38, on the sheet's box)."""
    from rasterio.io import MemoryFile
    i, j = japan.jp_cell(zone, code)
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=800, height=600, count=1, dtype="float32", crs=crs,
                          nodata=1.70141e38, transform=from_origin(i * 400, (j + 1) * 300, 0.5, 0.5)) as dst:
            dst.write(np.full((600, 800), value, dtype=np.float32), 1)
        return _zip(f"{code}.tif", memfile.read())


def _paged_bucket(http_server, objects):
    """A bucket answering ListObjectsV2 page by page: max-keys keys a page, the continuation token the index of the
    next key (the delimiter listing of the top folders in one page), GET of its keys, 404 NoSuchKey otherwise."""
    def answer(request):
        query = dict(request.query)
        if request.path == "/" and query.get("list-type") == "2":
            prefix = query.get("prefix", "")
            keys = sorted(k for k in objects if k.startswith(prefix))
            if query.get("delimiter") == "/":
                folders = sorted({prefix + k[len(prefix):].split("/", 1)[0] + "/" for k in keys
                                  if "/" in k[len(prefix):]})
                body = (f"<ListBucketResult xmlns='{NS}'><IsTruncated>false</IsTruncated>"
                        + "".join(f"<CommonPrefixes><Prefix>{escape(p)}</Prefix></CommonPrefixes>" for p in folders))
            else:
                start, size = int(query.get("continuation-token", "0")), int(query.get("max-keys", "1000"))
                page, more = keys[start:start + size], start + size < len(keys)
                body = (f"<ListBucketResult xmlns='{NS}'><IsTruncated>{'true' if more else 'false'}</IsTruncated>"
                        + (f"<NextContinuationToken>{start + size}</NextContinuationToken>" if more else "")
                        + "".join(f"<Contents><Key>{escape(k)}</Key><LastModified>2025-12-11T08:12:45.000Z"
                                  f"</LastModified><ETag>&quot;{_etag(objects[k])}&quot;</ETag>"
                                  f"<Size>{len(objects[k])}</Size></Contents>" for k in page))
            return Answer(200, (body + "</ListBucketResult>").encode(), {"Content-Type": "application/xml"})
        key = request.path.lstrip("/")
        if key in objects:
            return Answer(200, objects[key], {"Content-Type": "application/x-zip-compressed"})
        return Answer(404, b"<Error><Code>NoSuchKey</Code></Error>", {"Content-Type": "application/xml"})
    http_server.route("/", answer)


def _row_of_sheets(first, count):
    """count sheets of one row from the sheet `first` eastwards (codes), and a grid of 1 m over them."""
    i, j = japan.jp_cell(8, first)
    codes = [japan.jp_sheet(8, i + k, j) for k in range(count)]
    grid = make_grid((i * 400 + 1, j * 300 + 1, (i + count) * 400 - 1, (j + 1) * 300 - 1), 1.0, japan.YM_CRS)
    return codes, grid


def test_yamanashi_paged_listing(yamanashi, http_server, tmp_path, monkeypatch):
    """A block listed in pages (2 keys a page here; LE holds 10 pages of 1 000 on the bucket): the catalogue's terrain
    layer follows the continuation tokens of its own prefix and gets every sheet of the block, the 7 keys of 03 over
    4 pages; the 02 and Tokyo keys beside them are never listed by it nor downloaded."""
    codes, grid = _row_of_sheets("08KD3941", 5)
    objects = {_ym_key(c, "03"): _sheet_tif_zip(c, 1000.0 + k) for k, c in enumerate(codes)}
    objects.update({_ym_key(c, "03"): _sheet_tif_zip(c, 9.0) for c in ("08KD3911", "08KD3912")})  # same block
    objects.update({_ym_key(c, "02"): b"surface" for c in codes})
    objects["Tokyo/2023/01/LP/Grid/TIFF/09/KD/39/09KD3941.zip"] = b"another prefecture"
    _paged_bucket(http_server, objects)
    monkeypatch.setattr(yamanashi.index.listing, "max_keys", 2)
    cache_dir = str(tmp_path)
    _search(yamanashi, grid, cache_dir)
    pages = [dict(r.query) for r in http_server.requests() if r.path == "/" and "delimiter" not in dict(r.query)]
    block = [q for q in pages if q["prefix"] == "Yamanashi/2024/03/LP/Grid/TIFF/08/KD/"]
    # each index tile asking the block went through its 4 pages, in order
    assert block and [q.get("continuation-token") for q in block] == [None, "2", "4", "6"] * (len(block) // 4)
    assert all(q["prefix"].startswith("Yamanashi/2024/03/") for q in pages)
    files = yamanashi.files(grid, cache_dir)
    assert sorted(os.path.basename(p).split("_")[1] for p in files) == sorted(codes)
    for path in files:
        code = os.path.basename(path).split("_")[1]
        with rio.open(path) as tile:
            assert np.allclose(tile.read(1), 1000.0 + codes.index(code), atol=0.006)
    zips = {r.path for r in http_server.requests() if r.path.endswith(".zip")}
    assert zips == {"/" + _ym_key(c, "03") for c in codes}


def test_yamanashi_surface_layer_downloads_its_own_sheets(yamanashi, http_server, tmp_path, monkeypatch):
    """The catalogue's surface layer (the source's nmpt, DSM2) lists 02 only (in pages too), reads 02's ZIP of a
    sheet and caches it as yamanashi/dsm2/2024/s/<letters>/<digits>/2024_<sheet>_<key>.tif with 02's heights; the
    terrain's and DSM1's files of the same sheet are never asked."""
    layer = src.SOURCES["yamanashi"].nmpt
    assert layer is japan.YM_DSM
    codes, grid = _row_of_sheets("08KD3941", 3)
    objects = {}
    for c in codes:
        objects[_ym_key(c, "03")] = _sheet_tif_zip(c, 10.0)
        objects[_ym_key(c, "02")] = _sheet_tif_zip(c, 30.0)
        objects[_ym_key(c, "01")] = _sheet_tif_zip(c, 50.0)
    _paged_bucket(http_server, objects)
    monkeypatch.setattr(layer.index.listing, "max_keys", 2)
    cache_dir = str(tmp_path)
    layer.index._listed.clear()
    layer.download(grid, cache_dir, None, "surface")
    files = layer.files(grid, cache_dir)
    assert len(files) == 3
    for path in files:
        rel = os.path.relpath(path, cache_dir).replace(os.sep, "/")
        code = os.path.basename(path).split("_")[1]
        assert rel.startswith(f"yamanashi/dsm2/2024/s/{code[2:4]}/{code[4:6]}/2024_{code}_"), rel
        with rio.open(path) as tile:
            assert np.allclose(tile.read(1), 30.0, atol=0.006)
    zips = {r.path for r in http_server.requests() if r.path.endswith(".zip")}
    assert zips == {"/" + _ym_key(c, "02") for c in codes}
    prefixes = {dict(r.query).get("prefix") for r in http_server.requests() if r.path == "/"}
    assert "Yamanashi/2024/02/LP/Grid/TIFF/08/KD/" in prefixes
    assert all(p == "" or p.startswith("Yamanashi/2024/02/LP/Grid/TIFF/08/") for p in prefixes)
    pages = [dict(r.query) for r in http_server.requests() if r.path == "/" and "delimiter" not in dict(r.query)]
    assert any(q.get("continuation-token") for q in pages)  # 02's KD block in pages too
    assert os.path.isfile(layer.index_path(cache_dir, *_owner_tile(codes[0])))  # yamanashi/sheet-index/dsm2/...
    assert "sheet-index/dsm2/" in layer.index_path(cache_dir, 35.75, 138.5).replace(os.sep, "/")


def _owner_tile(code):
    from rasterio.warp import transform
    i, j = japan.jp_cell(8, code)
    lons, lats = transform(japan.YM_CRS, "EPSG:4326", [(i + 0.5) * 400], [(j + 0.5) * 300])
    return math.floor(lats[0] / 0.25) * 0.25, math.floor(lons[0] / 0.25) * 0.25


def _border_scene(tmp_path, lat, lon):
    """A Yamanashi grid of 800 x 300 px of 1 m in EPSG:6676 whose western half holds its data (100 m) and whose
    eastern half, reaching the grid's edge, has none (across a border): (grid, elevation path, cells of the two
    halves' sheets)."""
    from rasterio.warp import transform
    xs, ys = transform("EPSG:4326", japan.YM_CRS, [lon], [lat])
    i, j = int(xs[0] // 400), int(ys[0] // 300)
    grid = make_grid((i * 400, j * 300, (i + 2) * 400, (j + 1) * 300), 1.0, japan.YM_CRS)
    from shapely.geometry import box
    grid.area_shape = box(*grid.bounds)  # the footprint: the whole grid (a search's area), not a circle in it
    elevation = np.full((grid.height, grid.width), 100.0, np.float32)
    elevation[:, grid.width // 2:] = np.nan
    path = str(tmp_path / "nmt.npy")
    np.save(path, elevation)
    return grid, path, (i, j), (i + 1, j)


def test_yamanashi_gap_filled_from_shizuoka_as_a_seam(shizuoka, http_server, tmp_path):
    """The neighbour fill of the catalogue's pair: a Yamanashi grid by the Shizuoka border (Nanbu, inside Shizuoka's
    offline boxes) with no data in its eastern half gets Shizuoka's sheet there (its listing and ZIP on the local
    bucket), counted as Shizuoka's and kept in the joined mask (a seam: Data.joined, no anchors on its edge), never in
    the mask of the filled pixels; its own data stay."""
    assert "shizuoka" in src.SOURCES["yamanashi"].neighbours and "yamanashi" in src.SOURCES["shizuoka"].neighbours
    grid, path, _, east = _border_scene(tmp_path, 35.30, 138.55)
    code = japan.jp_sheet(8, *east)
    _bucket(http_server, {f"2019/LP/Grid/08/{code[2:4]}/{code[4:6]}/{code}.zip": _zip(f"{code}_DEM.txt",
                                                                                       _sheet_text(code, 120.0))})
    src.mosaic.used_data.clear()
    try:
        out = str(tmp_path / "joined.npy")
        joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [src.SOURCES["shizuoka"]],
                                                               str(tmp_path / "cache"), out)
        result = np.load(path)
        assert joined_path == out and [(s.id, n) for s, n in counts] == [("shizuoka", 400 * 300)]
        assert np.allclose(result[:, 400:], 120.0, atol=0.006) and np.allclose(result[:, :400], 100.0)
        joined = np.load(out)
        assert joined[:, 400:].all() and not joined[:, :400].any()
        assert any(u.get("credit", {}).get("data") == japan.SZ_CREDIT.data for u in src.mosaic.used_data)
        assert not np.isnan(result).any()  # nothing left for the fallback: no pixel of the seam is "filled"
    finally:
        src.mosaic.used_data.clear()


def test_yamanashi_gap_filled_from_tokyo_across_zones(tokyo, http_server, tmp_path, monkeypatch):
    """The same for Tokyo (zone IX sheets onto Yamanashi's zone VIII grid, inside Tokyo's boxes by Kosuge): every
    Tokyo sheet under the gap from its table and bucket, the gap Tokyo's heights, a seam, never filled."""
    from rasterio.warp import transform, transform_bounds
    grid, path, _, _ = _border_scene(tmp_path, 35.745, 139.00)
    left, bottom, right, top = transform_bounds(japan.YM_CRS, japan.TK_CRS, *grid.bounds)
    middle = (grid.bounds[0] + grid.bounds[2]) / 2
    codes = set()
    for i in range(int(left // 400), int(right // 400) + 1):  # Tokyo's sheets wholly over the gap (no overlap with
        for j in range(int(bottom // 300), int(top // 300) + 1):  # the data, so no offset to match: as they are)
            xs, _ = transform(japan.TK_CRS, japan.YM_CRS, [i * 400, i * 400], [j * 300, (j + 1) * 300])
            if min(xs) > middle + 2:
                codes.add(japan.jp_sheet(9, i, j))
    assert codes
    for code in codes:
        http_server.add(f"/2023/dig/grd50/{code}.zip", _sheet_tif_zip(code, 120.0, zone=9, crs="EPSG:6677"))
    monkeypatch.setattr(japan, "_tk_table", lambda: {code: (2023,) for code in codes})
    src.mosaic.used_data.clear()
    try:
        out = str(tmp_path / "joined.npy")
        joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [src.SOURCES["tokyo"]],
                                                               str(tmp_path / "cache"), out)
        result = np.load(path)
        joined = np.load(out)
        assert joined_path == out and [s.id for s, _ in counts] == ["tokyo"]
        assert counts[0][1] == int(joined.sum()) > 0.5 * 400 * 300  # most of the gap under the sheets served
        assert np.allclose(result[joined], 120.0, atol=0.006) and np.allclose(result[:, :400], 100.0)
        assert not joined[:, :400].any() and np.isnan(result[:, 400:][~joined[:, 400:]]).all()
    finally:
        src.mosaic.used_data.clear()


# --- Kanagawa ---------------------------------------------------------------------------------------------------------
KG_RECORDED = os.path.join(HERE, "data", "recorded", "kanagawa")


def _kg_key(code, year=2024, sub="01", kind="MESH"):
    return f"{year}/{sub}/LP/Grid/{kind}/09/{code[2:4]}/{code[4:6]}/{code}.zip"


def _kg_recorded(code):
    with open(os.path.join(KG_RECORDED, f"{code}.zip"), "rb") as f:
        return f.read()


_LEM_ROWS = {}


def _lem_text(codes) -> bytes:
    """A .lem body as the publisher writes it (CRLF, a 10-character record number, 5-character integers in 0.1 m),
    from one int code per pixel (rows north to south); each distinct row is formatted once."""
    lines = []
    for k, row in enumerate(np.asarray(codes)):
        key = row.tobytes()
        if key not in _LEM_ROWS:
            _LEM_ROWS[key] = "".join(f"{v:5d}" for v in row.tolist())
        lines.append(f"{k + 1:10d}{_LEM_ROWS[key]}")
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def _lem_zip(code, codes) -> bytes:
    """A MESH sheet's ZIP: <code>_0.5g.lem and a cp932 header <code>_0.5g.csv (never read)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{code.lower()}_0.5g.csv", "測量年,2024\r\n東西方向の点数,2000\r\n".encode("cp932"))
        z.writestr(f"{code.lower()}_0.5g.lem", _lem_text(codes))
    return buffer.getvalue()


def _kg_codes(value, holes=None):
    """1500 x 2000 codes of one height (0.1 m), -1111 on the rows `holes` (a slice)."""
    codes = np.full((1500, 2000), value, dtype=np.int64)
    if holes is not None:
        codes[holes] = -1111
    return codes


@pytest.fixture
def kanagawa(http_server, monkeypatch):
    """The catalogue's Kanagawa layer on the local server."""
    layer = japan.KG_DTM
    monkeypatch.setattr(layer, "bucket", http_server.base)
    monkeypatch.setattr(layer.index.listing, "url", http_server.base)
    layer.index._listed.clear()
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return layer


def _kg_grid(code, margin=1.0):
    left, bottom, right, top = japan.KG_DTM.levels["q"].edges(japan.jp_quad_cell(9, code))
    return make_grid((left + margin, bottom + margin, right - margin, top - margin), 0.5, japan.KG_CRS)


def test_kanagawa_keys_and_prefixes():
    """The catalogue's key parser takes the MESH sheets of KG_FOLDERS only (the quadrant sheets of zone IX: 09NC1222
    is x -69 000..-68 000, y -93 750..-93 000), never 2022/02 (the 1 m grid), 2019/02, the CSV variant, the DSM or a
    year set by hand later; a box asks one prefix per subfolder and 1/50000 sheet, none for another year."""
    cell = japan.jp_quad_cell(9, "09NC1222")
    assert cell == (-69, -125) and japan.KG_LEVELS["q"].edges(cell) == (-69_000, -93_750, -68_000, -93_000)
    assert japan.jp_quad_sheet(9, *cell) == "09NC1222" and japan.jp_quad_cell(9, "09NC1225") is None
    for year, subs in japan.KG_FOLDERS.items():
        for sub in subs:
            assert japan.kg_key(_kg_key("09NC1222", year, sub)) == (year, "q", cell)
    assert list(japan.KG_FOLDERS) == [2024, 2022, 2021, 2020, 2019] and japan.KG_FOLDERS[2020] == ("02", "01")
    for key in (_kg_key("09NC1222", 2022, "02"), _kg_key("09NC1222", 2019, "02"), _kg_key("09NC1222", 2026),
                _kg_key("09NC1222", kind="CSV"), "2021/01/LP/DSM/TXT/09/LD/75/09LD7541.zip",
                _kg_key("09NC1222").replace("/12/09NC", "/13/09NC"), _kg_key("08NC1222"),
                _kg_key("09NC1222").replace(".zip", "_2.zip")):
        assert japan.kg_key(key) is None, key
    assert japan.kg_key(_kg_key("09LD7541", 2022)) == (2022, "q", japan.jp_quad_cell(9, "09LD7541"))
    box = (-69_000, -93_750, -68_000, -93_000)
    assert japan.kg_prefixes("2020/", box) == ["2020/02/LP/Grid/MESH/09/NC/", "2020/01/LP/Grid/MESH/09/NC/"]
    assert japan.kg_prefixes("2024/", (-81_000, -93_750, -79_000, -93_000)) == \
        ["2024/01/LP/Grid/MESH/09/NB/", "2024/01/LP/Grid/MESH/09/NC/"]
    assert japan.kg_prefixes("2023/", box) == [] and japan.kg_prefixes("doc/", box) == []


def test_lem_grid():
    """The .lem parser (sheetfile._lem_grid): heights in 0.1 m, rows north to south; -9999 and -1111 no data, a height
    below 0 m real, a five-digit height filling its field; CRLF or LF; a short line, a field that is no integer, a
    missing row or a record out of order is an error."""
    from sources.readers.sheetfile import _lem_grid
    codes = np.array([[55, -9999, -1111, -5], [10927, 0, -1, 7]])
    text = _lem_text(codes)
    assert text.splitlines()[0] == b"         1   55-9999-1111   -5"
    for body in (text, text.replace(b"\r\n", b"\n"), text.rstrip(b"\r\n")):
        heights = _lem_grid(body, (2, 4))
        assert heights.dtype == np.float32
        assert np.array_equal(np.isnan(heights), [[False, True, True, False], [False, False, False, False]])
        assert np.allclose(heights[~np.isnan(heights)], [5.5, -0.5, 1092.7, 0.0, -0.1, 0.7])
    first, second = text.split(b"\r\n")[:2]
    for broken, match in ((first + b"\r\n" + second[:-1], "line 2 has 29 characters, 30 expected"),
                          (first + b"\r\n" + second.replace(b"    0", b"  0 0"), "not an integer"),
                          (first + b"\r\n" + second.replace(b"    0", b"   0-"), "not an integer"),
                          (first + b"\r\n" + second.replace(b"    0", b"     "), "not an integer"),
                          (first + b"\r\n" + second.replace(b"    0", b"    x"), "not an integer"),
                          (first, "1 lines, 2 expected"),
                          (second + b"\r\n" + first, "line 1 holds record 2")):
        with pytest.raises(RuntimeError, match=match):
            _lem_grid(broken, (2, 4))


def _kg_header_box(data, code):
    """The box (left, bottom, right, top in m) a recorded sheet's cp932 CSV header gives (区画左下X/Y, 区画右上X/Y in cm,
    X northward), read here by the test's own lines, not the app's."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        rows = dict(line.split(",", 1) for line in z.read(f"{code.lower()}_0.5g.csv").decode("cp932").splitlines()
                    if "," in line)
    return (int(rows["区画左下Y座標"]) / 100, int(rows["区画左下X座標"]) / 100, int(rows["区画右上Y座標"]) / 100,
            int(rows["区画右上X座標"]) / 100)


@pytest.mark.parametrize("code, year, valid", [("09MC9132", 2024, 330), ("09MD5023", 2021, 0)])
def test_kanagawa_recorded_sheets(kanagawa, http_server, tmp_path, code, year, valid):
    """The publisher's sheets (recorded 2026-11-27; the numbers measured then by a parser of their own): mid Lake Ashi
    has 330 valid cells, all at 725.0-725.3 m, composed on its box (2000 x 1500 px of 0.5 m in EPSG:6677), the box
    the code gives equal to the corners in the sheet's own header; a sheet without a valid cell (-1111 and -9999
    only) is recorded as without data, never an error and never asked again."""
    data = _kg_recorded(code)
    _bucket(http_server, {_kg_key(code, year): data})
    cache_dir = str(tmp_path)
    grid = _kg_grid(code)
    _search(kanagawa, grid, cache_dir)
    (sheet,) = kanagawa.tiles(grid)
    left, bottom, right, top = japan.KG_LEVELS["q"].edges(japan.jp_quad_cell(9, code))
    assert _kg_header_box(data, code) == (left, bottom, right, top)
    path = kanagawa.tile_path(cache_dir, sheet)
    if valid:
        assert path.replace(os.sep, "/").split("/kanagawa/grid-mesh/q/")[1].startswith(
            f"{code[2:4]}/{code[4:6]}/{year}_{code}_")
        with rio.open(path) as tile:
            values = tile.read(1)
            assert tile.crs.to_epsg() == 6677 and tile.shape == (1500, 2000)
            assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5))
        assert np.count_nonzero(~np.isnan(values)) == valid
        assert 725.0 - 0.006 <= np.nanmin(values) and np.nanmax(values) <= 725.3 + 0.006
        assert kanagawa.used(grid, cache_dir)["credit"]["data"] == japan.KG_CREDIT.data
    else:
        assert not os.path.exists(path) and not cache.due(cache_dir, path)  # recorded: no data
        assert kanagawa.files(grid, cache_dir) == []
    _search(kanagawa, grid, cache_dir)
    assert _zips(http_server) == 1  # the second search asks nothing for the sheet, with or without data


def test_kanagawa_rows_north_and_west_first(kanagawa, http_server, tmp_path):
    """A .lem's first line is the sheet's northern row and each line's first field its western column: a sheet whose
    first row, last row and first column differ lands so on the sheet's box."""
    code = "09NC1222"
    codes = np.full((1500, 2000), 500, dtype=np.int64)
    codes[0, :], codes[-1, :], codes[:, 0] = 1000, 2000, 3000
    _bucket(http_server, {_kg_key(code): _lem_zip(code, codes)})
    cache_dir = str(tmp_path)
    grid = _kg_grid(code)
    _search(kanagawa, grid, cache_dir)
    (path,) = kanagawa.files(grid, cache_dir)
    left, bottom, right, top = japan.KG_LEVELS["q"].edges(japan.jp_quad_cell(9, code))
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5))
    assert np.allclose(values[0, 1:], 100.0, atol=0.006) and np.allclose(values[-1, 1:], 200.0, atol=0.006)
    assert np.allclose(values[:, 0], 300.0, atol=0.006) and np.allclose(values[1:-1, 1:], 50.0, atol=0.006)


def test_kanagawa_empty_member_is_no_data(kanagawa, http_server, tmp_path):
    """An empty .lem member is no data, never an error: the sheet is composed from the older survey."""
    code = "09NC1222"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{code.lower()}_0.5g.csv", "測量年,2024\r\n".encode("cp932"))
        z.writestr(f"{code.lower()}_0.5g.lem", b"")
    _bucket(http_server, {_kg_key(code): buffer.getvalue(), _kg_key(code, 2019): _lem_zip(code, _kg_codes(2019))})
    cache_dir = str(tmp_path)
    grid = _kg_grid(code)
    _search(kanagawa, grid, cache_dir)
    (path,) = kanagawa.files(grid, cache_dir)
    with rio.open(path) as tile:
        assert np.allclose(tile.read(1), 201.9, atol=0.006)
    assert [y for _, y, _ in gave_pixels(path)] == [2019]


@pytest.mark.parametrize("fuller", ["01", "02"])
def test_kanagawa_one_year_fuller_first(kanagawa, http_server, tmp_path, fuller):
    """The two folders of 2020 are one year: their files go the fuller first (SheetSetFile), whichever folder it is
    in, the other filling its holes; KG_FOLDERS' order of 02 before 01 decides nothing."""
    code = "09NC1222"
    other = "02" if fuller == "01" else "01"
    objects = {_kg_key(code, 2020, fuller): _lem_zip(code, _kg_codes(4000 + int(fuller), slice(0, 10))),
               _kg_key(code, 2020, other): _lem_zip(code, _kg_codes(4000 + int(other), slice(20, None)))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _kg_grid(code)
    _search(kanagawa, grid, cache_dir)
    (path,) = kanagawa.files(grid, cache_dir)
    with rio.open(path) as tile:
        values = tile.read(1)
    assert np.allclose(values[:10], 400.0 + int(other) / 10, atol=0.006)  # the fuller's hole, filled by the other
    assert np.allclose(values[10:], 400.0 + int(fuller) / 10, atol=0.006)
    assert [p for _, _, p in gave_pixels(path)] == [1490 * 2000, 10 * 2000]


def test_kanagawa_folders_newest_first(kanagawa, http_server, tmp_path):
    """09NC1222 in 2024 with a hole (rows 0-99 outside its survey) and in 2019 (whole): 2024 first, 2019 only for the
    hole; 09NC1224 in 2024 whole: 2019 never downloaded; 09NC1311 in 2021 (rows 0-9 only), 2020/02 (whole) and 2020/01
    (rows 0-19): 2021 first, then within 2020 the fuller (2020/02) fills and 2020/01 gives nothing; 2022/02's 1 m grid
    is never listed. A sheet not listed (09NC1313) is never asked; the estimate counts each sheet's newest files."""
    a, b, c = "09NC1222", "09NC1224", "09NC1311"
    objects = {
        _kg_key(a, 2024): _lem_zip(a, _kg_codes(2024, slice(0, 100))),
        _kg_key(a, 2019): _lem_zip(a, _kg_codes(2019)),
        _kg_key(b, 2024): _lem_zip(b, _kg_codes(3024)),
        _kg_key(b, 2019): _lem_zip(b, _kg_codes(3019)),
        _kg_key(c, 2021): _lem_zip(c, _kg_codes(4021, slice(10, None))),
        _kg_key(c, 2020, "01"): _lem_zip(c, _kg_codes(4201, slice(20, None))),
        _kg_key(c, 2020, "02"): _lem_zip(c, _kg_codes(4202)),
        _kg_key(c, 2022, "02"): b"the 1 m grid",
    }
    _bucket(http_server, objects)
    ia, ja = japan.jp_quad_cell(9, a)
    assert japan.jp_quad_cell(9, b) == (ia, ja - 1) and japan.jp_quad_cell(9, c) == (ia + 1, ja)
    grid = make_grid((ia * 1000 + 1, (ja - 1) * 750 + 1, (ia + 2) * 1000 - 1, (ja + 1) * 750 - 1), 1.0, japan.KG_CRS)
    cache_dir = str(tmp_path)
    tiles, todo, mb = kanagawa.estimate(grid, cache_dir, None)
    newest = len(objects[_kg_key(a, 2024)]) + len(objects[_kg_key(b, 2024)]) + len(objects[_kg_key(c, 2021)])
    assert tiles == todo == 3 and mb == pytest.approx(newest / 1e6)
    _search(kanagawa, grid, cache_dir)
    by_code = {os.path.basename(p).split("_")[1]: p for p in kanagawa.files(grid, cache_dir)}
    assert sorted(by_code) == [a, b, c]
    with rio.open(by_code[a]) as tile:
        values = tile.read(1)
    assert np.allclose(values[:100], 201.9, atol=0.006) and np.allclose(values[100:], 202.4, atol=0.006)
    with rio.open(by_code[b]) as tile:
        assert np.allclose(tile.read(1), 302.4, atol=0.006)
    with rio.open(by_code[c]) as tile:
        values = tile.read(1)
    assert np.allclose(values[:10], 402.1, atol=0.006) and np.allclose(values[10:], 420.2, atol=0.006)
    assert [(n.split("@")[0], y, p) for n, y, p in gave_pixels(by_code[c])] == \
        [("2021_09NC1311", 2021, 10 * 2000), ("2020_09NC1311", 2020, 1490 * 2000)]
    asked = {r.path.lstrip("/") for r in http_server.requests() if r.path.endswith(".zip")}
    assert asked == {_kg_key(a, 2024), _kg_key(a, 2019), _kg_key(b, 2024), _kg_key(c, 2021), _kg_key(c, 2020, "01"),
                     _kg_key(c, 2020, "02")}
    prefixes = {dict(r.query).get("prefix") for r in http_server.requests() if r.path == "/"}
    assert all(p == "" or p.startswith(("2024/01/LP/Grid/MESH/09/", "2022/01/", "2021/01/", "2020/02/", "2020/01/",
                                        "2019/01/")) for p in prefixes)
    assert kanagawa.used(grid, cache_dir)["survey_years"] == [2019, 2024]


def test_kanagawa_catalogue_entry():
    """The catalogue's own settings: region jp-14, zone IX, the MESH grid's .lem members of kanagawa-pointcloud, two
    connections at once, the credit with the records' line, no surface model; neighbours on both sides (at most six
    each, the country layer's most)."""
    source = src.SOURCES["kanagawa"]
    assert source.regions == ("jp-14",) and source.countries == ("jp",) and source.crs == "EPSG:6677"
    assert source.nmt is japan.KG_DTM and source.nmpt is None and source.credits == (japan.KG_CREDIT,)
    assert japan.KG_DTM.bucket == japan.KG_DTM.index.listing.url == \
        "https://kanagawa-pointcloud.s3.ap-northeast-1.amazonaws.com"
    assert japan.KG_DTM.folders_pattern == r"\d{4}/" and japan.KG_DTM.prefixes is japan.kg_prefixes
    assert japan.KG_DTM.parse is japan.kg_key and japan.KG_DTM.members == r"\.lem$"
    assert japan.KG_DTM.reader.sheet.members == r"\.lem$" and japan.KG_DTM.reader.sheet.listed
    assert set(japan.KG_DTM.levels) == {"q"} and japan.KG_DTM.levels["q"].cell == japan.SHEET_QUAD
    assert (japan.KG_DTM.folder, japan.KG_DTM.index.prefix, japan.KG_DTM.index.top) == \
        ("kanagawa/grid-mesh", "grid-mesh", "kanagawa")
    assert japan.KG_DTM.native_res == 0.5 and japan.KG_DTM.bytes_per_tile() == 1.72e6
    assert japan.KG_DTM.credit is japan.KG_CREDIT and not japan.KG_DTM.credits_by_pixels
    assert "データ提供：（神奈川県環境農政局緑政部森林再生課）" in japan.KG_CREDIT.attribution
    assert japan.KG_CREDIT.licence == "CC BY 4.0" and japan.KG_RECORDS in japan.KG_CREDIT.notice
    # the conditions quoted stand on the records of 2019-2022, not on the 2024 record (its `restriction` is empty)
    assert japan.KG_RECORDS.endswith("kanagawa-2019-pointcloud")
    assert f"(the 2024 record, {japan.KG_RECORD_2024}, states none)" in japan.KG_CREDIT.notice
    assert src.net.HOST_SLOTS_OF["kanagawa-pointcloud.s3.ap-northeast-1.amazonaws.com"] == 2
    assert source.neighbours == ("tokyo", "shizuoka", "yamanashi")
    for other in source.neighbours:
        assert "kanagawa" in src.SOURCES[other].neighbours, other
    assert all(len(s.neighbours) <= 6 for s in src.SOURCES.values())
    assert source.sample == (35.1317, 139.6232) and source.border_boxes == japan.KG_BORDER_BOXES
    assert src.SOURCES["tokyo"].border_boxes == japan.TK_BORDER_BOXES and len(japan.TK_BORDER_BOXES) == 2


def test_kanagawa_offline_boxes():
    """Kanagawa's offline boxes (region jp-14) come first among the Japanese sources (Tokyo's and Shizuoka's boxes
    hold some of its land, Yamanashi's 13 km² of it) and keep off the neighbours' land: of the coverage map's outlines
    they hold most of jp-14 and little of jp-13, jp-19 and jp-22; Kanagawa's places choose jp-14 offline and one
    point on each neighbour's side next to its boxes keeps its own choice."""
    import json
    from shapely.geometry import box, shape
    from shapely.ops import unary_union
    from sources import choose
    source = src.SOURCES["kanagawa"]
    assert all(region == "jp-14" for region, _ in source.offline) and source.offline == japan.KG_BOXES
    order = list(src.SOURCES)
    assert order.index("kanagawa") < order.index("yamanashi") < order.index("tokyo") < order.index("shizuoka")
    with open(os.path.join(os.path.dirname(HERE), "viewer", "src", "coverage", "shapes.json"), encoding="utf-8") as f:
        outlines = {x["properties"]["id"]: shape(x["geometry"]) for x in json.load(f)["features"]
                    if x["properties"]["id"] in ("jp-13", "jp-14", "jp-19", "jp-22")}
    ours = unary_union([box(w, s, e, n) for _, (s, n, w, e) in source.offline])
    km2 = {k: g.intersection(ours).area * 111.32 ** 2 * math.cos(math.radians(35.3)) for k, g in outlines.items()}
    # measured 2026-11-27 (the boxes of the cells): a box grown or moved by a cell (about 5 km²) changes one of them
    assert km2 == {"jp-14": pytest.approx(2281.68, abs=1.0), "jp-13": pytest.approx(29.63, abs=1.0),
                   "jp-19": pytest.approx(10.72, abs=1.0), "jp-22": pytest.approx(9.32, abs=1.0)}, km2

    def offline(lat, lon):
        return next((region for region, (s, n, w, e) in choose.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e),
                    None)
    # Makuiwa, Tanzawa (Hirugatake), Jogashima, Sagamiko, Yokohama's Kanazawa, Machida's south-east edge (Kanagawa's
    # land inside Tokyo's box (35.48, 35.55, 139.42, 139.86))
    for lat, lon in ((35.1532, 139.0856), (35.4605, 139.1595), (35.1340, 139.6200), (35.6120, 139.1800),
                     (35.3400, 139.6200), (35.5200, 139.5000)):
        assert offline(lat, lon) == "jp-14", (lat, lon)
    # the neighbours' side next to Kanagawa's boxes: Tokyo (Machida, Hachioji), Yamanashi (Doshi), Shizuoka (Atami)
    for lat, lon, code in ((35.5700, 139.4300, "jp-13"), (35.6600, 139.3000, "jp-13"),
                           (35.4800, 138.9500, "jp-19"), (35.0950, 139.0700, "jp-22")):
        assert offline(lat, lon) == code, (lat, lon, offline(lat, lon))


def test_tokyo_gap_filled_from_kanagawa_as_a_seam(kanagawa, http_server, tmp_path):
    """The neighbour fill of the catalogue's new pair: a Tokyo grid (zone IX) by the Kanagawa border at Machida,
    two quadrant sheets wide, with no data in its eastern half gets Kanagawa's sheet there (its listing and its .lem
    on the local bucket), counted as Kanagawa's and kept in the joined mask (a seam), never filled; its own data
    stay."""
    from rasterio.warp import transform
    from shapely.geometry import box
    assert "kanagawa" in src.SOURCES["tokyo"].neighbours and "tokyo" in src.SOURCES["kanagawa"].neighbours
    xs, ys = transform("EPSG:4326", japan.KG_CRS, [139.40], [35.53])
    i, j = int(xs[0] // 1000), int(ys[0] // 750)
    grid = make_grid((i * 1000, j * 750, (i + 2) * 1000, (j + 1) * 750), 1.0, japan.KG_CRS)
    grid.area_shape = box(*grid.bounds)
    elevation = np.full((grid.height, grid.width), 100.0, np.float32)
    elevation[:, grid.width // 2:] = np.nan
    path = str(tmp_path / "nmt.npy")
    np.save(path, elevation)
    code = japan.jp_quad_sheet(9, i + 1, j)
    _bucket(http_server, {_kg_key(code, 2020, "02"): _lem_zip(code, _kg_codes(1200))})
    src.mosaic.used_data.clear()
    try:
        out = str(tmp_path / "joined.npy")
        joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [src.SOURCES["kanagawa"]],
                                                               str(tmp_path / "cache"), out)
        result = np.load(path)
        assert joined_path == out and [(s.id, n) for s, n in counts] == [("kanagawa", 1000 * 750)]
        assert np.allclose(result[:, 1000:], 120.0, atol=0.006) and np.allclose(result[:, :1000], 100.0)
        joined = np.load(out)
        assert joined[:, 1000:].all() and not joined[:, :1000].any()
        assert any(u.get("credit", {}).get("data") == japan.KG_CREDIT.data for u in src.mosaic.used_data)
        assert not np.isnan(result).any()
    finally:
        src.mosaic.used_data.clear()


@pytest.mark.parametrize("code", ["09MC9132", "09MD5023"])
def test_check_source_reads_a_lem_sheet(code):
    """tools/check_source.py's own reader of a .lem sheet (placed by its CSV header's corners, not the code) gives the
    app's parser's heights on the sheet's pixels, for both recorded sheets."""
    import check_source as cs
    from sources.readers.sheetfile import _lem_grid
    data = _kg_recorded(code)
    left, bottom, right, top = japan.KG_LEVELS["q"].edges(japan.jp_quad_cell(9, code))
    profile = {"crs": japan.KG_CRS, "transform": from_origin(left, top, 0.5, 0.5), "width": 2000, "height": 1500}
    values = cs._lem_values(data, profile)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        heights = _lem_grid(z.read(f"{code.lower()}_0.5g.lem"), (1500, 2000))
    assert np.array_equal(np.isnan(values), np.isnan(heights)) and np.allclose(values, heights, equal_nan=True)


def _lem_variant(code, drop=None, header=None, lem=None):
    """A recorded sheet's ZIP with a member left out, its header replaced or its .lem replaced."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_kg_recorded(code))) as source, \
            zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name in source.namelist():
            if drop and name.endswith(drop):
                continue
            data = source.read(name)
            if header is not None and name.endswith(".csv"):
                data = header
            if lem is not None and name.endswith(".lem"):
                data = lem
            out.writestr(name, data)
    return buffer.getvalue()


def test_check_source_lem_broken_is_a_warning(kanagawa, http_server, tmp_path):
    """A .lem sheet check_source cannot read (no .csv member, a header without a corner, a byte that is not ASCII)
    is a RuntimeError of _lem_values, so check_files says WARN with the reason instead of ending in a traceback; the
    recorded sheet itself passes."""
    import check_source as cs
    code = "09MC9132"
    profile = {"crs": japan.KG_CRS, "transform": from_origin(0, 0, 0.5, 0.5), "width": 2000, "height": 1500}
    lem = _lem_text(_kg_codes(500))
    for broken, match in ((_lem_variant(code, drop=".csv"), "no .lem and .csv members"),
                          (_lem_variant(code, header="測量年,2024\r\n".encode("cp932")), "the header has no"),
                          (_lem_variant(code, lem=lem[:20] + b"\xe9" + lem[21:]), "not a .lem sheet")):
        with pytest.raises(RuntimeError, match=match):
            cs._lem_values(broken, profile)
    objects = {_kg_key(code): _kg_recorded(code)}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _kg_grid(code)
    _search(kanagawa, grid, cache_dir)
    assert cs.check_files(kanagawa, grid, cache_dir, 1)["status"] == cs.PASS
    objects[_kg_key(code)] = _lem_variant(code, drop=".csv")  # the source file read again is now broken
    check = cs.check_files(kanagawa, grid, cache_dir, 1)
    assert check["status"] == cs.WARN and "no .lem and .csv members" in check["text"], check["text"]


# --- Miyagi -----------------------------------------------------------------------------------------------------------
MG_RECORDED = os.path.join(HERE, "data", "recorded", "miyagi")


def _mg_recorded(name):
    with open(os.path.join(MG_RECORDED, name), "rb") as f:
        return f.read()


@pytest.fixture
def miyagi(http_server, monkeypatch):
    """The catalogue's Miyagi layer reading its ZIPs from the local server, with the table `table` (code -> folders)."""
    monkeypatch.setattr(japan, "MG_BUCKET", http_server.base)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)

    def use(table):
        monkeypatch.setattr(japan, "_mg_table", lambda: table)
        return japan.MG_DTM
    return use


def _mg_search(layer, grid, cache_dir):
    layer.download(grid, cache_dir, None, "terrain")
    layer.downloaded(grid, cache_dir)


def _mg_grid(code, margin=1.0):
    left, bottom, right, top = japan.MG_DTM.index.edges(japan.jp_quad_cell(10, code))
    return make_grid((left + margin, bottom + margin, right - margin, top - margin), 1.0, japan.MG_CRS)


def _mg_text(code, z, rows=None, flag=1):
    """A sheet's "id,x,y,z,flag" rows as the publisher writes them (cell centres on .5 m, west to east from the
    north-west corner), only the rows given (row numbers from the north; None: all 750)."""
    i, j = japan.jp_quad_cell(10, code)
    left, top = i * 1000, (j + 1) * 750
    lines, n = [], 0
    for r in (range(750) if rows is None else rows):
        y = top - 0.5 - r
        for c in range(1000):
            n += 1
            lines.append(f"{n},{left + 0.5 + c:.2f},{y:.2f},{z:.2f},{flag}")
    return ("\r\n".join(lines) + "\r\n").encode()


def test_miyagi_sheet_codes_and_files():
    """Quadrant sheets of zone X (10PD6721 is x -10 000..-9 000, y -168 750..-168 000: the research's check against a
    real file's points); the files of a sheet come from the shipped table, its region folder in the URL, both folders
    for 10PE0822 (listed twice), none for a code the table lacks (Kinkasan's 10QF3522)."""
    assert japan.jp_quad_cell(10, "10PD6721") == (-10, -225) and japan.jp_quad_sheet(10, -10, -225) == "10PD6721"
    assert japan.MG_DTM.index.edges((-10, -225)) == (-10_000, -168_750, -9_000, -168_000)
    assert japan.jp_quad_cell(9, "10PD6721") is None and japan.jp_quad_cell(10, "10PD6725") is None
    bucket = "https://gic-miyagi.s3.ap-northeast-1.amazonaws.com"
    assert japan.mg_files(-10, -225) == [("01_10PD6721", f"{bucket}/2024/1mcsv/01/10PD6721.zip", 2023)]
    assert japan.mg_files(*japan.jp_quad_cell(10, "10PE0822")) == [
        ("02_10PE0822", f"{bucket}/2024/1mcsv/02/10PE0822.zip", 2023),
        ("03_10PE0822", f"{bucket}/2024/1mcsv/03/10PE0822.zip", 2023)]
    assert japan.mg_files(*japan.jp_quad_cell(10, "10QF3522")) == []


def test_miyagi_table_shipped():
    """The table in the catalogue (tools/miyagi_sheets.py from the portal's list of 2026-11-27): 9 570 sheets in 9 571
    rows, every code a quadrant sheet of zone X, the test places' sheets in their folders."""
    table = japan._mg_table()
    assert len(table) == 9570 and sum(len(f) for f in table.values()) == 9571
    assert table["10PE0822"] == (2, 3) and table["10QD3312"] == (6,) and table["10QE3444"] == (1,)
    assert all(japan.jp_quad_cell(10, code) is not None for code in table)
    assert {f for folders in table.values() for f in folders} == {1, 2, 3, 4, 5, 6, 7}
    assert "10QF3522" not in table  # Kinkasan: in the sheet index, no grid


def test_miyagi_sheets_tool(tmp_path):
    """tools/miyagi_sheets.py on the recorded rows of the portal's list: 10PE0822 in two folders, the table written and
    read back; a re-published list says what it adds, removes and moves; a list with another header, a URL of
    another bucket or a code that is no quadrant sheet of zone X stops it."""
    import miyagi_sheets
    text = _mg_recorded("grid_list_rows.csv").decode("utf-8")
    found = miyagi_sheets.sheets(miyagi_sheets.rows(text))
    assert found["10PE0822"] == {2, 3} and found["10QD3312"] == {6} and len(found) == 5
    out = str(tmp_path / "t.npz")
    miyagi_sheets.save(out, found)
    assert miyagi_sheets.load(out) == found
    assert miyagi_sheets.sheet_url(6, "10QD3312") == f"{miyagi_sheets.BUCKET}/2024/1mcsv/06/10QD3312.zip"
    republished = {**{c: f for c, f in found.items() if c != "10QE3444"}, "10QD3312": {7}, "10QD3313": {6}}
    lines = miyagi_sheets.changes(found, republished)
    assert lines[0].startswith("sheets added: 1 ['10QD3313']") and lines[1].startswith("sheets removed: 1 ['10QE3444']")
    assert lines[2] == "sheets in other folders: 1 [('10QD3312', [6], [7])]"
    with pytest.raises(ValueError, match="not the grid list"):
        miyagi_sheets.rows("a,b,c,d\r\n")
    header = text.splitlines()[0]
    with pytest.raises(ValueError, match="no sheet's address"):
        miyagi_sheets.rows(header + "\r\nt,n,https://example.org/2024/1mcsv/01/10PD6721.zip,1\r\n")
    with pytest.raises(ValueError, match="not a quadrant sheet of zone X"):
        miyagi_sheets.rows(header + f"\r\nt,n,{miyagi_sheets.sheet_url(1, '10PD6725')},1\r\n")
    with pytest.raises(ValueError, match="names no sheet"):
        miyagi_sheets.rows(header + "\r\n")


@pytest.mark.parametrize("code, rows, flagged", [("10QE3444", 183, 0), ("10QE1532", 578, 7)])
def test_miyagi_recorded_sheets(miyagi, http_server, tmp_path, code, rows, flagged):
    """The publisher's small sheets (recorded 2026-11-27): each row a pixel of the 1 m sheet (1000 x 750 px in
    EPSG:6678 on the code's box), the rest no data; the rows flagged -9999 keep their heights (the user's decision of
    2026-11-27: 10QE1532's first row, flagged -9999, at -0.40 m)."""
    data = _mg_recorded(f"{code}.zip")
    layer = miyagi({code: (1,)})
    http_server.add(f"/2024/1mcsv/01/{code}.zip", data, "application/x-zip-compressed")
    cache_dir = str(tmp_path)
    grid = _mg_grid(code)
    _mg_search(layer, grid, cache_dir)
    (path,) = layer.files(grid, cache_dir)
    assert path.replace(os.sep, "/").endswith(f"miyagi/1mcsv/2023/{code[2:4]}/{code[4:6]}/{code}.tif")
    left, bottom, right, top = layer.index.edges(japan.jp_quad_cell(10, code))
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.crs.to_epsg() == 6678 and tile.shape == (750, 1000)
        assert tile.transform.almost_equals(from_origin(left, top, 1.0, 1.0))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        table = np.loadtxt(io.BytesIO(z.read(f"{code.lower()}_1g.txt")), delimiter=",")
    assert len(table) == rows and int((table[:, 4] == -9999).sum()) == flagged
    assert np.count_nonzero(~np.isnan(values)) == rows  # every row, the flagged ones too
    for x, y, z_, flag in table[:, 1:5]:
        assert abs(values[int(top - y), int(x - left)] - z_) < 0.006, (x, y, flag)
    if flagged:
        assert table[0, 4] == -9999 and abs(values[int(top - table[0, 2]), int(table[0, 1] - left)] + 0.40) < 0.006
    _mg_search(layer, grid, cache_dir)
    assert _zips(http_server) == 1  # a second search asks nothing


def test_miyagi_flagged_rows_keep_their_heights(miyagi, http_server, tmp_path):
    """A synthetic sheet whose northern rows are flagged -9999 (the provider's interpolated cells: a lake's level, a
    block without ground): their heights are kept as the others, never no data."""
    code = "10QD3312"
    layer = miyagi({code: (6,)})
    text = _mg_text(code, 945.2, range(0, 20), flag=-9999) + _mg_text(code, 900.0, range(20, 750))
    http_server.add(f"/2024/1mcsv/06/{code}.zip", _zip(f"{code.lower()}_1g.txt", text), "application/x-zip-compressed")
    cache_dir = str(tmp_path)
    grid = _mg_grid(code)
    _mg_search(layer, grid, cache_dir)
    (path,) = layer.files(grid, cache_dir)
    with rio.open(path) as tile:
        values = tile.read(1)
    assert np.allclose(values[:20], 945.2, atol=0.006) and np.allclose(values[20:], 900.0, atol=0.006)


def test_miyagi_two_files_and_missing_keys(miyagi, http_server, tmp_path):
    """10PE0822 listed in two folders: both read, the fuller first, the other filling its holes; a sheet the table
    lacks is no tile and never asked; a listed key the bucket answers 403 for (its answer to a missing key) is an error
    of its sheet, nothing recorded, asked again by the next search."""
    code = "10PE0822"
    i, j = japan.jp_quad_cell(10, code)
    absent, broken = japan.jp_quad_sheet(10, i + 1, j), japan.jp_quad_sheet(10, i + 2, j)  # 10PE0911, 10PE0912
    layer = miyagi({code: (2, 3), broken: (1,)})
    http_server.add(f"/2024/1mcsv/02/{code}.zip", _zip(f"{code.lower()}_1g.txt", _mg_text(code, 50.0, range(0, 10))),
                    "application/x-zip-compressed")
    http_server.add(f"/2024/1mcsv/03/{code}.zip", _zip(f"{code.lower()}_1g.txt", _mg_text(code, 60.0, range(5, 750))),
                    "application/x-zip-compressed")
    http_server.add(f"/2024/1mcsv/01/{broken}.zip", b"<Error><Code>AccessDenied</Code></Error>", "application/xml",
                    status=403)
    cache_dir = str(tmp_path)
    grid = make_grid((i * 1000 + 1, j * 750 + 1, (i + 3) * 1000 - 1, (j + 1) * 750 - 1), 1.0, japan.MG_CRS)
    tiles = layer.tiles(grid)
    assert sorted(tiles) == sorted([(i, j), (i + 2, j)])  # the absent sheet is no tile
    layer._download_and_record((i, j), cache_dir)
    with rio.open(layer.tile_path(cache_dir, (i, j))) as tile:
        values = tile.read(1)
    assert np.allclose(values[:5], 50.0, atol=0.006) and np.allclose(values[5:], 60.0, atol=0.006)
    assert [n for n, _, _ in gave_pixels(layer.tile_path(cache_dir, (i, j)))] == ["03_10PE0822", "02_10PE0822"]
    with pytest.raises(RuntimeError, match=broken):
        layer._download_and_record((i + 2, j), cache_dir)
    assert cache.due(cache_dir, layer.tile_path(cache_dir, (i + 2, j)))  # the 403: an error, nothing recorded
    assert len(http_server.requests(f"/2024/1mcsv/01/{broken}.zip")) == 1  # a 403 is not retried
    assert not any(absent in r.path for r in http_server.requests())


def test_miyagi_auto_takes_europe_far_from_sheets(monkeypatch, tmp_path):
    """--source auto in jp-04: a centre within 2 km of a sheet of the table (Banji-iwa, Sendai's station) takes miyagi,
    one farther (Wakabayashi's plain 3.6 km, the Natori plain 2.6 km) europe (instead_without_data, the user's
    decision of 2026-11-27); the table decides, no request is made."""
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "jp")
    monkeypatch.setattr(src.choose, "region_codes", lambda lat, lon, cache_dir, code: ("jp-04",))

    def no_request(*args, **kwargs):
        raise AssertionError("a request")
    monkeypatch.setattr(src.net, "_get", no_request)
    for lat, lon in ((38.2950, 140.5277), (38.2601, 140.8822)):
        assert src.choose_source("auto", lat, lon, str(tmp_path))[0].id == "miyagi", (lat, lon)
    for lat, lon in ((38.2380, 140.9500), (38.1700, 140.8900)):
        assert src.choose_source("auto", lat, lon, str(tmp_path)) == (
            src.SOURCES["europe"], "the centre is in JP-04, but miyagi has no terrain data near it"), (lat, lon)
    assert japan.MG_DTM.has_data_near(38.2380, 140.9500, str(tmp_path)) is False
    assert japan.MG_DTM.index.has_data_near(38.2380, 140.9500, str(tmp_path), metres=4000) is True


def test_miyagi_catalogue_entry():
    """The catalogue's own settings: region jp-04, zone X, the 1 m grid's text members from the prefecture's bucket by
    the shipped table, two connections at once (the portal too), the credit with the portal's three items and the
    approval sentence, no surface model, no neighbours, europe where no sheet lies near."""
    source = src.SOURCES["miyagi"]
    assert source.regions == ("jp-04",) and source.countries == ("jp",) and source.crs == "EPSG:6678"
    assert source.nmt is japan.MG_DTM and source.nmpt is None and source.credits == (japan.MG_CREDIT,)
    assert source.neighbours == () and source.border_boxes == () and source.instead_without_data == "europe"
    assert source.default_resolution == 1.0 and japan.MG_DTM.native_res == 1.0
    assert japan.MG_DTM.folder == "miyagi/1mcsv/2023" and japan.MG_DTM.members == r"\.txt$"
    assert japan.MG_DTM.reader.sheet.listed and japan.MG_DTM.index.cell == japan.SHEET_QUAD
    assert japan.MG_DTM.bytes_per_tile() == 5.1e6
    assert japan.MG_BUCKET == "https://gic-miyagi.s3.ap-northeast-1.amazonaws.com"
    for text in ("宮城県", "【宮城県】3次元点群データ_データ一覧_グリッドデータ_CSV_2023", japan.MG_RESOURCE,
                 "測量法に基づく国土地理院長承認（使用）R6JHs966"):
        assert text in japan.MG_CREDIT.attribution, text
    assert japan.MG_TERMS in japan.MG_CREDIT.notice and japan.MG_CREDIT.licence == "CC BY 4.0"
    assert src.net.HOST_SLOTS_OF["gic-miyagi.s3.ap-northeast-1.amazonaws.com"] == 2
    assert src.net.HOST_SLOTS_OF["miyagi.dataeye.jp"] == 2
    assert source.sample == (38.2955, 140.5330) and japan.MG_DTM.has_data_near(*source.sample, "") is True


def test_miyagi_offline_boxes():
    """Miyagi's offline boxes (region jp-04) hold its places and keep off its neighbours' (no source there: their
    points choose no Japanese source offline)."""
    from sources import choose
    source = src.SOURCES["miyagi"]
    assert all(region == "jp-04" for region, _ in source.offline) and source.offline == japan.MG_BOXES

    def offline(lat, lon):
        return next((region for region, (s, n, w, e) in choose.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e),
                    None)
    for lat, lon in ((38.2955, 140.5330), (38.2601, 140.8822), (38.7450, 140.6800), (38.1350, 140.4450)):
        assert offline(lat, lon) == "jp-04", (lat, lon)
    # Yamagata city, Fukushima's Kunimi, Iwate's Ichinoseki: no box
    for lat, lon in ((38.2550, 140.3400), (37.8770, 140.5500), (38.9340, 141.1270)):
        assert offline(lat, lon) is None, (lat, lon)


@pytest.mark.parametrize("code", ["10QE3444", "10QE1532"])
def test_check_source_reads_miyagi_rows(miyagi, http_server, tmp_path, code):
    """tools/check_source.py reads "id,x,y,z,flag" rows by its own rule (GDAL's XYZ driver took id, x, y as the
    columns: "Ungridded dataset"): every row in the pixel holding it, the flagged ones too, equal to the tile the
    layer cached; a text of four columns is a RuntimeError (check_files' WARN line)."""
    import check_source as cs
    data = _mg_recorded(f"{code}.zip")
    layer = miyagi({code: (1,)})
    http_server.add(f"/2024/1mcsv/01/{code}.zip", data, "application/x-zip-compressed")
    cache_dir = str(tmp_path)
    grid = _mg_grid(code)
    _mg_search(layer, grid, cache_dir)
    check = cs.check_files(layer, grid, cache_dir, 1)
    assert check["status"] == cs.PASS and check["tiles"][0]["max_abs_m"] <= 0.006, check["text"]
    left, bottom, right, top = layer.index.edges(japan.jp_quad_cell(10, code))
    profile = {"crs": japan.MG_CRS, "transform": from_origin(left, top, 1.0, 1.0), "width": 1000, "height": 750}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(f"{code.lower()}_1g.txt")
    with rio.open(layer.tile_path(cache_dir, japan.jp_quad_cell(10, code))) as tile:
        cached = tile.read(1)
    values = cs._csv_values(text, profile)
    assert np.array_equal(np.isnan(values), np.isnan(cached)) and np.allclose(values, cached, atol=0.006,
                                                                               equal_nan=True)
    with pytest.raises(RuntimeError, match="5 expected"):
        cs._csv_values(b"1,2.5,3.5,4\r\n2,3.5,3.5,4\r\n", profile)


def test_check_source_reads_an_xyz_sheet_once(miyagi, http_server, tmp_path):
    """check_source's text branch on a sheet of "x y z" lines (Shizuoka's kind) reads it through GDAL's XYZ driver
    from the bytes it downloaded: one request to the ZIP, under the host's slot, and the cached tile equals it."""
    import check_source as cs
    code = "10QD3312"
    layer = miyagi({code: (6,)})
    i, j = japan.jp_quad_cell(10, code)
    left, top = i * 1000, (j + 1) * 750
    lines = [f"{left + 0.5 + c:.3f} {top - 0.5 - r:.3f} {900 + r + c / 1000:.3f}"
             for r in range(10) for c in range(1000)]
    text = ("\r\n".join(lines) + "\r\n").encode()
    http_server.add(f"/2024/1mcsv/06/{code}.zip", _zip(f"{code.lower()}_1g.txt", text), "application/x-zip-compressed")
    cache_dir = str(tmp_path)
    grid = _mg_grid(code)
    _mg_search(layer, grid, cache_dir)
    before = len(http_server.requests(f"/2024/1mcsv/06/{code}.zip"))
    slots, host_slot = [], src.net.host_slot

    import contextlib

    @contextlib.contextmanager
    def counted(cache, url):
        with host_slot(cache, url):
            slots.append(url)  # held while the request runs
            yield
    import unittest.mock
    with unittest.mock.patch.object(src.net, "host_slot", counted):
        check = cs.check_files(layer, grid, cache_dir, 1)
    assert len(http_server.requests(f"/2024/1mcsv/06/{code}.zip")) == before + 1  # one download, no second by GDAL
    assert [u.rsplit("/", 3)[-2:] for u in slots] == [["06", f"{code}.zip"]]  # under the host's slot
    assert check["status"] == cs.PASS and check["tiles"][0]["max_abs_m"] <= 0.006, check["text"]


def test_check_source_composes_a_sheet_of_two_files(miyagi, http_server, tmp_path):
    """A sheet of two files (10PE0822 in folders 02 and 03): check_source composes them as the layer does (the fuller
    first, the other filling its holes), so the cached tile passes; compared with one file it would differ by 10 m."""
    import check_source as cs
    code = "10PE0822"
    layer = miyagi({code: (2, 3)})
    http_server.add(f"/2024/1mcsv/02/{code}.zip", _zip(f"{code.lower()}_1g.txt", _mg_text(code, 50.0, range(0, 10))),
                    "application/x-zip-compressed")
    http_server.add(f"/2024/1mcsv/03/{code}.zip", _zip(f"{code.lower()}_1g.txt", _mg_text(code, 60.0, range(5, 750))),
                    "application/x-zip-compressed")
    cache_dir = str(tmp_path)
    grid = _mg_grid(code)
    _mg_search(layer, grid, cache_dir)
    check = cs.check_files(layer, grid, cache_dir, 1)
    assert check["status"] == cs.PASS and check["tiles"][0]["max_abs_m"] <= 0.006, check["text"]
    assert "02/10PE0822.zip + " in check["tiles"][0]["file"] and check["tiles"][0]["file"].endswith("03/10PE0822.zip")
    assert cs._sheet_files(src.SOURCES["tokyo"].nmt, japan.jp_cell(9, "09KD8388")) == [
        (f"{japan.TK_BUCKET}/2024/dig/grd50/09KD8388.zip", 2024),
        (f"{japan.TK_BUCKET}/2023/dig/grd50/09KD8388.zip", 2023)]
    assert cs._sheet_files(src.SOURCES["czechia"].nmt, None) == []
