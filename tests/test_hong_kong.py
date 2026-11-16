"""Hong Kong (sources/catalogue/hong_kong.py): the 1:1000 sheets of the Hong Kong 1980 Grid against real rows of the
CSDI Portal's index, the static table of its sheets (tools/hong_kong_sheets.py: the index checked row by row), the
catalogue's layers on a recorded sheet (CellSheetTiles: a sheet outside the table is never asked, a 404 of a sheet in
it is an error of its tile), the mosaic of a grid across four sheets and the choice of the source by Nominatim's
recorded answers.

Recorded files (2026-11-16): tests/data/recorded/hong_kong/sheets.json, rows of the index as the tool keeps them
(code, file name, URL, footprint in EPSG:2326): 23 of DTM_2020 (one on each map with terrain sheets, the test places,
map 17's whose kilometre pairs are not those of their boxes) and 4 of DSM_2020 (map 1 has surface sheets only);
tests/data/recorded/hong_kong/2NE20D_dtm.head.bin and .tail.bin, the TIFF of the terrain sheet on the Shenzhen River
without its pixels: the bytes before its first tile and after its last (the IFD and the GeoTIFF keys at the end), as
published (EPSG:2326, 0.5 m, nodata -9999, 120 tiles of 128 x 128 float32, uncompressed, in order from byte 1214), so
the tests build the published file around pixels of their own and no height of CEDD's is kept here;
tests/data/recorded/nominatim/reverse-hong-kong.json, Nominatim's reverse answers at zoom 3 and 8 of Lion Rock, Chek
Lap Kok and Tung Lung Chau."""

import io
import json
import math
import os
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import cache  # noqa: E402
import osm  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from sources.catalogue import hong_kong as hk  # noqa: E402
from tile_values import TILE_EPS  # noqa: E402

RECORDED = os.path.join(HERE, "data", "recorded", "hong_kong")
REVERSE = os.path.join(HERE, "data", "recorded", "nominatim", "reverse-hong-kong.json")
BORDER = ("2NE20D", "2NE20D(e829n843,e830n843).zip")  # the recorded sheet (terrain)
LION_ROCK = (22.352, 114.187)
TUNG_LUNG_CHAU = (22.25, 114.29)
CHEK_LAP_KOK = (22.308, 113.918)


def _rows(layer):
    with open(os.path.join(RECORDED, "sheets.json"), encoding="utf-8") as f:
        return [tuple(r) for r in json.load(f)[layer]]


def _published_tif(values: np.ndarray) -> bytes:
    """The recorded sheet's TIFF as CEDD publishes it (its recorded bytes around the tiles) with these pixels
    (1200 x 1500 float32): 10 x 12 tiles of 128 x 128, row by row, the last row and column padded."""
    with open(os.path.join(RECORDED, "2NE20D_dtm.head.bin"), "rb") as f:
        head = f.read()
    with open(os.path.join(RECORDED, "2NE20D_dtm.tail.bin"), "rb") as f:
        tail = f.read()
    padded = np.full((1280, 1536), -9999.0, dtype="<f4")
    padded[:1200, :1500] = values
    tiles = padded.reshape(10, 128, 12, 128).transpose(0, 2, 1, 3)
    assert len(head) == 1214
    return head + tiles.tobytes() + tail


def _zipped(member: str, data: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, data)
    return out.getvalue()


def _border_pixels() -> np.ndarray:
    """Heights of our own for the border sheet: a slope rising east and south, -9999 in the north-west (Shenzhen,
    beyond the river, as the published sheet has it: no data)."""
    rows, cols = np.mgrid[0:1200, 0:1500]
    values = (2.0 + cols * 0.01 + rows * 0.02).astype(np.float32)
    values[rows + cols < 900] = -9999.0
    return values


