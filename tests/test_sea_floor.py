"""Heights below a layer's floor are no data where its tiles are read onto the grid (Layer.nodata_below,
mosaic.build_mosaic's below): the sea floor of IGN's overseas RGE ALTI 1 m (sources/catalogue/france.py
OVERSEAS_FLOOR). The cache is LERC within 5 mm, so the floor holds within that: the tests use heights clearly on
either side of it. Every path of the mosaic (a tile on the grid copied, a tile filling another's holes, a tile
reprojected bilinearly, a finer tile averaged, each also in strips of rows) against independent references (the
mosaic of tiles floored before they are read; without a floor, test_units' _place_before), a tile cached before the
floor existed, the catalogue's own layers on served answers, the default, and step 1 of a search offline (the
floored pixels at 0 m inside the sea zone, from the fallback outside it)."""

from urllib.parse import urlencode

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

import sources as src
from grid import make_grid
from sources import mosaic, net
from sources.catalogue import france
from sources.layer import _write_tile
from test_units import _place_before

CRS = "EPSG:32620"
# A 4 x 4 tile: below the floor (-30, -1.02), above it (-0.98, -0.5, -0.01), 0 and land
VALUES = np.array([[-30.0, -1.02, -0.98, -0.5],
                   [-0.01, 0.0, 0.4, 1.0],
                   [5.0, 20.0, -2.0, np.nan],
                   [-500.0, -600.0, 3.0, 7.5]], dtype=np.float32)
FLOORED = VALUES.copy()
FLOORED[VALUES < -1.0] = np.nan
FLOORED[3, 1] = np.nan  # below layer.VALID_MIN: no data whatever the floor


def _tile(path, left=1000.0, top=2004.0, res=1.0, values=VALUES):
    """A tile as the cache writes it (LERC within 5 mm)."""
    _write_tile(path, values, CRS, from_origin(left, top, res, res))
    return path


def _plain(path, values, left, top, res):
    """A float32 GeoTIFF of exactly these values (NaN its nodata): the references compare bits."""
    with rio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype="float32",
                  crs=CRS, nodata=np.nan, transform=from_origin(left, top, res, res)) as dst:
        dst.write(values.astype(np.float32), 1)
    return path


def _grid(res=1.0, left=1000.0, bottom=2000.0, size=4):
    return make_grid((left, bottom, left + size, bottom + size), res, CRS)


@pytest.mark.parametrize("below, expected", [(None, np.where(VALUES < -500, np.nan, VALUES)), (-1.0, FLOORED)])
def test_a_tile_on_the_grid(tmp_path, below, expected):
    """Copied straight into the mosaic (the first raster of the part): below the floor no data, above it kept."""
    path = _tile(str(tmp_path / "a.tif"))
    out = mosaic.build_mosaic([path], _grid(), str(tmp_path / "m.npy"), "t", below=below)
    assert np.allclose(np.asarray(out), expected, equal_nan=True, atol=0.0051)
    assert np.isnan(np.asarray(out)).sum() == np.isnan(expected).sum()


# The paths of the mosaic, each a list of (values, left, top, res) on GRID: a tile on the grid; a tile with holes
# under one that fills them; a tile half a pixel off (bilinear); a finer tile (0.5 m: averaged)
GRID = (1000.0, 2000.0, 1016.0, 2012.0)
RNG = np.random.default_rng(7)
LAND = (RNG.uniform(-3, 4, (12, 16))).astype(np.float32)
HOLES = LAND.copy()
HOLES[3:7, 4:9] = np.nan
FINE = (RNG.uniform(-3, 4, (24, 32))).astype(np.float32)
FINE[0:2, 0:2] = [[-30.0, -30.0], [-30.0, 0.5]]   # a 2 x 2 block averaged onto one pixel
PATHS = {"copied": [(LAND, 1000.0, 2012.0, 1.0)],
         "holes filled": [(HOLES, 1000.0, 2012.0, 1.0), (LAND[::-1].copy(), 1000.0, 2012.0, 1.0)],
         "bilinear": [(np.vstack([LAND, LAND[:1]])[:, :16], 999.5, 2012.5, 1.0)],
         "averaged": [(FINE, 1000.0, 2012.0, 0.5)]}


