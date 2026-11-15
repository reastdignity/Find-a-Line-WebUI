"""The parts of Australia's national 5 m DEM (GeoWcsTiles: a WCS 1.0.0 in a geographic CRS on its own pixels) and
Uruguay's 2.5 m DTM (GeoSheetTiles: sheets of a geographic grid, named from their cells), against a fake service."""

import os
import re
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box as shapely_box

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.catalogue import australia, uruguay  # noqa: E402
from sources.indexes.tilings import GeoPixelTiling  # noqa: E402

# A small fake grid with Geoscience Australia's pixel and a corner of its own: 2500 x 1800 pixels
CORNER = (151.0, -33.5)
PIXEL = australia.AU_PIXEL
SIZE = (2500, 1800)


def value(lon, lat):
    """The fake coverage at a point: 0 (no data) west of 151.06 E, heights elsewhere."""
    return np.where(lon < 151.06, 0.0, (lon - 151.0) * 1e4 + (lat + 34.0) * 1e3)


def _geotiff(left, bottom, right, top, width, height, crs="EPSG:4283") -> bytes:
    dx, dy = (right - left) / width, (top - bottom) / height
    rows, cols = np.mgrid[0:height, 0:width]
    band = value(left + (cols + 0.5) * dx, top - (rows + 0.5) * dy).astype(np.float32)
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=width, height=height, count=1, dtype="float32", crs=crs,
                          transform=from_origin(left, top, dx, dy)) as dst:
            dst.write(band, 1)
        return memfile.read()


def _wcs(server, path="/wcs"):
    """A WCS 1.0.0 answering GetCoverage on the asked BBOX, WIDTH and HEIGHT; 404 beyond the fake grid."""
    def answer(request):
        q = dict(request.query)
        if q.get("REQUEST") != "GetCoverage" or q.get("VERSION") != "1.0.0" or q.get("CRS") != "EPSG:4283":
            return Answer(400, b"bad request", {"Content-Type": "text/xml"})
        left, bottom, right, top = (float(v) for v in q["BBOX"].split(","))
        if left >= CORNER[0] + SIZE[0] * PIXEL[0] or top <= CORNER[1] - SIZE[1] * PIXEL[1]:
            return Answer(404, b"<ServiceExceptionReport>parameter BBOX is invalid", {"Content-Type": "text/xml"})
        return Answer(200, _geotiff(left, bottom, right, top, int(q["WIDTH"]), int(q["HEIGHT"])),
                      {"Content-Type": "image/tiff"})
    server.route(path, answer)


def _layer(server, tile_px=1000):
    return src.GeoWcsTiles("Fake 5 m DEM", server.url("/wcs"), "1", "EPSG:4283", "fake/dem5m/live", 5.0,
                           corner=CORNER, pixel=PIXEL, size=SIZE, tile_px=tile_px, zero_is_nodata=True)