def _box(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


# --- the sheet codes ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("layer", ["dtm", "dsm"])
def test_sheet_codes_of_the_index(layer):
    """Real rows of the index, spread over the territory (every map from 1 to 17): code -> cell -> the footprint,
    the cell -> the code, the cached name -> the cell; the tool's check takes them all."""
    import hong_kong_sheets as tool
    rows = _rows(layer)
    assert len(rows) >= (10 if layer == "dtm" else 4)
    for code, name, url, ring in rows:
        cell = hk.hk_cell(code)
        assert cell is not None, code
        assert hk.HK_DTM.index.edges(cell) == pytest.approx(_box(ring), abs=0.01), code
        assert hk.hk_sheet(*cell) == code
        assert hk.hk_cell_of_name(hk.hk_name(code)) == cell
        assert name.startswith(f"{code}(") and url == f"{hk.HK_BULK}/{hk.HK_FOLDERS[layer]}/{name}"
    assert set(tool.check(layer, rows)) == {r[0] for r in rows}
    maps = {int(hk._HK_CODE.fullmatch(r[0]).group(1)) for r in _rows("dtm") + _rows("dsm")}
    assert maps == set(range(1, 18))


def test_codes_outside_the_scheme():
    """Off the 17 maps there is no sheet; a code with a block 0 or above 25, a leading zero, an unknown map or
    quarter is none."""
    assert hk.hk_sheet(-1, 0) is None              # west of map 13
    assert hk.hk_sheet(80, 0) is None              # east of map 16: no map 18
    assert hk.hk_sheet(0, 80) is None              # north of map 1
    assert hk.hk_sheet(80, 60) == "17SW21C"        # map 17, east of map 4
    for code in ("7SW05C", "7SW0C", "7SW26A", "18NW1A", "0NW1A", "7XW1A", "7SW1E", "7sw1a", "7SW25C "):
        assert hk.hk_cell(code) is None, code
    assert hk.hk_name(None) is None and hk.hk_cell_of_name("7SE/7SW25C") is None
    assert hk.hk_name("7SW25C") == "7SW/7SW25C"
    # every cell of a map has its own code: 400 per map
    codes = {hk.hk_sheet(i, j) for i in range(40, 60) for j in range(40, 60)}  # map 7
    assert len(codes) == 400 and all(c.startswith("7") for c in codes)


def test_a_grid_ending_on_a_sheet_edge():
    """A grid whose right or top edge lies exactly on a sheet's edge takes no sheet beyond it (7SW25C's box is
    x 836 000-836 750, y 824 000-824 600: a grid ending at 836 750 took 7SW25D before, a download giving no pixel);
    one reaching a metre over it takes the next sheet; a grid starting exactly on an edge starts with that sheet."""
    tiling = hk.HK_DTM.index
    cell = hk.hk_cell("7SW25C")
    left, bottom, right, top = tiling.edges(cell)
    assert (left, bottom, right, top) == (836000, 824000, 836750, 824600)
    names = lambda grid: [hk.hk_sheet(*c) for c in tiling.cells(grid)]  # noqa: E731
    assert names(make_grid((left + 100, bottom + 100, right, top), 1.0, hk.HK_CRS)) == ["7SW25C"]
    assert names(make_grid((left, bottom, right, top), 1.0, hk.HK_CRS)) == ["7SW25C"]
    assert names(make_grid((left + 100, bottom + 100, right + 1, top), 1.0, hk.HK_CRS)) == ["7SW25C", "7SW25D"]
    assert names(make_grid((left + 100, bottom + 100, right, top + 1), 1.0, hk.HK_CRS)) == ["7SW25C", "7SW25A"]
    assert names(make_grid((left - 1, bottom + 100, right, top), 1.0, hk.HK_CRS)) == ["7SW24D", "7SW25C"]


def test_file_names_kept_as_published(monkeypatch):
    """The file names carry the sheet's corners floored to the kilometre, but on map 17 a pair is a kilometre off
    (17NW12A lies at x 861 500, y 845 000 and names e861n844): the URL is the table's name, never computed."""
    rows = {r[0]: r for r in _rows("dtm")}
    code, name, url, ring = rows["17NW12A"]
    left, bottom, right, top = _box(ring)
    assert name != f"{code}(e{int(left) // 1000}n{int(bottom) // 1000},e{int(right) // 1000}n{int(top) // 1000}).zip"
    monkeypatch.setattr(hk, "_hk_table", lambda: {"dtm": {code: name}, "dsm": {}})
    assert hk.hk_files("dtm", *hk.hk_cell(code)) == [(code, url, 2020)]
    assert hk.hk_files("dsm", *hk.hk_cell(code)) == []


def test_tiling_on_the_recorded_header():
    """The layers' cells are the sheets: the recorded file's header (EPSG:2326, 0.5 m, "Area", nodata -9999) lies
    on its cell's box, pixel edges on whole metres (the source's grid_origin 0); the footprints all lie 500 m
    modulo 750 and 200 m modulo 600 east and north, the cells' origin (800 000, 800 000)."""
    values = _border_pixels()
    with MemoryFile(_published_tif(values)) as memfile, memfile.open() as tif:
        assert tif.crs.to_epsg() == 2326 and tif.nodata == -9999 and tif.dtypes == ("float32",)
        assert tif.shape == (1200, 1500) and tif.block_shapes == [(128, 128)] and tif.tags()["AREA_OR_POINT"] == "Area"
        assert tif.profile.get("compress") is None and tif.profile["tiled"]
        assert np.array_equal(tif.read(1), values)  # the tiles where the recorded header says
        transform = tif.transform
    left, bottom, right, top = hk.HK_DTM.index.edges(hk.hk_cell(BORDER[0]))
    assert transform == from_origin(left, top, 0.5, 0.5)
    assert left % 1 == 0 and top % 1 == 0 and src.SOURCES["hong_kong"].grid_origin == (0.0, 0.0)
    for code, name, url, ring in _rows("dtm") + _rows("dsm"):
        x, y, _, _ = _box(ring)
        assert (round(x) % 750, round(y) % 600) == (500, 200)
    assert (hk.HK_LEFT % 750, hk.HK_BOTTOM % 600) == (500, 200)
    assert hk.HK_DTM.index.origin == hk.HK_DSM.index.origin == (hk.HK_LEFT, hk.HK_BOTTOM)


# --- the layers on the local server --------------------------------------------------------------------------------
@pytest.fixture
def hong_kong(http_server, monkeypatch):
    """The catalogue's layers on the local server: the recorded sheet (with our pixels), a sheet of the table the
    local server lacks (404), and a table of those two."""
    http_server.add(f"/2020dtm/{BORDER[1]}", _zipped(BORDER[1].replace(".zip", ".tif"),
                                                     _published_tif(_border_pixels())), "application/zip")
    missing = next(r for r in _rows("dtm") if r[0] == "12SW22A")  # in the table, not on the local server
    monkeypatch.setattr(hk, "HK_BULK", http_server.base)
    monkeypatch.setattr(hk, "_hk_table", lambda: {"dtm": {BORDER[0]: BORDER[1], missing[0]: missing[1]},
                                                  "dsm": {}})
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return hk.HK_DTM


def test_recorded_sheet_lands_on_its_box(hong_kong, tmp_path):
    """The published sheet is written in EPSG:2326 on its box, the land beyond the boundary (-9999) as no data."""
    cell = hk.hk_cell(BORDER[0])
    path = hong_kong.tile_path(str(tmp_path), cell)
    assert path.replace(os.sep, "/").endswith("hong_kong/dtm-2020/2NE/2NE20D.tif")
    assert hong_kong.tile_of("hong_kong/dtm-2020/2NE/2NE20D.tif") == cell
    assert hong_kong.tile_of("hong_kong/dtm-2020/2SE/2NE20D.tif") is None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    assert hong_kong.download_tile(cell, path).received > 0
    expected = _border_pixels()
    expected[expected == -9999.0] = np.nan
    left, bottom, right, top = hong_kong.index.edges(cell)
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 2326 and tile.shape == (1200, 1500)
        assert tile.transform.almost_equals(from_origin(left, top, 0.5, 0.5))
        values = tile.read(1)
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert 0.2 < np.isnan(values).mean() < 0.3                           # Shenzhen beyond the river: no data
    assert np.nanmax(np.abs(values - expected)) <= TILE_EPS


def test_the_table_decides(hong_kong, tmp_path, http_server):
    """A sheet outside the table is no tile and never asked; a 404 for a sheet in it is an error of that tile,
    asked once, never recorded as missing."""
    cell = hk.hk_cell(BORDER[0])
    left, bottom, right, top = hong_kong.index.edges(cell)
    grid = make_grid((left - 100, bottom + 10, right - 10, top - 10), 1.0, hk.HK_CRS)
    assert [hk.hk_sheet(*t) for t in hong_kong.tiles(grid)] == [BORDER[0]]  # its west neighbour is not listed
    west = (cell[0] - 1, cell[1])
    assert hong_kong.tile_url(west) is None and hong_kong.download_tile(west, str(tmp_path / "w.tif")).received == 0
    cache_dir = str(tmp_path / "cache")
    missing = hk.hk_cell("12SW22A")
    with pytest.raises(RuntimeError, match="12SW22A"):
        hong_kong._download_and_record(missing, cache_dir)
    assert cache.due(cache_dir, hong_kong.tile_path(cache_dir, missing))  # nothing recorded
    asked = [r.path for r in http_server.requests()]
    assert asked == ["/2020dtm/12SW22A(e846n812,e847n813).zip"]           # once, and nothing else


def _sheet_zip(code, value, profile):
    """A sheet as CEDD publishes it (the recorded header's profile) holding one height."""
    left, bottom, right, top = hk.HK_DTM.index.edges(hk.hk_cell(code))
    name = f"{code}(e{int(left) // 1000}n{int(bottom) // 1000},e{int(right) // 1000}n{int(top) // 1000})"
    with MemoryFile() as memfile:
        with memfile.open(**{**profile, "transform": from_origin(left, top, 0.5, 0.5)}) as dst:
            dst.write(np.full((1200, 1500), value, dtype=np.float32), 1)
        data = memfile.read()
    return f"{name}.zip", _zipped(f"{name}.tif", data)


def test_a_grid_across_four_sheets(http_server, tmp_path, monkeypatch):
    """Step 1 of a search at Lion Rock's corner of four sheets, terrain and surface: only those eight files asked,
    each sheet's height on its own quarter of a 1 m grid, no gap and no seam between them."""
    with MemoryFile(_published_tif(_border_pixels())) as memfile, memfile.open() as published:
        profile = {k: v for k, v in published.profile.items() if k != "transform"}
    i, j = hk.hk_cell("11NW5B")
    cells = [(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)]
    table = {"dtm": {}, "dsm": {}}
    for layer, offset in (("dtm", 0.0), ("dsm", 5.0)):
        for k, cell in enumerate(cells):
            code = hk.hk_sheet(*cell)
            name, data = _sheet_zip(code, 100.0 + 10 * k + offset, profile)
            http_server.add(f"/{hk.HK_FOLDERS[layer]}/{name}", data, "application/zip")
            table[layer][code] = name
    monkeypatch.setattr(hk, "HK_BULK", http_server.base)
    monkeypatch.setattr(hk, "_hk_table", lambda: table)
    source = src.SOURCES["hong_kong"]
    _, _, x, y = hk.HK_DTM.index.edges((i, j))  # the corner the four sheets share
    grid = make_grid((x - 200, y - 150, x + 200, y + 150), source.default_resolution, source.crs, source.grid_origin)
    cache_dir = str(tmp_path / "cache")
    for layer, label, offset in ((source.nmt, "terrain", 0.0), (source.nmpt, "surface", 5.0)):
        assert layer.estimate(grid, cache_dir, None)[:2] == (4, 4)
        out = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / f"{label}.npy"), label))
        assert out.shape == (300, 400) and not np.isnan(out).any()
        quarters = {(0, 0): out[150:, :200], (1, 0): out[150:, 200:], (0, 1): out[:150, :200], (1, 1): out[:150, 200:]}
        for k, (di, dj) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            assert np.allclose(quarters[(di, dj)], 100.0 + 10 * k + offset, atol=TILE_EPS), (label, di, dj)
    assert len([r for r in http_server.requests() if r.path.endswith(".zip")]) == 8
    assert not http_server.stray()


