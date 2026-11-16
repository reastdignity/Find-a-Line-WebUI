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
                                f"{modified.get(k, '2026-11-04T07:00:00.000Z')}</LastModified><ETag>&quot;{abs(hash(objects[k])) % 10 ** 12:012x}&quot;</ETag>"
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