def test_geo_pixel_tiling_boxes_paths_and_tiles():
    """Tiles of whole pixels from the corner, the last ones cut at the grid's size; paths and tile_of round trip;
    the tiles over a grid inside, across and outside the grid's area (and under an outline within the box)."""
    tiling = GeoPixelTiling("EPSG:4283", "fake/dem5m/live", 1000, CORNER, PIXEL, SIZE)
    first = tiling.box((0, -1))
    assert (first.width, first.height) == (1000, 1000)
    assert first.left == CORNER[0] and first.top == CORNER[1]
    assert first.right == CORNER[0] + 1000 * PIXEL[0] and first.bottom == CORNER[1] - 1000 * PIXEL[1]
    last = tiling.box((2, -2))  # columns 2000-2499, rows 1000-1799
    assert (last.width, last.height) == (500, 800)
    assert last.right == CORNER[0] + 2500 * PIXEL[0] and last.bottom == CORNER[1] - 1800 * PIXEL[1]
    # The grid's corner, pixel and size in the folder's name: another grid never takes these tiles
    grid = re.fullmatch(r"epsg4283-1000px-g([0-9a-f]{8})", tiling._dir).group(1)
    moved = GeoPixelTiling("EPSG:4283", "fake/dem5m/live", 1000, (CORNER[0] + PIXEL[0], CORNER[1]), PIXEL, SIZE)
    assert moved._dir != tiling._dir
    name = f"fake/dem5m/live/epsg4283-1000px-g{grid}/2_-2.tif"
    assert tiling.path("C:/cache", (2, -2)).replace(os.sep, "/") == f"C:/cache/{name}"
    assert tiling.tile_of(name) == (2, -2) and moved.tile_of(name) is None
    assert tiling.tile_of("fake/dem5m/live/epsg4283-1000px/2_-2.tif") is None
    assert tiling.tile_of(f"other/epsg4283-1000px-g{grid}/2_-2.tif") is None
    # A grid in GDA94 / MGA 56 around a point inside the first tile: that tile only
    from pyproj import Transformer
    to_mga = Transformer.from_crs("EPSG:4283", "EPSG:28356", always_xy=True)
    x, y = to_mga.transform(CORNER[0] + 500 * PIXEL[0], CORNER[1] - 500 * PIXEL[1])
    inside = make_grid((x - 100, y - 100, x + 100, y + 100), 5.0, "EPSG:28356")
    assert tiling.tiles(inside) == [(0, -1)]
    # Across the tiles' corner of (0, -1), (1, -1), (0, -2), (1, -2)
    x, y = to_mga.transform(CORNER[0] + 1000 * PIXEL[0], CORNER[1] - 1000 * PIXEL[1])
    across = make_grid((x - 300, y - 300, x + 300, y + 300), 5.0, "EPSG:28356")
    assert sorted(tiling.tiles(across)) == [(0, -2), (0, -1), (1, -2), (1, -1)]
    # Under an outline in the box's north-west quarter only: the tiles under it, none outside the box
    across.area_shape = shapely_box(x - 300, y + 20, x - 20, y + 300)  # clear of the meridian (convergence)
    assert tiling.tiles(across) == [(0, -1)]
    # Beyond the grid's size: none
    x, y = to_mga.transform(CORNER[0] - 0.1, CORNER[1] + 0.1)
    assert tiling.tiles(make_grid((x - 100, y - 100, x + 100, y + 100), 5.0, "EPSG:28356")) == []


def test_geo_wcs_tiles(http_server, tmp_path):
    """A tile asked on the service's own pixels (BBOX to 17 digits, WIDTH and HEIGHT its pixels) and saved on
    them; zero is no data; a tile whose answer has no valid pixel is missing (no file), and so is a 404."""
    _wcs(http_server)
    layer = _layer(http_server)
    path = str(tmp_path / "t.tif")
    fetched = layer.download_tile((1, -1), path)
    assert fetched.received > 0 and fetched.url == http_server.url("/wcs")
    asked = dict(http_server.requests("/wcs")[-1].query)
    box = layer.index.box((1, -1))
    assert [float(v) for v in asked["BBOX"].split(",")] == [box.left, box.bottom, box.right, box.top]
    assert (asked["WIDTH"], asked["HEIGHT"], asked["COVERAGE"], asked["FORMAT"]) == ("1000", "1000", "1", "GeoTIFF")
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 4283 and tile.shape == (1000, 1000)
        assert tile.transform.almost_equals(from_origin(box.left, box.top, *PIXEL), precision=1e-12)
        band = tile.read(1)
    rows, cols = np.mgrid[0:1000, 0:1000]
    truth = value(box.left + (cols + 0.5) * PIXEL[0], box.top - (rows + 0.5) * PIXEL[1]).astype(np.float32)
    assert np.isnan(band[truth == 0]).all() and (truth == 0).any()  # west of 151.06 E: no data
    valid = truth != 0
    assert np.abs(band[valid] - truth[valid]).max() < 0.01  # LERC within 5 mm
    # West of 151.06 E the whole tile is zero: missing, no file
    zero = str(tmp_path / "zero.tif")
    assert layer.download_tile((0, -1), zero).received == 0 and not os.path.exists(zero)
    # Beyond the grid: 404, missing
    beyond = str(tmp_path / "beyond.tif")
    far = src.GeoWcsTiles("Fake", http_server.url("/wcs"), "1", "EPSG:4283", "fake/x/live", 5.0,
                          corner=(CORNER[0] + 1, CORNER[1]), pixel=PIXEL, size=SIZE)
    assert far.download_tile((0, -1), beyond).received == 0 and not os.path.exists(beyond)
    assert layer.tile_of(os.path.relpath(layer.tile_path(str(tmp_path), (1, -1)), str(tmp_path)).replace(os.sep, "/")) \
        == (1, -1)


