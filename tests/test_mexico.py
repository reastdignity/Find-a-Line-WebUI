"""Mexico's INEGI 5 m lidar sheets (InegiSheets: sheets of INEGI's 1:10 000 lattice, a static mask of the cells with a
sheet, the viewer's JSON per sheet, a ZIP holding an ArcInfo GRID per sheet), against a fake INEGI and its recorded
answers; the source in the catalogue; tools/mx_sheets.py."""

import io
import json
import math
import os
import struct
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio
from pyproj import Transformer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.catalogue import mexico  # noqa: E402
from sources.layers import inegi  # noqa: E402

RECORDED = os.path.join(HERE, "tests", "data", "recorded", "inegi", "mexico-dtm")
POTRERO = (25.9500, -100.4730)
NODATA = -3.4028234663852886e+38  # an ArcInfo GRID's float nodata (-FLT_MAX)


# --- a fake ArcInfo GRID (GDAL reads AIG, it cannot write one) ---

def aig_files(band: np.ndarray, left: float, top: float, res: float = 5.0) -> dict:
    """The files of a float ArcInfo GRID of band (NaN: no data): hdr.adf, dblbnd.adf, sta.adf, w001001.adf and its
    index w001001x.adf, blocks of one row of 4 lines, raw big-endian floats (as INEGI's)."""
    h, w = band.shape
    rows = math.ceil(h / 4)
    hdr = bytearray(308)
    hdr[0:8] = b"GRID1.2\x00"
    hdr[16:24] = struct.pack(">ii", 2, 0)  # float cells
    hdr[256:280] = struct.pack(">ddd", res, res, left)
    hdr[288:308] = struct.pack(">iiiii", 1, rows, w, 1, 4)
    padded = np.full((rows * 4, w), NODATA, dtype=">f4")
    padded[:h] = np.where(np.isnan(band), NODATA, band)
    data, index, offset = bytearray(), bytearray(), 100
    for r in range(rows):
        block = padded[r * 4:(r + 1) * 4].tobytes()
        index += struct.pack(">ii", offset // 2, len(block) // 2)
        data += struct.pack(">H", len(block) // 2) + block
        offset += 2 + len(block)

    def head(size):
        return bytes.fromhex("0000270afffffc14") + bytes(16) + struct.pack(">i", size // 2) + bytes(72)
    valid = band[np.isfinite(band)]
    return {"hdr.adf": bytes(hdr), "dblbnd.adf": struct.pack(">4d", left, top - h * res, left + w * res, top),
            "sta.adf": struct.pack(">4d", valid.min(), valid.max(), valid.mean(), valid.std()),
            "w001001.adf": head(100 + len(data)) + bytes(data), "w001001x.adf": head(100 + len(index)) + bytes(index)}


def sheet_zip(name: str, band: np.ndarray, left: float, top: float, mod: str = "T") -> bytes:
    """A ZIP as INEGI's: MT_Grid\\<sheet>_mt\\<sheet>_mt\\*.adf with backslashes, its info folder, metadata."""
    kind = "mt" if mod == "T" else "ms"
    low = name.lower()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, body in aig_files(band, left, top).items():
            archive.writestr(f"{kind.upper()}_Grid\\{low}_{kind}\\{low}_{kind}\\{member}", body)
        archive.writestr(f"{kind.upper()}_Grid\\{low}_{kind}\\info\\arc.dir", b"\x00" * 76)
        archive.writestr(f"{kind.upper()}_Metadatos\\{name}_{kind.upper()}.html", b"<html></html>")
    return out.getvalue()


def test_aig_fixture_reads_back(tmp_path):
    band = np.arange(30 * 21, dtype=np.float32).reshape(30, 21) / 4 + 500
    band[0, 0] = np.nan
    folder = tmp_path / "g_mt"
    folder.mkdir()
    for member, body in aig_files(band, 349630.0, 2876710.0).items():
        (folder / member).write_bytes(body)
    with rio.open(str(folder)) as grid:
        assert grid.driver == "AIG" and grid.crs is None and tuple(grid.transform)[:6] == (5, 0, 349630, 0, -5, 2876710)
        got = grid.read(1, masked=True).filled(np.nan)
    assert np.array_equal(np.isnan(got), np.isnan(band)) and np.allclose(got[1:], band[1:])


# --- sheet names ---

def test_sheet_names():
    """The names of INEGI's lattice: El Potrero Chico is G14C15B2; names and cells both ways; every listed cell."""
    lat, lon = POTRERO
    cell = math.floor((lon + 180) * 18), math.floor(lat * 16)
    assert inegi.inegi_sheet(*cell) == "G14C15B2" and inegi.inegi_cell("G14C15B2") == cell
    assert inegi.inegi_cell("g14c15b2") == cell
    # Its neighbours: west B1, the sixth to the east C1, the row to the south B4
    assert inegi.inegi_sheet(cell[0] - 1, cell[1]) == "G14C15B1"
    assert inegi.inegi_sheet(cell[0] + 1, cell[1]) == "G14C15C1"
    assert inegi.inegi_sheet(cell[0], cell[1] - 1) == "G14C15B4"
    for bad in ("G14C15B5", "G14C15G2", "G14C95B2", "G14E15B2", "G14C15B", "X14C15B2", "G14C15B22"):
        assert inegi.inegi_cell(bad) is None, bad
    assert inegi.inegi_sheet(-1, 10) is None and inegi.inegi_sheet(10, -1) is None
    mask, (i0, j0) = mexico.MX_DTM.index.mask()
    rows, cols = np.nonzero(mask)
    for r, c in zip(rows[::97], cols[::97]):  # a sample of the 26 334 sheets: names and cells both ways
        name = inegi.inegi_sheet(i0 + c, j0 + r)
        assert inegi.inegi_cell(name) == (i0 + c, j0 + r)
        assert inegi.inegi_crs(name) == f"EPSG:{4484 + int(name[1:3]) - 11}"
    with pytest.raises(ValueError):
        inegi.inegi_crs("G17A11A1")


def test_grid_entry():
    """The GRID product of a sheet's JSON: its edition and the ZIP's URL; the ASCII product and the other model are
    not it; a download elsewhere than INEGI's file server is refused."""
    with open(os.path.join(RECORDED, "expected.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    edition, url = inegi.grid_entry(recorded["G14C15B2"], "T", mexico.MX_FILES)
    assert edition == 2011 and url.startswith(mexico.MX_FILES) and url.endswith("/Terreno_GRID/702825397371_gr.zip")
    assert inegi.grid_entry(recorded["G14C15B2"], "S", mexico.MX_FILES) is None
    assert inegi.grid_entry([], "T", mexico.MX_FILES) is None
    two = [dict(recorded["G14C15B2"][1], edicion=2013, url_descarga="https://www.inegi.org.mx/contenidos/productos/x/9"),
           recorded["G14C15B2"][1]]
    assert inegi.grid_entry(two, "T", mexico.MX_FILES) == (2013, "https://www.inegi.org.mx/contenidos/productos/x/9_gr.zip")
    with pytest.raises(RuntimeError, match="outside"):
        inegi.grid_entry([dict(recorded["G14C15B2"][1], url_descarga="https://evil.example/x/1")], "T", mexico.MX_FILES)


# --- the layer against a fake INEGI ---

def _cell_box(name: str, crs: str):
    """The cell's edges projected (west, south, east, north in metres): a GRID reaching 200 m beyond them."""
    i, j = inegi.inegi_cell(name)
    west, south, east, north = inegi._CELLS.edges((i, j))
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = zip(*(to.transform(x, y) for x in (west, east) for y in (south, north)))
    return min(xs), min(ys), max(xs), max(ys)


def _fake_grid(name: str, crs: str, value):
    """(band, left, top) of a GRID on whole 5 m covering the sheet's cell and 200 m beyond, value(x, y) per pixel."""
    left, bottom, right, top = _cell_box(name, crs)
    left, top = math.floor((left - 200) / 5) * 5, math.ceil((top + 200) / 5) * 5
    w, h = math.ceil((right + 200 - left) / 5), math.ceil((top - bottom + 200) / 5)
    rows, cols = np.mgrid[0:h, 0:w]
    band = value(left + (cols + 0.5) * 5, top - (rows + 0.5) * 5).astype(np.float32)
    return band, left, top


def _layer(server, mod="T"):
    return src.InegiSheets("Fake INEGI 5 m", f"fake/mx/{mod.lower()}", mod, server.url("/app/geo2/elevacionesmex/"
                           "getF10KDescarga.do"), server.url("/contenidos/productos/"), mexico.MX_SHEETS, "fake/mx")


def _serve(server, names, zips, mod="T"):
    """The JSON of each sheet (the recorded ones, else one GRID product whose ZIP is zips[name], else []) and the
    ZIPs."""
    with open(os.path.join(RECORDED, "expected.json"), encoding="utf-8") as f:
        recorded = json.load(f)

    def answer(request):
        q = dict(request.query)
        name = q.get("cve", "")
        if q.get("res") != "5" or q.get("mod") != mod:
            return Answer(200, b"[]", {"Content-Type": "text/html;charset=UTF-8"})
        if name in zips:
            items = [{"mod": mod, "edicion": 2012, "archivo": "|_gr.zip,0.1 MB",
                      "url_descarga": server.url(f"/contenidos/productos/lidar/{name}")}]
        else:
            items = json.loads(json.dumps(recorded.get(name, [])).replace("https://www.inegi.org.mx", server.base))
        names.append(name)
        return Answer(200, json.dumps(items).encode(), {"Content-Type": "text/html;charset=UTF-8"})
    server.route("/app/geo2/elevacionesmex/getF10KDescarga.do", answer)
    for name, body in zips.items():
        server.add(f"/contenidos/productos/lidar/{name}_gr.zip", body, "application/x-zip-compressed")


def test_recorded_sheet_answers(http_server, tmp_path):
    """The recorded JSON of two sheets, asked through the layer on the server, cached byte for byte as recorded."""
    with open(os.path.join(RECORDED, "answers.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    http_server.add_cassette(RECORDED)
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    found = {}
    for name in recorded["case"]["sheets"]:
        found[name] = layer.index.answer(cache_dir, name)
    written = json.dumps(found, sort_keys=True).encode().replace(http_server.base.encode(), recorded["hosts"][0].encode())
    with open(os.path.join(RECORDED, "expected.json"), "rb") as f:
        assert written == f.read()
    assert not http_server.stray() and len(http_server.log) == 2
    assert {r.user_agent for r in http_server.log} == {cache.http_headers()["User-Agent"]}
    # Cached: asked again only by an update
    layer.index.answer(cache_dir, "G14C15B2")
    assert len(http_server.log) == 2
    layer.index.answer(cache_dir, "G14C15B2", "all")
    assert len(http_server.log) == 3


def test_sheets_over_a_grid_download_and_cut(http_server, tmp_path):
    """The sheets of a grid across four cells (each listed, two with a GRID); each ZIP downloaded whole, its GRID
    read in the sheet's zone (EPSG:4487), cut to its cell plus 10 m and to the rows and columns it keeps; two
    neighbours meet without a gap or an overlap beyond the margin; the edition in the name and the tags."""
    crs = "EPSG:4487"
    lat, lon = POTRERO
    i, j = math.floor((lon + 180) * 18), math.floor(lat * 16)
    b2, b1 = inegi.inegi_sheet(i, j), inegi.inegi_sheet(i - 1, j)
    zips = {}
    for name, offset in ((b2, 0.0), (b1, 1000.0)):  # the western one 1000 m higher: whose pixel it is shows
        band, left, top = _fake_grid(name, crs, lambda x, y, o=offset: 500 + o + (x % 100) / 10 + (y % 100) / 100)
        zips[name] = sheet_zip(name, band, left, top)
    asked = []
    _serve(http_server, asked, zips)
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    # A grid around the corner of the two cells' common edge with the row to the north
    west, south, east, north = inegi._CELLS.edges((i, j))
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(west, north)
    grid = make_grid((x - 300, y - 300, x + 300, y + 300), 5.0, crs)
    total, todo, mb = layer.estimate(grid, cache_dir, None)
    assert (total, todo) == (2, 2) and mb == pytest.approx(8.4)
    listed = [inegi.inegi_sheet(*c) for c in ((i - 1, j), (i, j), (i - 1, j + 1), (i, j + 1)) if layer.index.listed(*c)]
    assert b1 in listed and b2 in listed and sorted(asked) == sorted(listed)
    tiles = layer.tiles(grid)
    assert [t.name for t in tiles] == [b1, b2] and {t.crs for t in tiles} == {crs} and {t.edition for t in tiles} == {2012}
    src.download_layers([(layer, "terrain")], grid, cache_dir)
    paths = layer.files(grid, cache_dir)
    assert [os.path.basename(p) for p in paths] == [f"2012_{b1}.tif", f"2012_{b2}.tif"]
    with rio.open(paths[1]) as tile:
        assert tile.crs.to_epsg() == 4487 and tile.tags()["INEGI_SHEET"] == b2 and tile.tags()["INEGI_EDITION"] == "2012"
        assert tile.transform.a == 5.0 and tile.transform.c % 5 == 0 and tile.transform.f % 5 == 0
        left, bottom, right, top = _cell_box(b2, crs)
        assert tile.bounds.left > left - 200 and tile.bounds.right < right + 200  # cut: not the whole GRID
    # The mosaic: west of the common edge the western sheet's heights (1000 m higher), east of it the eastern's
    mosaic = src.build_mosaic(paths, grid, str(tmp_path / "m.tif"), "terrain")
    assert np.isfinite(mosaic[grid.height // 2 + 5:]).all()  # the southern half: both sheets, no gap between
    row = grid.height - 10
    y_row = grid.top - (row + 0.5) * 5
    _, lat_row = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y_row)
    edge_col = (Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(west, lat_row)[0] - grid.left) / 5
    assert mosaic[row, int(edge_col) - 4] > 1400 and mosaic[row, int(edge_col) + 4] < 600
    # Cached: nothing asked again (the JSON answers too)
    before = len(http_server.log)
    assert layer.estimate(grid, cache_dir, None)[1] == 0 and len(http_server.log) == before
    assert layer.source_date(tiles[0]) == "2012"


def test_a_new_edition_replaces_the_old_file(http_server, tmp_path):
    """An update whose answer names a newer edition: a new file, the older one deleted once it is downloaded."""
    crs = "EPSG:4487"
    name = "G14C15B2"
    band, left, top = _fake_grid(name, crs, lambda x, y: 700 + 0 * x)
    asked = []
    _serve(http_server, asked, {name: sheet_zip(name, band, left, top)})
    layer = _layer(http_server)
    cache_dir = str(tmp_path / "cache")
    old = os.path.join(cache_dir, "fake", "mx", "t", f"2011_{name}.tif")
    os.makedirs(os.path.dirname(old))
    with open(old, "wb") as f:
        f.write(b"old")
    cache.record(cache_dir, old)
    lat, lon = inegi._CELLS.edges(inegi.inegi_cell(name))[1] + 0.03, inegi._CELLS.edges(inegi.inegi_cell(name))[0] + 0.03
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    grid = make_grid((x - 100, y - 100, x + 100, y + 100), 5.0, crs)
    src.download_layers([(layer, "terrain")], grid, cache_dir)
    assert not os.path.exists(old) and os.path.exists(os.path.join(cache_dir, "fake", "mx", "t", f"2012_{name}.tif"))


def test_download_faults(http_server, tmp_path):
    """A 404 is no data (no file, recorded missing); an HTML page, a ZIP without a GRID, a ZIP of two GRIDs, a cut-short
    answer and an answer beyond the byte cap are errors; the index's JSON that is not a list is an error, the cached
    answer is used when the index fails later."""
    crs = "EPSG:4487"
    name = "G14C15B2"
    i, j = inegi.inegi_cell(name)
    tile = inegi.InegiSheet(i, j, name, 2012, http_server.url("/z/none_gr.zip"), crs)
    reader = inegi.InegiGrid("Fake")
    path = str(tmp_path / "t" / "a.tif")
    assert reader.fetch(tile, path).received == 0 and not os.path.exists(path)
    http_server.add("/z/page_gr.zip", b"<html>no</html>", "text/html")
    band, left, top = _fake_grid(name, crs, lambda x, y: 600 + 0 * x)
    good = sheet_zip(name, band, left, top)
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("MT_Metadatos\\a.html", b"x")
    two = io.BytesIO()
    with zipfile.ZipFile(two, "w") as archive:
        for k in (1, 2):
            for member, body in aig_files(band, left, top).items():
                archive.writestr(f"MT_Grid/g{k}/g{k}/{member}", body)
    http_server.add("/z/empty_gr.zip", empty.getvalue(), "application/x-zip-compressed")
    http_server.add("/z/two_gr.zip", two.getvalue(), "application/x-zip-compressed")
    http_server.route("/z/short_gr.zip", lambda request: Answer(200, good[:len(good) // 2],
                                                               {"Content-Type": "application/x-zip-compressed"}))
    http_server.add("/z/good_gr.zip", good, "application/x-zip-compressed")
    sleeps = []
    original = src.net._sleep
    src.net._sleep = lambda attempt: sleeps.append(attempt)
    try:
        for bad, message in (("page", "a ZIP expected"), ("empty", "0 ArcInfo GRIDs"), ("two", "2 ArcInfo GRIDs"),
                             ("short", "not a ZIP")):
            with pytest.raises(RuntimeError, match=message):
                reader.fetch(tile._replace(url=http_server.url(f"/z/{bad}_gr.zip")), path)
            assert not os.path.exists(path)
        small = inegi.InegiGrid("Fake", max_bytes=1000)
        with pytest.raises(RuntimeError, match="more than 1000 bytes"):
            small.fetch(tile._replace(url=http_server.url("/z/good_gr.zip")), path)
        assert not os.listdir(os.path.dirname(path))  # no part file, no unpacked folder left
        assert reader.fetch(tile._replace(url=http_server.url("/z/good_gr.zip")), path).received == len(good)
        # The index: an answer that is not a list is an error; once cached, a failing index leaves the cached answer
        http_server.route("/idx", lambda request: Answer(200, b'{"a": 1}', {"Content-Type": "text/html"}))
        index = inegi.InegiIndex("fake/mx/t", "T", http_server.url("/idx"), http_server.url("/contenidos/"),
                                 mexico.MX_SHEETS, "fake/mx", 365)
        with pytest.raises(RuntimeError, match="a list expected"):
            index.answer(str(tmp_path / "c"), name)
    finally:
        src.net._sleep = original
    cached = inegi.InegiIndex("fake/mx/t", "T", http_server.url("/ok"), http_server.url("/contenidos/"),
                              mexico.MX_SHEETS, "fake/mx", 365)
    http_server.add("/ok", b"[]", "text/html")
    assert cached.answer(str(tmp_path / "c2"), name) == []
    cached.index_url = http_server.url("/gone-500")
    http_server.route("/gone-500", lambda request: Answer(500, b"down", {"Content-Type": "text/html"}))
    src.net._sleep = lambda attempt: None
    try:
        assert cached.answer(str(tmp_path / "c2"), name, "all") == []  # the cached answer, however old
        assert cached.sheets([(i, j)], str(tmp_path / "c3"), None) == []  # none cached: left out, said
    finally:
        src.net._sleep = original


def test_mask_tool_and_has_data_near(tmp_path):
    """tools/mx_sheets.py: centroids to cells (each must carry its sheet's name), the saved mask read back; the stored
    mask at the places of wave 0's study."""
    import mx_sheets
    to3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    lat, lon = POTRERO
    i, j = math.floor((lon + 180) * 18), math.floor(lat * 16)

    def centroid(ci, cj):
        x, y = to3857.transform(-180 + (ci + 0.5) / 18, (cj + 0.5) / 16)
        return {"cve": inegi.inegi_sheet(ci, cj), "x": x, "y": y}
    listing = [centroid(i, j), centroid(i + 3, j - 2)]
    assert mx_sheets.cells(listing) == [(i, j), (i + 3, j - 2)]
    with pytest.raises(ValueError, match="lies in the cell"):
        mx_sheets.cells([dict(listing[0], cve=inegi.inegi_sheet(i + 1, j))])
    path = str(tmp_path / "m.npz")
    mx_sheets.save(path, {"t": [(i, j), (i + 3, j - 2)], "s": [(i, j)]})
    index = inegi.InegiIndex("f/t", "T", "https://x/", "https://x/", path, "f", 365)
    assert index.listed(i, j) and index.listed(i + 3, j - 2) and not index.listed(i + 1, j)
    assert index.has_data_near(lat, lon, "") and not index.has_data_near(lat + 1, lon, "")
    surface = inegi.InegiIndex("f/s", "S", "https://x/", "https://x/", path, "f", 365)
    assert surface.listed(i, j) and not surface.listed(i + 3, j - 2)
    # The stored mask (2026-11-15): wave 0's places with 5 m sheets, and without
    stored = src.SOURCES["mexico"].nmt
    for place in (POTRERO, (25.640, -100.470), (26.084, -100.438), (20.188, -98.730), (20.748, -99.948),
                  (19.293, -99.264)):  # Potrero Chico, La Huasteca, El Salto, El Chico, Peña de Bernal, Los Dinamos
        assert stored.has_data_near(*place, "") is True, place
    for place in ((27.526, -107.821), (28.200, -108.210)):  # the Copper Canyon (Divisadero), Basaseachi
        assert stored.has_data_near(*place, "") is False, place
    mask, _ = stored.index.mask()
    assert mask.sum() == 26334 and src.SOURCES["mexico"].nmpt.index.mask()[0].sum() == 26333


def test_mexico_declared():
    """The source: before the usa (its offline box holds Monterrey); its CRS, resolution, layers, neighbours."""
    mx = src.SOURCES["mexico"]
    order = list(src.SOURCES)
    assert order.index("mexico") < order.index("usa")
    assert mx.countries == ("mx",) and mx.default_resolution == 5.0 and mx.fallbacks == ["europe"]
    assert mx.instead_without_data == "europe" and mx.neighbours == ("usa",) and "mexico" in src.SOURCES["usa"].neighbours
    assert mx.working_crs(*POTRERO) == "EPSG:4487" and mexico.mx_crs(32.5, -117.0) == "EPSG:4484"
    assert mexico.mx_crs(18.5, -88.0) == "EPSG:4489" and mexico.mx_crs(30.0, -130.0) == "EPSG:4484"
    assert isinstance(mx.nmt, src.InegiSheets) and isinstance(mx.nmpt, src.InegiSheets)
    assert mx.nmt.folder == "mexico/mde-lidar5m/t" and mx.nmpt.folder == "mexico/mde-lidar5m/s"
    assert mx.nmt.index.mod == "T" and mx.nmpt.index.mod == "S" and mx.nmt.ttl_days is None
    assert mx.credits[0].attribution.startswith("Fuente: INEGI, Modelos Digitales de Elevación de Alta Resolución")
    assert src.HOST_SLOTS_OF["www.inegi.org.mx"] == 2
    assert src.AREA_NAMES["mx"] == "México"


@pytest.mark.parametrize("place, code", [
    ((31.7619, -106.4850), "us"),   # El Paso
    ((27.5306, -99.4803), "us"),    # Laredo
    ((32.7157, -117.1611), "us"),   # San Diego
    ((31.3404, -110.9343), "us"),   # Nogales, Arizona
    ((28.7091, -100.4995), "us"),   # Eagle Pass
    ((25.9017, -97.4975), "us"),    # Brownsville
    ((25.6866, -100.3161), "mx"),   # Monterrey
    ((31.6904, -106.4245), "mx"),   # Ciudad Juárez
    ((32.5149, -117.0382), "mx"),   # Tijuana
    ((32.6245, -115.4523), "mx"),   # Mexicali
    ((27.4763, -99.5164), "mx"),    # Nuevo Laredo
    ((25.8690, -97.5027), "mx"),    # Matamoros
    ((31.3086, -110.9422), "mx"),   # Nogales, Sonora
    (POTRERO, "mx"), ((19.4326, -99.1332), "mx"), ((21.1619, -86.8515), "mx"),  # Mexico City, Cancún
])
def test_offline_boxes_along_the_border(place, code, monkeypatch, tmp_path):
    """Offline, the first box holding a point wins: the US border towns stay with the usa, the Mexican ones are
    Mexico's."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(src.choose.osm, "reverse", offline)
    assert src.choose.country_code(*place, str(tmp_path)) == code


def test_auto_takes_europe_without_sheets(monkeypatch, tmp_path):
    """Offline: El Potrero Chico gets mexico; the Copper Canyon (no sheet near it) europe."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(src.choose.osm, "reverse", offline)
    assert src.choose_source("auto", *POTRERO, str(tmp_path))[0].id == "mexico"
    assert src.choose_source("auto", 27.526, -107.821, str(tmp_path)) == (
        src.SOURCES["europe"], "the centre is in MX, but mexico has no terrain data near it")


def test_check_source_reads_the_grid(http_server, tmp_path):
    """tools/check_source.py compares a cached sheet with its ZIP's GRID, read on its own (zipfile, GDAL), cut to the
    cell as the layer cuts it: equal values, the same pixels without data."""
    import check_source
    crs = "EPSG:4487"
    name = "G14C15B2"
    i, j = inegi.inegi_cell(name)
    band, left, top = _fake_grid(name, crs, lambda x, y: 500 + (x % 100) / 10 + (y % 100) / 100)
    http_server.add("/z/g_gr.zip", sheet_zip(name, band, left, top), "application/x-zip-compressed")
    tile = inegi.InegiSheet(i, j, name, 2012, http_server.url("/z/g_gr.zip"), crs)
    layer = _layer(http_server)
    path = str(tmp_path / "t.tif")
    layer.reader.fetch(tile, path)
    with rio.open(path) as cached:
        values = cached.read(1, masked=True).astype(np.float32).filled(np.nan)
        profile = {"crs": cached.crs, "transform": cached.transform, "width": cached.width, "height": cached.height}
    source = check_source._read_grid(layer, tile.url, tile, profile)
    result = check_source.compare(values, source)
    assert result["max_abs_m"] <= 0.0051 and result["same_nodata"] == 1.0 and np.isnan(values).any()
