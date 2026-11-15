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


def test_shizuoka_one_key_whichever_items():
    """A sheet's sets do not depend on the items seen: a 1/500 sheet of FY2021 and FY2025 is split at FY2022 with
    or without the quadrant sheet over it among the items; a file listed twice (two tiles' answers, uploaded again
    in between) is taken from its newer upload, in either order."""
    versions = japan.SZ_DTM.index.versions
    quad = japan.jp_quad_cell(8, "08LD3341")
    left, _, _, top = japan.SZ_LEVELS["q"].edges(quad)
    small = japan.SZ_LEVELS["s"].cell_of(left + 450, top - 150)

    def item(year, level, cell, etag="aaaaaaaa", modified="2026-11-04T00:00:00.000Z", listed=""):
        return {"name": f"{year}_x{cell}@{etag}", "url": f"u/{year}/{level}/{cell}", "level": level,
                "cell": list(cell), "year": year, "size": 1, "modified": modified, "listed": listed}
    own = [item(2021, "s", small), item(2025, "s", small)]
    alone = [(s.level, s.key) for s in versions.sets(own) if s.level == "s"]
    with_quad = [(s.level, s.key) for s in versions.sets(own + [item(2022, "q", quad)]) if s.level == "s"]
    assert alone == with_quad and len(alone) == 2
    old = item(2019, "s", small, "11111111", "2026-11-04T00:00:00.000Z", "2026-11-05T00:00:00+00:00")
    new = item(2019, "s", small, "22222222", "2026-11-10T00:00:00.000Z", "2026-11-01T00:00:00+00:00")
    assert versions.sets([old, new])[0].files[0][0].endswith("@22222222")
    assert versions.sets([new, old])[0].files[0][0].endswith("@22222222")


def _straddling_sheet():
    """A 1/500 sheet of zone VIII across the 0.25 degree line at 139.0 E (about 34.88 N), and the x of that line."""
    from rasterio.warp import transform
    xs, ys = transform("EPSG:4326", japan.SZ_CRS, [139.0], [34.88])
    cell = japan.SZ_LEVELS["s"].cell_of(xs[0], ys[0])
    xl, _ = transform("EPSG:4326", japan.SZ_CRS, [139.0, 139.0], [34.87, 34.89])
    return cell, sum(xl) / 2


def test_shizuoka_straddling_sheet_one_key_by_turns(shizuoka, http_server, tmp_path):
    """A sheet across two index tiles: a search on either side reads both tiles' answers, so after a re-upload
    seen by one tile's newer answer both searches take the newer file; searches by turns download it once, and
    the older version (the same file name) is pruned, never the current one."""
    cell, line_x = _straddling_sheet()
    code = japan.jp_sheet(8, *cell)
    key = f"2019/LP/Grid/08/{code[2:4]}/{code[4:6]}/{code}.zip"
    objects = {key: _zip(f"{code}_DEM.txt", _sheet_text(code, 10.0))}
    modified = {key: "2026-11-04T07:00:00.000Z"}
    _bucket(http_server, objects, modified)
    left, bottom, right, top = japan.SZ_LEVELS["s"].edges(cell)
    assert left + 20 < line_x < right - 20
    west = make_grid((left + 2, bottom + 50, line_x - 5, top - 50), 0.5, japan.SZ_CRS)
    east = make_grid((line_x + 5, bottom + 50, right - 2, top - 50), 0.5, japan.SZ_CRS)
    cache_dir = str(tmp_path)

    def zips():
        return len([r for r in http_server.requests() if r.path.endswith(".zip")])
    shizuoka.download(west, cache_dir, None, "terrain")
    shizuoka.downloaded(west, cache_dir)
    assert zips() == 1
    shizuoka.index._listed.clear()
    shizuoka.download(east, cache_dir, None, "terrain")
    assert zips() == 1  # the second search downloads nothing
    # uploaded again in place; only the east tile's answer is asked again
    objects[key] = _zip(f"{code}_DEM.txt", _sheet_text(code, 11.0))
    modified[key] = "2026-11-10T07:00:00.000Z"
    from rasterio.warp import transform_bounds
    w, s, e, n = transform_bounds(japan.SZ_CRS, "EPSG:4326", line_x + 5, bottom, right, top)
    east_tile = shizuoka.index.index_path(cache_dir, math.floor(s / 0.25) * 0.25, math.floor(w / 0.25) * 0.25)
    cache.forget(cache_dir, [east_tile])
    for grid in (east, west, east):
        shizuoka.index._listed.clear()
        shizuoka.download(grid, cache_dir, None, "terrain")
        shizuoka.downloaded(grid, cache_dir)
    assert zips() == 2  # the newer file once, whichever side asks
    (path,) = shizuoka.files(west, cache_dir)
    with rio.open(path) as tile:
        assert np.allclose(tile.read(1), 11.0, atol=0.006)
    folder = os.path.dirname(path)
    assert [f for f in os.listdir(folder) if code in f] == [os.path.basename(path)]


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


def test_shizuoka_listed_404_drops_the_index_answers(shizuoka, http_server, tmp_path):
    """A listed key gone from the bucket: the sheet's error says the index answers of its tiles were dropped,
    and the next search lists them again (and no longer asks for the file)."""
    k85, k86 = "2019/LP/Grid/08/OF/04/08OF0485.zip", "2019/LP/Grid/08/OF/04/08OF0486.zip"
    objects = {k85: _zip("08OF0485_DEM.txt", _sheet_text("08OF0485", 10.0)),
               k86: _zip("08OF0486_DEM.txt", _sheet_text("08OF0486", 12.0))}
    _bucket(http_server, objects)
    cache_dir = str(tmp_path)
    grid = _sheet_grid("08OF0485")
    shizuoka._use(cache_dir)
    (sheet,) = shizuoka.tiles(grid)
    answers = glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "lp-grid", "*.json"))
    assert [os.path.basename(a) for a in answers if a.endswith("folders.json")] and len(answers) >= 2
    del objects[k85]
    with pytest.raises(RuntimeError, match="index answers of its 1 tile.*dropped"):
        shizuoka._download_and_record(sheet, cache_dir)
    assert not [a for a in glob.glob(os.path.join(cache_dir, "shizuoka", "sheet-index", "lp-grid", "*.json"))
                if not a.endswith("folders.json")]
    lists = len([r for r in http_server.requests("/") if dict(r.query).get("list-type")])
    shizuoka.index._listed.clear()
    assert shizuoka.tiles(grid) == []
    assert len([r for r in http_server.requests("/") if dict(r.query).get("list-type")]) > lists


def test_shizuoka_survey_folders_kept_a_week(shizuoka, http_server, tmp_path, monkeypatch):
    """The survey folders are one delimiter listing kept in the data folder for FOLDERS_TTL_DAYS: asked once
    while fresh, again when stale."""
    from sources.layers import s3sheets
    objects = {"2019/LP/Grid/08/OF/04/08OF0485.zip": b"x"}
    _bucket(http_server, objects)
    shizuoka._use(str(tmp_path))

    def delimited():
        return len([r for r in http_server.requests("/") if dict(r.query).get("delimiter") == "/"])
    assert shizuoka.survey_folders() == ["2019/"] and delimited() == 1
    objects["2026/LP/Grid/08/OF/04/08OF0485.zip"] = b"y"
    assert shizuoka.survey_folders() == ["2019/"] and delimited() == 1
    monkeypatch.setattr(s3sheets, "FOLDERS_TTL_DAYS", -1)
    assert shizuoka.survey_folders() == ["2019/", "2026/"] and delimited() == 2


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