def test_australia_declared():
    """The national source: after Queensland and Tasmania (their regions win), its working grid in GDA94 / MGA."""
    ids = list(src.SOURCES)
    assert ids.index("australia") > ids.index("queensland_demh") and ids.index("australia") > ids.index("tasmania")
    assert australia.au_mga_crs(-33.82, 151.297) == "EPSG:28356"
    assert australia.au_mga_crs(-31.95, 115.86) == "EPSG:28350"
    assert australia.au_mga_crs(-12.0, 100.0) == "EPSG:28349"  # outside: the nearest zone
    layer = src.SOURCES["australia"].nmt
    assert layer.ttl_days is not None  # a live folder: data may be added
    assert layer.index.box((0, -1)).left == australia.AU_CORNER[0]


def test_uruguay_sheet_names():
    """Every cell of the table names its sheet and back; names of the IDE's index at their places."""
    cells = uruguay._uy_remesas()
    assert len(cells) == 6597 and sorted(set(cells.values())) == list(range(1, 13))
    assert all(uruguay.uy_cell(uruguay.uy_sheet(*cell)) == cell for cell in cells)
    # (name, west, south) of sheets of the index (Articulacion_Ortoimagenes_Nacional.shp, 2026-11-15)
    for name, west, south, remesa in (("C17A6", -53.88, -32.67, 9), ("O12A2", -57.90, -31.725, 10),
                                      ("J23D2", -55.92, -33.795, 1), ("P25B1", -58.14, -34.065, 3)):
        cell = round((west + 58.68) / 0.06), round((south + 35.10) / 0.045)
        assert uruguay.uy_sheet(*cell) == name and uruguay.uy_cell(name) == cell
        assert uruguay.uy_url(*cell) == (f"https://visualizador.ide.uy/descargas/datos/CN_Remesa_{remesa:02d}/01_MDT/"
                                         f"02_MDT_GeoTIFF_Resolucion_250cm/{name}_MDT_Remesa_{remesa:02d}.tif")
    assert uruguay.uy_cell("I12A1") is None and uruguay.uy_cell("C17E1") is None and uruguay.uy_cell("C17A7") is None
    assert uruguay.uy_url(0, 0) is None  # in the grid, not in the table
    assert uruguay.uy_crs(-32.92, -54.467) == "EPSG:5382" and uruguay.uy_crs(-33.0, -53.5) == "EPSG:5383"