def _files(tmp_path, name, tiles, below=None):
    """The tiles as plain files, floored first when below is given (the reference's input)."""
    out = []
    for n, (values, left, top, res) in enumerate(tiles):
        v = values if below is None else np.where(values < below, np.nan, values).astype(np.float32)
        out.append(_plain(str(tmp_path / f"{name}-{n}-{below}.tif"), v, left, top, res))
    return out


@pytest.mark.parametrize("rows", [None, 3])
@pytest.mark.parametrize("name", list(PATHS))
def test_the_floor_is_the_mosaic_of_tiles_floored_first(tmp_path, name, rows):
    """On every path, whole or in strips of rows: the floored mosaic has the bits of the mosaic of the same tiles
    floored before they are read (no value below the floor reaches a resampling)."""
    grid = make_grid(GRID, 1.0, CRS)
    raw = _files(tmp_path, name, PATHS[name])
    first = _files(tmp_path, name, PATHS[name], below=-1.0)
    floored = np.asarray(mosaic.build_mosaic(raw, grid, str(tmp_path / "f.npy"), "t", below=-1.0, rows=rows))
    reference = np.asarray(mosaic.build_mosaic(first, grid, str(tmp_path / "r.npy"), "t", rows=rows))
    assert np.isfinite(floored).any() and np.isnan(floored).any()
    assert np.array_equal(floored.view(np.uint32), reference.view(np.uint32)), name
    if name == "averaged":  # -30, -30, -30 and 0.5: only 0.5 is averaged
        assert abs(float(floored[0, 0]) - 0.5) < 1e-6


@pytest.mark.parametrize("rows", [None, 3])
@pytest.mark.parametrize("name", list(PATHS))
def test_no_floor_is_the_mosaic_as_before(tmp_path, name, rows):
    """The default (None) on every path, whole or in strips: the bits of test_units' reference of the mosaic before
    the floor existed (_place_before)."""
    grid = make_grid(GRID, 1.0, CRS)
    files = _files(tmp_path, name, PATHS[name])
    out = np.asarray(mosaic.build_mosaic(files, grid, str(tmp_path / "m.npy"), "t", rows=rows))
    old = np.full((grid.height, grid.width), np.nan, np.float32)
    for path in files:
        with rio.open(path) as f:
            _place_before(f, grid, old)
    assert np.nanmin(out) < -1  # the heights below -1 are there
    assert np.array_equal(out.view(np.uint32), old.view(np.uint32)), name


def test_the_floor_comes_before_the_resampling(tmp_path):
    """-1.5 next to 0, the tile half a pixel off the grid (bilinear): floored after the resampling the edge pixel
    would keep -0.75; floored before, the pixel takes 0 (from the 0 m pixels only)."""
    values = np.zeros((8, 8), np.float32)
    values[:, :4] = -1.5
    path = _plain(str(tmp_path / "a.tif"), values, 999.5, 2008.5, 1.0)
    grid = make_grid((1000, 2000, 1008, 2008), 1.0, CRS)
    plain = np.asarray(mosaic.build_mosaic([path], grid, str(tmp_path / "p.npy"), "t"))
    floored = np.asarray(mosaic.build_mosaic([path], grid, str(tmp_path / "f.npy"), "t", below=-1.0))
    assert np.isclose(plain[2, 3], -0.75)  # the edge pixel mixes -1.5 and 0
    assert floored[2, 3] == 0.0 and np.nanmin(floored) == 0.0 and np.isnan(floored[:, :3]).all()
    first = _plain(str(tmp_path / "b.tif"), np.where(values < -1, np.nan, values).astype(np.float32), 999.5, 2008.5, 1.0)
    reference = np.asarray(mosaic.build_mosaic([first], grid, str(tmp_path / "r.npy"), "t"))
    assert np.array_equal(floored.view(np.uint32), reference.view(np.uint32))