# --- the table and its tool ----------------------------------------------------------------------------------------
def test_the_table_shipped():
    """The table in the catalogue: every sheet of the index (3 253 terrain, 3 310 surface, 2026-11-16), every code a
    sheet of the scheme, the names as published; the test places' sheets in both layers, the recorded rows as the
    index gave them."""
    table = hk._hk_table()
    assert (len(table["dtm"]), len(table["dsm"])) == (3253, 3310)
    for layer in ("dtm", "dsm"):
        assert all(hk.hk_cell(code) is not None for code in table[layer])
        assert all(name.startswith(f"{code}(") and name.endswith(".zip") for code, name in table[layer].items())
        for code in ("11NW5B", "12SW22D", "12SW22A", "16NW3A", "2NE20D", "7SW25C"):
            assert code in table[layer], (layer, code)
        for code, name, url, _ in _rows(layer):
            assert table[layer][code] == name and url.endswith(f"/{hk.HK_FOLDERS[layer]}/{name}")
    assert set(table["dtm"]) < set(table["dsm"]) and "1SE25A" in set(table["dsm"]) - set(table["dtm"])
    assert table["dtm"]["17NW12A"] == "17NW12A(e861n844,e862n845).zip"  # as published
    # every sheet lies whole in the offline box
    from rasterio.warp import transform_bounds
    (code_box,) = hk.HK_BOXES
    south, north, west, east = code_box[1]
    for layer in ("dtm", "dsm"):
        for code in table[layer]:
            w, s, e, n = transform_bounds(hk.HK_CRS, "EPSG:4326", *hk.HK_DTM.index.edges(hk.hk_cell(code)))
            assert south <= s and n <= north and west <= w and e <= east, code