def test_geo_sheet_tiles(http_server, tmp_path):
    """A sheet downloaded whole and written on its own pixels (its CRS, its origin off whole metres, -32767 as no
    data); a cell without a file in the table missing without a request; the sheets over a grid; tile_of."""
    origin = (654460.0374, 6209564.7505)
    band = np.full((40, 50), 120.25, dtype=np.float32)
    band[:5] = -32767
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=50, height=40, count=1, dtype="float32", crs="EPSG:5382",
                          nodata=-32767, transform=from_origin(*origin, 2.5, 2.5)) as dst:
            dst.write(band, 1)
            dst.update_tags(AREA_OR_POINT="Area")
        http_server.add("/d/E18D5.tif", memfile.read(), "image/tiff")
    known = uruguay.uy_cell("E18D5")
    layer = src.GeoSheetTiles("Fake MDT", "fake/mdt/2018", "EPSG:4326", uruguay.UY_CELL, uruguay.UY_ORIGIN, 2.5,
                              uruguay.uy_sheet, uruguay.uy_cell,
                              lambda i, j: http_server.url(f"/d/{uruguay.uy_sheet(i, j)}.tif") if (i, j) == known
                              else None, within=(0, 0, 95, 111))
    path = layer.tile_path(str(tmp_path), known)
    assert path.replace(os.sep, "/").endswith("fake/mdt/2018/E18D5.tif")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    assert layer.download_tile(known, path).received > 0
    with rio.open(path) as tile:
        assert tile.crs.to_epsg() == 5382 and tile.transform.almost_equals(from_origin(*origin, 2.5, 2.5))
        got = tile.read(1)
    assert np.isnan(got[:5]).all() and np.allclose(got[5:], 120.25, atol=0.006)
    other = (known[0] + 1, known[1])
    assert layer.tile_url(other) is None
    before = len(http_server.requests("/d/"))
    assert layer.download_tile(other, str(tmp_path / "none.tif")).received == 0
    assert len(http_server.requests("/d/")) == before
    assert layer.tile_of("fake/mdt/2018/E18D5.tif") == known and layer.tile_of("fake/mdt/2018/E18D7.tif") is None
    # The sheets over a grid around the sheet's middle: that sheet; a grid across four corners: four
    west, south, east, north = layer.index.edges(known)
    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:5382", always_xy=True)
    x, y = to_utm.transform((west + east) / 2, (south + north) / 2)
    assert layer.tiles(make_grid((x - 200, y - 200, x + 200, y + 200), 2.5, "EPSG:5382")) == [known]
    x, y = to_utm.transform(east, north)
    assert len(layer.tiles(make_grid((x - 200, y - 200, x + 200, y + 200), 2.5, "EPSG:5382"))) == 4
    assert re.fullmatch(r"[A-R]\d\d[A-D][1-6]", uruguay.uy_sheet(*known))


def test_probe_of_the_new_kinds(http_server, tmp_path):
    """The probe: a GetCoverage of 16 x 16 own pixels for GeoWcsTiles, the first 8 bytes (never one) of a sheet for
    GeoSheetTiles, which must be a TIFF's."""
    from sources import probe
    _wcs(http_server)
    layer = _layer(http_server)
    assert probe.strategy(layer) == "geowcs"
    lat, lon = CORNER[1] - 500 * PIXEL[1], CORNER[0] + 1500 * PIXEL[0]
    assert probe._geo_coverage(str(tmp_path), layer, lat, lon) == (probe.NONE, probe.OK)
    asked = dict(http_server.requests("/wcs")[-1].query)
    assert (asked["WIDTH"], asked["HEIGHT"]) == ("16", "16")
    with pytest.raises(RuntimeError, match="GetCoverage: HTTP 404"):
        probe._geo_coverage(str(tmp_path), layer, lat, lon + 1)
    http_server.add("/s/a.tif", b"II*\x00" + bytes(100), "image/tiff")
    http_server.add("/s/b.tif", b"<html>", "text/html")
    assert probe.strategy(src.SOURCES["uruguay"].nmt) == "sheet"
    assert probe._tiff_head(str(tmp_path), http_server.url("/s/a.tif")) == ""
    assert http_server.requests("/s/a.tif")[-1].headers["range"] == "bytes=0-7"
    with pytest.raises(RuntimeError, match="not a TIFF"):
        probe._tiff_head(str(tmp_path), http_server.url("/s/b.tif"))