def test_the_default_of_a_layer():
    """No floor unless a layer says so: of every layer of the catalogue, only the overseas RGE ALTI ones."""
    floored = {s.id: layer.nodata_below for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
               if layer is not None and layer.nodata_below is not None}
    assert floored == {"france_guadeloupe": -1.0, "france_martinique": -1.0, "france_guiana": -1.0,
                       "france_spm": -1.0, "france_reunion_rgealti": -1.0, "france_mayotte": -1.0}
    assert src.WATER_MASK.nodata_below is None
    for layer in (france.FR_RGEALTI, france.FR_MNT, france.FR_MNS, france.REU_MNT, france.REU_MNS):
        assert layer.nodata_below is None


def _serve(server, layer, tile, values, nodata):
    """The GetMap the catalogue's layer writes for tile, answered by values (a float32 GeoTIFF as IGN's)."""
    request = layer.index.request(tile)
    res = (request.right - request.left) / request.width
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=request.width, height=request.height, count=1, dtype="float32",
                          crs=layer.crs, transform=from_origin(request.left, request.top, res, res),
                          nodata=nodata) as dst:
            dst.write(values.astype(np.float32), 1)
        body = memfile.read()
    server.add(f"/wms-r/wms?{urlencode(layer.reader.getmap_params(request))}", body, "image/geotiff")


@pytest.mark.parametrize("sid", ["france_martinique", "france_mayotte"])
def test_the_catalogues_layers_fresh_and_cached(http_server, tmp_path, monkeypatch, sid):
    """A served answer with the sea floor in it, through the catalogue's own layer (only the service's address
    replaced): the tile is cached as it came (the floor is not written: a tile cached before it existed is the same
    file), and the grid has no data below -1 m (within the cache's 5 mm), keeps the water just above it and the land.
    A tile whose every height lies below the floor is cached (it has data) and gives the grid nothing."""
    layer = src.SOURCES[sid].nmt
    monkeypatch.setattr(layer.reader, "service_url", http_server.url("/wms-r/wms"))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    ox, oy = layer.origin
    tile, deep_tile = (1.0, 500, 1600), (1.0, 501, 1600)
    sea = np.full((1000, 1000), 30.0)
    sea[:, :400] = -25.0          # the sea floor
    sea[:, 400:410] = -1.02       # just below the floor
    sea[:, 410:420] = -0.98       # just above it
    sea[:, 420:430] = -0.4        # the water's edge
    sea[:2, :] = -99999.0         # IGN's no data
    _serve(http_server, layer, tile, sea, -99999.0)
    _serve(http_server, layer, deep_tile, np.full((1000, 1000), -12.0), -99999.0)
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((500000 + ox + 100, 1600000 + oy + 100, 502000 + ox - 100, 1601000 + oy - 100), 1.0,
                     layer.crs, layer.origin)
    out = np.load(src.mosaic.prepare_layer(layer, grid, cache_dir, str(tmp_path / "nmt.npy"), "terrain"))
    for t in (tile, deep_tile):  # cached as they came: the floor is applied when read, not written
        with rio.open(layer.tile_path(cache_dir, t)) as cached:
            assert float(np.nanmin(cached.read(1, masked=True).filled(np.nan))) < -1
    west = out[:, :900]  # tile 500's part of the grid: its columns 100-999
    assert np.isnan(west[:, :310]).all()                       # -25 and -1.02: no data
    assert np.allclose(west[:, 310:320], -0.98, atol=0.0051)   # just above the floor: kept
    assert np.allclose(west[:, 320:330], -0.4, atol=0.0051)
    assert np.allclose(west[:, 330:], 30.0, atol=0.0051)
    assert np.isnan(out[:, 900:]).all()                        # tile 501: all below the floor