def test_the_sheets_tool(http_server, tmp_path, monkeypatch):
    """tools/hong_kong_sheets.py: the index read page by page (a page with exceededTransferLimit asks the next),
    every row checked (a code off the scheme, a footprint off its box, a URL of another folder, a code twice stop
    it), the table written and read back by the catalogue; a second run with the answers kept asks nothing."""
    import hong_kong_sheets as tool
    rows = _rows("dtm")[:3]
    bad = [(rows[0][0], rows[0][1], rows[0][2].replace("2020dtm", "2020dsm"), rows[0][3])]
    with pytest.raises(ValueError, match="URL"):
        tool.check("dtm", bad)
    moved = [(rows[0][0], rows[0][1], rows[0][2], [[x + 750, y] for x, y in rows[0][3]])]
    with pytest.raises(ValueError, match="footprint"):
        tool.check("dtm", moved)
    with pytest.raises(ValueError, match="not a 1:1000 sheet"):
        tool.check("dtm", [("7SW26A",) + rows[0][1:]])
    with pytest.raises(ValueError, match="twice"):
        tool.check("dtm", rows[:1] * 2)
    # The index's pages: 2 rows then 1, the last without exceededTransferLimit
    monkeypatch.setattr(tool, "INDEX", http_server.base + "/fs")
    monkeypatch.setattr(tool, "PAGE", 2)

    def feature(row):
        return {"attributes": {"TILE_NAME": row[0], "Filename": row[1], "URL": row[2]}, "geometry": {"rings": [row[3]]}}

    for offset, page in ((0, {"features": [feature(r) for r in rows[:2]], "exceededTransferLimit": True}),
                         (2, {"features": [feature(rows[2])]})):
        url, params = tool.page_url("dtm", offset)
        http_server.add(url[len(http_server.base):] + "?" + "&".join(f"{k}={v}" for k, v in params.items()),
                        json.dumps(page).encode(), "application/json")
    cache_dir = str(tmp_path / "cache")
    got = tool.index_rows("dtm", cache_dir, tool.Pacer(0))
    assert [r[0] for r in got] == [r[0] for r in rows] and len(http_server.requests("/fs/")) == 2
    assert tool.check("dtm", got) == {r[0]: r[1] for r in rows}
    # The whole run: the surface layer's one page too, then the table; the second run asks nothing
    url, params = tool.page_url("dsm", 0)
    http_server.add(url[len(http_server.base):] + "?" + "&".join(f"{k}={v}" for k, v in params.items()),
                    json.dumps({"features": [feature(r) for r in _rows("dsm")]}).encode(), "application/json")
    monkeypatch.setattr(tool, "PAUSE_S", 0)
    out, work = str(tmp_path / "t.npz"), str(tmp_path / "work")
    tool.main(["--work", work, "--out", out, "--data-dir", str(tmp_path / "data")])
    asked = len(http_server.requests("/fs/"))
    assert asked == 5
    tool.main(["--work", work, "--out", out, "--data-dir", str(tmp_path / "data")])
    assert len(http_server.requests("/fs/")) == asked
    monkeypatch.setattr(hk, "HK_SHEETS", out)
    hk._hk_table.cache_clear()
    try:
        assert hk._hk_table() == {"dtm": {r[0]: r[1] for r in rows}, "dsm": {r[0]: r[1] for r in _rows("dsm")}}
    finally:
        hk._hk_table.cache_clear()
    assert not http_server.stray()