def test_point_registered_sheet(http_server, tmp_path):
    """The IDE's files are PixelIsPoint (AREA_OR_POINT=Point): the cached tile is written on the pixel areas GDAL
    reads from the file (its corner half a pixel up and left of the first pixel's centre), without the Point tag,
    so the mosaic never moves it again."""
    centre = (654461.2874, 6209563.5005)  # the first pixel's centre
    area = from_origin(centre[0] - 1.25, centre[1] + 1.25, 2.5, 2.5)
    band = np.full((20, 30), 88.5, dtype=np.float32)
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=30, height=20, count=1, dtype="float32", crs="EPSG:5382",
                          nodata=-32767, transform=area) as dst:
            dst.update_tags(AREA_OR_POINT="Point")
            dst.write(band, 1)
        served = memfile.read()
    with MemoryFile(served) as check, check.open() as src_file:
        assert src_file.tags().get("AREA_OR_POINT") == "Point"
        read_transform = src_file.transform
    assert read_transform.almost_equals(area)
    http_server.add("/p/E18D6.tif", served, "image/tiff")
    cell = uruguay.uy_cell("E18D6")
    layer = src.GeoSheetTiles("Fake MDT", "fake/mdt/2018", "EPSG:4326", uruguay.UY_CELL, uruguay.UY_ORIGIN, 2.5,
                              uruguay.uy_sheet, uruguay.uy_cell,
                              lambda i, j: http_server.url(f"/p/{uruguay.uy_sheet(i, j)}.tif"))
    path = str(tmp_path / "E18D6.tif")
    assert layer.download_tile(cell, path).received > 0
    with rio.open(path) as tile:
        assert tile.transform.almost_equals(area)
        assert tile.tags().get("AREA_OR_POINT", "Area") == "Area"
        assert np.allclose(tile.read(1), 88.5, atol=0.006)


def test_geo_wcs_answer_on_other_pixels(http_server, tmp_path):
    """A service answering on pixels other than those asked (here half a pixel east and south, and one pixel
    wider): the tile is resampled by nearest neighbour onto its own pixels."""
    def answer(request):
        q = dict(request.query)
        left, bottom, right, top = (float(v) for v in q["BBOX"].split(","))
        width, height = int(q["WIDTH"]), int(q["HEIGHT"])
        dx, dy = (right - left) / width, (top - bottom) / height
        body = _geotiff(left + dx / 2, bottom - dy / 2, right + dx * 1.5, top - dy / 2, width + 1, height)
        return Answer(200, body, {"Content-Type": "image/tiff"})
    http_server.route("/off", answer)
    layer = src.GeoWcsTiles("Fake 5 m DEM", http_server.url("/off"), "1", "EPSG:4283", "fake/dem5m/live", 5.0,
                            corner=CORNER, pixel=PIXEL, size=SIZE, tile_px=100, zero_is_nodata=True)
    tile = (20, -1)  # columns 2000-2099: all east of 151.06 E
    path = str(tmp_path / "off.tif")
    assert layer.download_tile(tile, path).received > 0
    box = layer.index.box(tile)
    with rio.open(path) as written:
        assert written.shape == (100, 100)
        assert written.transform.almost_equals(from_origin(box.left, box.top, *PIXEL), precision=1e-12)
        band = written.read(1)
    # Nearest: each pixel takes an answered pixel half a pixel off, so its value is within one pixel's step of the
    # truth at its centre, and not the truth itself
    rows, cols = np.mgrid[0:100, 0:100]
    truth = value(box.left + (cols + 0.5) * PIXEL[0], box.top - (rows + 0.5) * PIXEL[1])
    step = 1e4 * PIXEL[0] + 1e3 * PIXEL[1]
    finite = np.isfinite(band)
    assert finite[1:, 1:].all() and np.abs(band[finite] - truth[finite]).max() <= step + 0.01
    assert not np.allclose(band[finite], truth[finite], atol=0.01)