def test_step_1_of_a_search_fills_the_floored_pixels(tmp_path, monkeypatch):
    """Offline, search.prepare_data on a synthetic source with the floor: its pixels below -1 m inside the sea zone
    (the coastline's sea grown by the shore buffer) are the sea at 0 m; those outside it (a basin behind the
    coastline) are gaps on land, filled from the source's fallback (a local stand-in), as any gap; the water just
    above the floor and the land keep their heights."""
    import search
    from params import SearchParams
    from test_italy import _File, _local
    from test_offline import OFFLINE_ENV
    for key, v in OFFLINE_ENV.items():
        monkeypatch.setenv(key, v)
    left, top, size = 700000.0, 1631000.0, 600
    z = np.full((size, size), 12.0, np.float32)
    z[:, 400:] = -20.0             # the sea floor east of the coastline at column 400
    z[:, 380:400] = -0.6           # the water's edge, above the floor
    z[100:160, 100:180] = -6.0     # a basin behind the coastline (a harbour, a mangrove channel)
    nmt = _File("terrain", _plain(str(tmp_path / "nmt.tif"), z, left, top, 1.0))
    nmt.nodata_below = -1.0
    grid_all = make_grid((left, top - size, left + size, top), 1.0, CRS)
    fallback = src.Source(id="fallback_test", name="fallback test", description="f", fallback=None,
                          credits=(src.FABDEM_CREDIT,),
                          nmt=_File("fabdem", _local(str(tmp_path / "fab.tif"), grid_all,
                                                     np.full((size, size), 13.0, np.float32))))
    fallback.nmt.credit = src.FABDEM_CREDIT
    source = src.Source(id="floor_test", name="floor test", description="t", nmt=nmt, crs=CRS,
                        fallback="fallback_test", credits=(src.FABDEM_CREDIT,))
    monkeypatch.setitem(src.SOURCES, "floor_test", source)
    monkeypatch.setitem(src.SOURCES, "fallback_test", fallback)
    import params as params_module
    monkeypatch.setattr(params_module, "SOURCE_CHOICES", [*params_module.SOURCE_CHOICES, "floor_test"])
    sea = np.zeros((size, size), bool)
    sea[:, 400:] = True

    def sea_of(grid):
        cols = ((grid.left - left) + (np.arange(grid.width) + 0.5) * grid.res).astype(int)
        rows = ((top - grid.top) + (np.arange(grid.height) + 0.5) * grid.res).astype(int)
        return sea[np.clip(rows, 0, size - 1)][:, np.clip(cols, 0, size - 1)]
    monkeypatch.setattr(search.src, "water_body_mask",
                        lambda grid, *a, **k: np.where(sea_of(grid), src.OCEAN, 0).astype(np.uint8))
    monkeypatch.setattr(search.coast, "sea_mask", lambda grid, *a, **k: (sea_of(grid), "test coastline", None))
    monkeypatch.setattr(search, "_download_layers", lambda plan: None)  # local files and the masks above: nothing
    lon, lat = rio.warp.transform(CRS, "EPSG:4326", [left + 300], [top - 300])
    params = SearchParams(lat=lat[0], lon=lon[0], radius=250, source="floor_test",
                          water="fill", fill_gaps="on", coastline="copernicus", nmpt="off")
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None)
    data = search.prepare_data(plan, statistics=False, shore="none")
    g = plan.grid
    e = np.asarray(data.elevation)

    def at(x, y):
        return float(e[int((g.top - y) // g.res), int((x - g.left) // g.res)])
    assert at(left + 450, top - 300) == 0.0                  # the sea floor in the sea zone: the sea at 0 m
    assert abs(at(left + 390, top - 300) + 0.6) < 1e-6       # the water's edge kept
    basin = at(left + 140, top - 130)
    assert np.isfinite(basin) and basin != 0.0 and abs(basin - 12.0) <= 3.0   # from the fallback, matched to the land
    assert bool(np.asarray(data.filled)[int((g.top - (top - 130)) // g.res), int((left + 140 - g.left) // g.res)])
    assert abs(at(left + 250, top - 300) - 12.0) < 1e-6      # the land kept