def test_pacer_keeps_a_second_between_starts(monkeypatch):
    import hong_kong_sheets as tool
    now, slept = [100.0], []
    monkeypatch.setattr(tool.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(tool.time, "sleep", lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    pace = tool.Pacer(1.0)
    pace()
    now[0] += 0.3
    pace()
    now[0] += 2.0
    pace()
    assert slept == [pytest.approx(0.7)]


# --- the catalogue -------------------------------------------------------------------------------------------------
@pytest.fixture
def recorded(monkeypatch):
    with open(REVERSE, encoding="utf-8") as f:
        answers = {(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"] for r in json.load(f)}
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params:
                        answers[(round(lat, 5), round(lon, 5), params["zoom"])])


def test_chosen_by_nominatims_region(tmp_path, recorded):
    """Nominatim names Hong Kong "cn" at zoom 3 and adds ISO3166-2-lvl3 CN-HK at zoom 8: the source's region."""
    for point in (LION_ROCK, TUNG_LUNG_CHAU, CHEK_LAP_KOK):
        assert src.choose_source("auto", *point, str(tmp_path)) == (src.SOURCES["hong_kong"],
                                                                    "the centre is in CN-HK"), point


def test_offline_box(monkeypatch, tmp_path):
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    assert src.choose_source("auto", *LION_ROCK, str(tmp_path)) == (src.SOURCES["hong_kong"],
                                                                     "the centre is in CN-HK")
    assert src.choose_source("auto", 22.62, 114.10, str(tmp_path))[0].id == "europe"  # Shenzhen north of the box
    assert src.choose_source("auto", 22.19, 113.55, str(tmp_path))[0].id == "europe"  # Macau


def test_catalogue_entry():
    s = src.SOURCES["hong_kong"]
    assert (s.countries, s.regions, s.crs, s.default_resolution) == (("cn",), ("cn-hk",), "EPSG:2326", 1.0)
    assert s.nmt.native_res == s.nmpt.native_res == 0.5 and s.fallbacks == ["europe"] and s.neighbours == ()
    assert s.nmt.nodata_below is None and s.nmpt.nodata_below is None and s.sea_fill is None  # the sea: nodata
    assert s.map_areas() == ("hk",) and src.AREA_NAMES["hk"] == "Hong Kong"
    assert s.ortho is None
    credit = s.credits[0]
    assert credit.licence == "CSDI Portal" and credit.url == "https://portal.csdi.gov.hk/csdi-webpage/doc/TNC"
    assert "Common Spatial Data Infrastructure (CSDI) Portal" in credit.attribution
    assert "available under the CSDI terms and conditions" in credit.attribution
    assert "Government of the Hong Kong Special Administrative Region" in credit.attribution
    assert s.nmt.credit == s.nmpt.credit == credit
    assert src.net.HOST_SLOTS_OF["bulkdata.csdi.gov.hk"] == 2 and src.net.HOST_SLOTS_OF["portal.csdi.gov.hk"] == 2
    assert osm.GEOFABRIK_OF_CODE["cn-hk"] == "hong-kong"
    lat, lon = s.sample
    (_, (south, north, west, east)), = s.offline
    assert south <= lat <= north and west <= lon <= east and math.isclose(lat, LION_ROCK[0])