def test_coverage_cells_tool_and_has_data_near(tmp_path):
    """tools/au_coverage.py: the pieces within the service's 4096 px, cells holding data when any sample does, the
    saved mask read back by GeoWcsTiles.has_data_near; and the stored mask at the places it was checked at."""
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import au_coverage
    assert au_coverage.pieces((718787, 651083), (88, 80)) == [(0, 0, 4096, 4096), (4096, 0, 4073, 4096),
                                                              (0, 4096, 4096, 4043), (4096, 4096, 4073, 4043)]
    samples = np.zeros((10, 9), dtype=np.float32)
    samples[5, 8] = 12.5  # one sample with data: the cell of rows 4-7, column 8
    samples[0, 0] = np.nan
    mask = au_coverage.cells(samples, 4)
    assert mask.shape == (3, 3) and mask.sum() == 1 and mask[1, 2]

    def get(params):  # a fake service answering every piece
        q = dict(params)
        left, bottom, right, top = (float(v) for v in q["BBOX"].split(","))
        return _geotiff(left, bottom, right, top, int(q["WIDTH"]), int(q["HEIGHT"]))
    got = au_coverage.sample(get, CORNER, PIXEL, SIZE, step=(25, 20), max_px=40)  # 100 x 90 samples, 3 x 3 pieces
    assert got.shape == (90, 100) and (got[:, :43] == 0).all() and (got[:, 44:] > 0).all()  # 151.06 E
    path = str(tmp_path / "cells.npz")
    au_coverage.save(path, au_coverage.cells(got, 4), (25, 20), 4)
    layer = src.GeoWcsTiles("Fake", "https://wcs.example/", "1", "EPSG:4283", "fake/x/live", 5.0, corner=CORNER,
                            pixel=PIXEL, size=SIZE, cells=path)
    lat = CORNER[1] - 900 * PIXEL[1]
    assert layer.has_data_near(lat, CORNER[0] + 200 * PIXEL[0], "", metres=500) is False  # 151.011 E
    assert layer.has_data_near(lat, CORNER[0] + 2000 * PIXEL[0], "") is True  # 151.110 E
    assert layer.has_data_near(lat, CORNER[0] - 1.0, "") is False  # beyond the grid
    plain = src.GeoWcsTiles("Fake", "https://wcs.example/", "1", "EPSG:4283", "fake/x/live", 5.0, corner=CORNER,
                            pixel=PIXEL, size=SIZE)
    assert plain.has_data_near(lat, CORNER[0] + 2000 * PIXEL[0], "") is None
    # The stored mask (2026-11-15): GA's coastal surveys are data, the inland cliffs are not
    stored = src.SOURCES["australia"].nmt
    for place in ((-33.8200, 151.2970), (-35.0930, 150.8030), (-34.88, 150.60), (-34.15, 151.08), (-28.07, 152.85),
                  (-27.477, 153.035)):  # North Head, Point Perpendicular, Nowra, Royal NP, Frog Buttress, Kangaroo Pt
        assert stored.has_data_near(*place, "") is True, place
    for place in ((-36.75, 141.83), (-33.59, 150.26), (-37.15, 142.45), (-33.732, 150.312)):
        assert stored.has_data_near(*place, "") is False, place  # Arapiles, Mount Victoria, Grampians, 3 Sisters


def test_australia_chosen_where_it_has_data(monkeypatch, tmp_path):
    """Offline: North Head gets australia, Arapiles europe (no survey near it), Kupang (West Timor, north of the
    split box) no Australian source, the Kimberley Australia."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(src.choose.osm, "reverse", offline)
    choose = src.choose_source
    assert choose("auto", -33.8200, 151.2970, str(tmp_path))[0].id == "australia"
    assert choose("auto", -36.75, 141.83, str(tmp_path)) == (
        src.SOURCES["europe"], "the centre is in AU, but australia has no terrain data near it")
    assert src.choose.country_code(-10.17, 123.60, str(tmp_path)) is None  # Kupang
    assert choose("auto", -10.17, 123.60, str(tmp_path))[0].id == "europe"
    assert src.choose.country_code(-14.0, 126.0, str(tmp_path)) == "au"  # the Kimberley
