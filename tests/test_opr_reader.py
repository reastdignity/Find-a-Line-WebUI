"""The reader's rule for USGS's OPR DEMs (sources/readers/windows.py compose_opr, opr_method): each file brought onto
1 m blocks by its own header's pixel (copied on the block's pixels, averaged below 0.75 m, cubic from 0.75 to
1.001 m, skipped above), its heights times its survey's factor, the tiles of one survey joined before the warp, and a
block equal to the same file warped whole (made-up files, no network)."""

import os
import sys

import numpy as np
import pytest
import rasterio as rio
from affine import Affine
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources.layer import VALID_MIN  # noqa: E402
from http_server import only_local_hosts  # noqa: E402
from sources.readers import windows  # noqa: E402

ZONE = "EPSG:26913"


@pytest.fixture(autouse=True)
def _only_the_test_server():
    """Every test of this file asks the test server only (http_server.only_local_hosts); an outside host fails the
    test (fix round 3)."""
    with only_local_hosts() as asked:
        yield
    assert not asked, f"the test asked outside hosts: {sorted(set(asked))}"
BLOCK = 200  # metres (and pixels) of the test's blocks: the reader takes any block; the layer's are 1000
X0, Y0 = 500000.0, 4400000.0  # a corner of the test's blocks in the zone


def terrain(x, y):
    """Smooth hills with a steep side, in metres, at zone coordinates."""
    return (1500 + 40 * np.sin(x / 37.0) * np.cos(y / 23.0) + 0.3 * (x - X0)
            + 25 * np.tanh((x - X0 - BLOCK - 2.0) / 1.5)).astype(np.float32)  # a step just east of block (0, 0)


def make_file(path, crs, left, top, res, width, height, unit=1.0, nodata=-999999.0, fill=None):
    """A tiled GeoTIFF in crs whose pixels hold the terrain at their centres (in zone metres, divided by unit: a
    file in feet); fill(band, x, y) may change the band."""
    t = from_origin(left, top, res, res)
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    xs, ys = t @ (cols, rows)
    if crs != ZONE:
        xs, ys = Transformer.from_crs(crs, ZONE, always_xy=True).transform(xs, ys)
    band = terrain(xs, ys) / np.float32(unit)
    if fill is not None:
        fill(band, xs, ys)
    band = np.where(np.isnan(band), nodata, band).astype(np.float32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32", crs=crs,
                  nodata=nodata, transform=t, tiled=True, blockxsize=64, blockysize=64) as dst:
        dst.write(band, 1)
    return path


def block_grid(i, j):
    return from_origin(X0 + i * BLOCK, Y0 + (j + 1) * BLOCK, 1.0, 1.0), (BLOCK, BLOCK)


def compose(paths, transform, shape, rules, years=None):
    files = [(os.path.basename(p)[:-4], p, (years or {}).get(p, 2020)) for p in paths]
    return windows.compose_opr(files, ZONE, transform, shape, "Test OPR", lambda url: rules.get(url))


def whole_warp(paths, transform, shape, method, factor=1.0, scale="stated"):
    """The reference: every file's whole array (joined on their lattice, the first winning) warped onto the block
    by rasterio.warp.reproject with GDAL's defaults (the same CRS kept when the files are in the zone's), but for
    cubic's kernel scale: "stated" (the user's decision of 2026-11-27) the file's pixel in metres over the block's,
    computed here from the header (not by the reader's code); None: GDAL's own estimate; a number: that one."""
    arrays = []
    for p in paths:
        with rio.open(p) as src:
            a = src.read(1, masked=True).astype(np.float32).filled(np.nan)
            arrays.append((a, src.transform, src.crs))
    t0, crs = arrays[0][1], arrays[0][2]
    offs = [(round((t.f - t0.f) / t0.e), round((t.c - t0.c) / t0.a)) for _, t, _ in arrays]
    r1, c1 = min(r for r, _ in offs), min(c for _, c in offs)
    r2 = max(r + a.shape[0] for (r, _), (a, _, _) in zip(offs, arrays))
    c2 = max(c + a.shape[1] for (_, c), (a, _, _) in zip(offs, arrays))
    joined = np.full((r2 - r1, c2 - c1), np.nan, np.float32)
    for (r, c), (a, _, _) in zip(offs, arrays):
        view = joined[r - r1:r - r1 + a.shape[0], c - c1:c - c1 + a.shape[1]]
        view[np.isnan(view)] = a[np.isnan(view)]
    joined[joined < VALID_MIN] = np.nan
    joined *= np.float32(factor)
    out = np.full(shape, np.nan, np.float32)
    same = windows._same_crs(crs, ZONE)
    options = {}
    if method == "cubic" and scale is not None:
        ratio = abs(t0.a) * crs.linear_units_factor[1] / abs(transform.a) if scale == "stated" else scale
        options = {"XSCALE": str(ratio), "YSCALE": str(ratio)}
    reproject(joined, out, src_transform=t0 @ Affine.translation(c1, r1), src_crs=crs, dst_transform=transform,
              dst_crs=crs if same else ZONE, src_nodata=np.nan, dst_nodata=np.nan,
              resampling=getattr(Resampling, method), num_threads=1, **options)
    return out


# Custom transverse Mercator CRSs whose grid is turned against zone 13 (convergence about the longitude offset
# times sin(latitude) at 39.7° N)
TURNED = {0: ZONE,
          2: "+proj=tmerc +lat_0=39 +lon_0=-108.1 +k=1 +x_0=500000 +y_0=0 +ellps=GRS80 +towgs84=0,0,0 +units=m +no_defs",
          10: "+proj=tmerc +lat_0=39 +lon_0=-89.4 +k=1 +x_0=500000 +y_0=0 +ellps=GRS80 +towgs84=0,0,0 +units=m "
              "+no_defs"}


def _file_over(tmp_path, name, crs, res, margin=120.0, unit=1.0, split=None):
    """A file (or two tiles of one survey, split at a column) in crs covering the 2 x 2 test blocks and margin m
    around them, its origin off the zone's lattice."""
    corners = np.array([(X0 - margin, Y0 - margin), (X0 + 2 * BLOCK + margin, Y0 - margin),
                        (X0 - margin, Y0 + 2 * BLOCK + margin), (X0 + 2 * BLOCK + margin, Y0 + 2 * BLOCK + margin)])
    if crs != ZONE:
        xs, ys = Transformer.from_crs(ZONE, crs, always_xy=True).transform(corners[:, 0], corners[:, 1])
    else:
        xs, ys = corners[:, 0], corners[:, 1]
    left = np.floor(xs.min() / res) * res + 0.37 * res
    top = np.ceil(ys.max() / res) * res + 0.21 * res
    width, height = int((xs.max() - left) / res) + 2, int((top - ys.min()) / res) + 2
    if split is None:
        return [make_file(str(tmp_path / f"{name}.tif"), crs, left, top, res, width, height, unit)]
    return [make_file(str(tmp_path / f"{name}_a.tif"), crs, left, top, res, split, height, unit),
            make_file(str(tmp_path / f"{name}_b.tif"), crs, left + split * res, top, res, width - split, height, unit)]


def test_methods_by_the_files_own_pixel(tmp_path, capsys):
    """On the block's pixels: copied, bit for bit; 0.5 m in the block's CRS and in another CRS: averaged; 0.762 m and
    0.9144 m in a State Plane CRS in feet and 1.0 m shifted by part of a pixel: cubic; 1.2 m and a geographic CRS:
    skipped and named."""
    transform, shape = block_grid(0, 0)
    on = make_file(str(tmp_path / "on.tif"), ZONE, X0 - 10, Y0 + BLOCK + 10, 1.0, 220, 220)
    with rio.open(on) as src:
        assert windows.opr_method(src, ZONE, transform) == ("copy", "")
        expected = src.read(1, window=rio.windows.Window(10, 10, BLOCK, BLOCK))
    block, tags = compose([on], transform, shape, {on: (1.0, ("copy",), "s")})
    assert np.array_equal(block, expected) and tags == {"sources": "on", "years": "2020"}

    cases = [("half_zone", ZONE, 0.5, "average"), ("half_2011", "EPSG:6342", 0.5, "average"),  # NAD83(2011) / UTM 13N
             ("half_other", "EPSG:32613", 0.5, "average"),
             ("sp_2_5ft", "EPSG:2232", 2.5, "cubic"),      # NAD83 / Colorado Central (ftUS): 0.762 m
             ("sp_3ft", "EPSG:2256", 3.0, "cubic"),        # NAD83 / Montana (ft): 0.9144 m
             ("shifted", ZONE, 1.0, "cubic")]
    for name, crs, res, method in cases:
        paths = _file_over(tmp_path, name, crs, res)
        with rio.open(paths[0]) as src:
            assert windows.opr_method(src, ZONE, transform)[0] == method, name
        block, tags = compose(paths, transform, shape, {paths[0]: (1.0, (method,), "s")})
        reference = whole_warp(paths, transform, shape, method)
        assert np.isfinite(block).all() and tags["sources"] == name, name
        assert np.nanmax(np.abs(block - reference)) < 2e-3, name
    # bilinear, as _read_window reads a 0.5 m file of the block's CRS, is not what the rule gives
    paths = _file_over(tmp_path, "half_zone", ZONE, 0.5)
    block, _ = compose(paths, transform, shape, {paths[0]: (1.0, ("average",), "s")})
    assert np.nanmax(np.abs(block - whole_warp(paths, transform, shape, "bilinear"))) > 0.002

    coarse = _file_over(tmp_path, "coarse", ZONE, 1.2)
    geo = make_file(str(tmp_path / "geo.tif"), "EPSG:4269", -105.01, 39.75, 1e-5, 300, 300)
    for path, why in ((coarse[0], "its pixel is 1.200 m (coarser than 1.001 m)"), (geo, "it has no projected CRS")):
        block, tags = compose([path], transform, shape, {path: (1.0, ("cubic",), "s")})
        assert tags is None and np.isnan(block).all()
        assert f"{os.path.basename(path)[:-4]} left out: {why}" in capsys.readouterr().out
    # a file whose header takes another method than its survey's sampled headers: read by its own all the same
    # (the user's D4 and N4; the code review's F3), named once, its values those of its own method
    paths = _file_over(tmp_path, "sp_3ft", "EPSG:2256", 3.0)
    block, tags = compose(paths, transform, shape, {paths[0]: (1.0, ("average",), "s")})
    assert tags["sources"] == "sp_3ft" and np.abs(block - whole_warp(paths, transform, shape, "cubic")).max() < 2e-3
    assert "survey s: file sp_3ft takes cubic, its record says average" in capsys.readouterr().out
    with pytest.raises(RuntimeError, match="no survey record"):
        compose(paths, transform, shape, {})


def test_compound_crs_files(tmp_path):
    """Files whose header names a compound CRS (21 of gate 0's 30 headers: a horizontal CRS and NAVD88 height): the
    pixel counts in the horizontal CRS's unit, so metres horizontally with heights in feet is 0.5 m (average), State
    Plane in US survey feet with heights in feet is 0.762 m (cubic), and NAD83 / UTM + NAVD88 on the lattice is a
    copy of the zone's own pixels."""
    transform, shape = block_grid(0, 0)
    cases = [("utm_ft", "EPSG:26913+6360", 0.5, "average"),   # NAD83 / UTM 13N + NAVD88 height (ftUS)
             ("sp_ft", "EPSG:2232+6360", 2.5, "cubic")]       # Colorado Central (ftUS) + NAVD88 height (ftUS)
    for name, crs, res, method in cases:
        paths = _file_over(tmp_path, name, rio.crs.CRS.from_user_input(crs).to_wkt(), res)
        with rio.open(paths[0]) as src:
            assert src.crs.is_projected and src.crs.to_wkt().startswith(("COMPD_CS", "COMPOUNDCRS")), name
            assert windows.opr_method(src, ZONE, transform) == (method, ""), name
        block, _ = compose(paths, transform, shape, {paths[0]: (1.0, (method,), "s")})
        assert np.isfinite(block).all() and np.abs(block - whole_warp(paths, transform, shape, method)).max() < 2e-3
    on = make_file(str(tmp_path / "on_compound.tif"), rio.crs.CRS.from_user_input("EPSG:26913+5703").to_wkt(),
                   X0 - 10, Y0 + BLOCK + 10, 1.0, 220, 220)
    with rio.open(on) as src:
        assert windows.opr_method(src, ZONE, transform) == ("copy", "")


@pytest.mark.parametrize("turn", [0, 2, 10])
def test_block_equals_the_whole_warp(tmp_path, turn):
    """Four neighbouring blocks made by the reader from a 0.762 m file turned 0, 2 and 10 degrees against the zone
    equal the same file warped whole (cubic, GDAL's defaults but the kernel's scale stated: 0.762) onto each block,
    to float rounding (bit for bit, measured 2026-11-27): inside and across their edges. Against one warp of the four
    blocks' lattice at once (the scale stated) they differ by 0, 2.3 and 11.1 mm at 0, 2 and 10 degrees (2026-11-27,
    after the fixed scale as before it): GDAL's default error threshold (the user's choice: the warp as it is)
    approximates the transform per warp, so its error depends on the warp's extent (the scope review's S1; with
    tolerance 0 the two agree to 0.1 mm); with GDAL's own scale on both sides the larger warp is 2.32 and 10.86 mm
    off (the third code review). The stated-scale blocks against a larger warp with GDAL's own scale are 13.5 and
    23.5 cm apart at 2 and 10 degrees: the size of the decision's change for a turned file at this terrain's 25 m step
    (GDAL widens the kernel of a turned file by its window's box), not a dependence on the warp's extent."""
    paths = _file_over(tmp_path, f"turned{turn}", TURNED[turn], 0.762)
    with rio.open(paths[0]) as src:
        assert windows.opr_method(src, ZONE, block_grid(0, 0)[0])[0] == "cubic"
    rules = {paths[0]: (1.0, ("cubic",), "s")}
    mosaic = np.full((2 * BLOCK, 2 * BLOCK), np.nan, np.float32)
    reference = np.full_like(mosaic, np.nan)
    for i in (0, 1):
        for j in (0, 1):
            transform, shape = block_grid(i, j)
            block, _ = compose(paths, transform, shape, rules)
            rows, cols = slice((1 - j) * BLOCK, (2 - j) * BLOCK), slice(i * BLOCK, (i + 1) * BLOCK)
            mosaic[rows, cols] = block
            reference[rows, cols] = whole_warp(paths, transform, shape, "cubic")
    assert np.isfinite(mosaic).all()
    assert np.abs(mosaic - reference).max() < 1e-4  # per block: float rounding
    larger = whole_warp(paths, from_origin(X0, Y0 + 2 * BLOCK, 1.0, 1.0), (2 * BLOCK, 2 * BLOCK), "cubic")
    assert np.abs(mosaic - larger).max() < {0: 1e-4, 2: 0.0025, 10: 0.012}[turn]


def _inside(values, px=4):
    """The pixels with data more than px pixels from the edge of the data (a file warped alone has no neighbours at
    its own edge rows: there it may differ from a joined window, which is what the join is for)."""
    from scipy import ndimage
    has = np.isfinite(values)
    return has & (ndimage.distance_transform_edt(has) > px)


def test_the_kernel_scale_is_the_files_own(tmp_path):
    """The user's decision of 2026-11-27: cubic's kernel scale fixed at the file's pixel over the block's (XSCALE and
    YSCALE 0.9144 for a 3 ft file), so a pixel's value does not depend on how much of the block the survey covers
    (fix round 1, S6: up to 3.7 cm apart on a 3 ft survey in Montana). A survey of two 3 ft tiles (NAD83 / Montana,
    ft, turned about 3° against the zone): the block from one tile alone equals the block from both joined wherever
    the lone tile has data more than 4 pixels inside its edge, and a block at the survey's edge (the file covering part
    of it) equals the same pixels of a warp onto a window the file covers whole: to 0.12 mm measured on 2026-11-27,
    the approximate transformer's fit per warp (GDAL's default error threshold, kept by the user: the scope review's
    S1; bit for bit with a threshold of 1e-6 on the real Montana tile of fix round 1). The ratio's direction: on a file of 0.9144 m in the zone's CRS covering the block
    whole GDAL's own estimate is the fixed ratio (equal), while the inverse ratio (above 1: no widening) is 4.3 cm off."""
    paths = _file_over(tmp_path, "mt3ft", "EPSG:2256", 3.0, split=240)  # the split about 100 m inside block (0, 0)
    rules = {p: (1.0, ("cubic",), "s") for p in paths}
    transform, shape = block_grid(0, 0)
    joined, tags = compose(paths, transform, shape, rules)
    assert tags["sources"] == "mt3ft_a,mt3ft_b"
    for one in paths:
        alone, _ = compose([one], transform, shape, rules)
        inside = _inside(alone)
        assert 0.1 < inside.mean() < 0.9  # each tile covers part of the block
        assert np.abs(alone[inside] - joined[inside]).max() < 2e-4, one
    # an edge block against an interior warp: the second tile alone onto block (0, 0), and onto a window of the same
    # lattice 150 m east, which that tile covers whole; their common pixels
    alone, _ = compose(paths[1:], transform, shape, rules)
    east = from_origin(X0 + 150, Y0 + BLOCK, 1.0, 1.0)
    interior, _ = compose(paths[1:], east, shape, rules)
    assert np.isfinite(interior).all()
    common = _inside(alone)[:, 150:]
    assert common.any() and np.abs(alone[:, 150:][common] - interior[:, :BLOCK - 150][common]).max() < 2e-4
    # the direction of the ratio
    zone = _file_over(tmp_path, "zone0914", ZONE, 0.9144)
    fixed, _ = compose(zone, transform, shape, {zone[0]: (1.0, ("cubic",), "s")})
    assert np.array_equal(fixed, whole_warp(zone, transform, shape, "cubic", scale=None))
    assert np.abs(fixed - whole_warp(zone, transform, shape, "cubic", scale=1 / 0.9144)).max() > 0.02
    assert windows.opr_scale(from_origin(0, 0, 3.0, 3.0), rio.crs.CRS.from_epsg(2256), transform) == \
        {"XSCALE": "0.9144", "YSCALE": "0.9144"}


def test_the_guard_takes_the_foot_and_the_us_survey_foot_as_one(tmp_path, capsys):
    """The reader's guard of a survey's one height factor (fix round 3: units at a relative 1e-5): a file in feet
    (NAD83 / Montana, ft) of a survey whose sampled files are in US survey feet is read; a file in metres of that
    survey is left out and named."""
    transform, shape = block_grid(0, 0)
    us_foot = 1200 / 3937
    feet = _file_over(tmp_path, "mt_ft", "EPSG:2256", 3.0, unit=0.3048)
    block, tags = compose(feet, transform, shape, {feet[0]: (us_foot, ("cubic",), "s", (us_foot,))})
    assert tags is not None and np.isfinite(block).all()
    metres = make_file(str(tmp_path / "m.tif"), ZONE, X0 - 10.3, Y0 + BLOCK + 10.3, 0.5, 450, 450)
    block, tags = compose([metres], transform, shape, {metres: (us_foot, ("average",), "s", (us_foot,))})
    assert tags is None and "file m left out: it is in another unit" in capsys.readouterr().out


def test_tiles_of_one_survey_joined(tmp_path):
    """A block across the edge between two tiles of one survey equals the whole survey warped at once; warped tile
    by tile (each alone, the first filling), the kernel would lose the other tile's pixels at the edge."""
    paths = _file_over(tmp_path, "two", "EPSG:2232", 2.5, split=380)
    rules = {p: (1.0, ("cubic",), "s") for p in paths}
    sources = []
    for i in (1, 0):  # the split lies in block (0, 0), about 170 m from its west edge
        transform, shape = block_grid(i, 0)
        block, tags = compose(paths, transform, shape, rules)
        reference = whole_warp(paths, transform, shape, "cubic")
        assert np.isfinite(block).all() and np.abs(block - reference).max() < 2e-3
        sources.append(tags["sources"])
    assert sources == ["two_b", "two_a,two_b"]
    alone = np.full(shape, np.nan, np.float32)
    for p in paths:
        values = whole_warp([p], transform, shape, "cubic")
        alone[np.isnan(alone)] = values[np.isnan(alone)]
    assert np.nanmax(np.abs(alone - reference)) > 0.01
    # two surveys are never joined: the newer fills, the older only the rest
    rules = {paths[0]: (1.0, ("cubic",), "new"), paths[1]: (1.0, ("cubic",), "old")}
    block, _ = compose(paths, transform, shape, rules)
    assert np.nanmax(np.abs(block - reference)) > 0.01


def test_a_tile_ending_just_outside_the_block(tmp_path):
    """A tile that ends within the margin outside the block still gives the kernel its pixels: the block equals the
    whole survey's warp at that edge (cubic's kernel, widened for a 0.762 m file, reaches about 1.5 m beyond the
    block's edge, with weight only within about 0.6 m). A file of 0.762 m in the zone's CRS, so its columns run
    along the block's edge."""
    paths = _file_over(tmp_path, "edge", ZONE, 0.762)
    with rio.open(paths[0]) as src:
        # the first column wholly beyond the east edge of block (0, 0), at least 0.1 m beyond it
        split = int(np.ceil((X0 + BLOCK + 0.1 - src.transform.c) / src.transform.a))
        assert 0.1 <= src.transform.c + split * src.transform.a - (X0 + BLOCK) < 0.9
    paths = _file_over(tmp_path, "edge", ZONE, 0.762, split=split)
    transform, shape = block_grid(0, 0)
    rules = {p: (1.0, ("cubic",), "s") for p in paths}
    with_both, _ = compose(paths, transform, shape, rules)
    reference = whole_warp(paths, transform, shape, "cubic")
    assert np.abs(with_both - reference).max() < 2e-3
    without, _ = compose(paths[:1], transform, shape, rules)
    assert np.nanmax(np.abs(without - reference)) > 0.01 or np.isnan(without).any()


def test_factor_after_the_floor(tmp_path):
    """A file in feet gives heights in metres (times its survey's factor); the floor (VALID_MIN, -500) acts on the
    file's own unit, before the factor: -600 ft is no data, -400 ft is -121.92 m."""
    transform, shape = block_grid(0, 0)

    def low(band, xs, ys):
        band[:, :40] = -600.0
        band[:, 40:80] = -400.0
    path = make_file(str(tmp_path / "feet.tif"), ZONE, X0 - 10, Y0 + BLOCK + 10, 1.0, 220, 220, unit=0.3048,
                     fill=low)
    block, _ = compose([path], transform, shape, {path: (0.3048, ("copy",), "s")})
    assert np.isnan(block[:, :30]).all()
    assert np.allclose(block[:, 31:70], -400 * 0.3048)
    expected = terrain(*from_origin(X0, Y0 + BLOCK, 1, 1) @ np.meshgrid(np.arange(BLOCK) + 0.5,
                                                                         np.arange(BLOCK) + 0.5))
    assert np.allclose(block[:, 80:], expected[:, 80:], atol=1e-3)
    # cubic from a file in feet: the factor before the warp, as the reference has it
    paths = _file_over(tmp_path, "sp_feet", "EPSG:2232", 2.5, unit=1200 / 3937)
    block, _ = compose(paths, transform, shape, {paths[0]: (1200 / 3937, ("cubic",), "s")})
    assert np.abs(block - whole_warp(paths, transform, shape, "cubic", 1200 / 3937)).max() < 2e-3
    assert np.abs(block - expected).max() < 1.0  # metres again, near the terrain


def _signalling(monkeypatch, when):
    """net.gdal_errors whose uses for which when(n) holds (n from 1) collect an error, as a range cut short."""
    import contextlib
    real, calls = windows.net.gdal_errors, {"n": 0}

    @contextlib.contextmanager
    def errors():
        with real() as found:
            calls["n"] += 1
            if when(calls["n"]):
                found.append("simulated: TIFFFetchNormalTag: cannot read GeoKeyDirectory (range cut short)")
            yield found
    monkeypatch.setattr(windows.net, "gdal_errors", errors)
    return calls


def test_an_error_at_the_open_is_never_dropped(tmp_path, monkeypatch):
    """The code review's F4: an error GDAL signalled at a file's open is raised (Incomplete) before anything is
    decided from the header, also when the header gives no method (no CRS: what a cut GeoKey directory leaves), so
    the retry and _forget apply; one that keeps coming fails the block (RuntimeError), never a block "missing"."""
    transform, shape = block_grid(0, 0)
    no_crs = str(tmp_path / "nocrs.tif")
    with rio.open(no_crs, "w", driver="GTiff", width=300, height=300, count=1, dtype="float32",
                  transform=from_origin(X0 - 10, Y0 + BLOCK + 10, 0.762, 0.762), nodata=-999999.0) as dst:
        dst.write(np.full((300, 300), 1500, np.float32), 1)
    _signalling(monkeypatch, lambda n: n == 1)
    with pytest.raises(windows.Incomplete, match="range cut short"):
        windows._opr_file(no_crs, ZONE, transform, shape, "nocrs", 2020, "Test OPR", (1.0, ("cubic",), "s"))
    monkeypatch.setattr(windows.net, "_sleep", lambda attempt: None)
    _signalling(monkeypatch, lambda n: True)
    with pytest.raises(RuntimeError, match="completely"):
        compose([no_crs], transform, shape, {no_crs: (1.0, ("cubic",), "s")})


def test_a_rotated_file_is_left_out(tmp_path, capsys):
    """The code review's F8: a file whose geotransform has rotation terms is left out and named (its pixel is not
    abs(a)); never windowed as if it were not turned."""
    transform, shape = block_grid(0, 0)
    path = str(tmp_path / "turned.tif")
    t = Affine(0.987, 0.359, X0 - 10, 0.359, -0.987, Y0 + BLOCK + 10)  # a 1.05 m pixel turned 20 degrees
    with rio.open(path, "w", driver="GTiff", width=300, height=300, count=1, dtype="float32", crs=ZONE,
                  transform=t, nodata=-999999.0) as dst:
        dst.write(np.full((300, 300), 1500, np.float32), 1)
    with rio.open(path) as src:
        assert windows.opr_method(src, ZONE, transform) == (None, "its geotransform is rotated")
    block, tags = compose([path], transform, shape, {path: (1.0, ("cubic",), "s")})
    assert tags is None and "turned left out: its geotransform is rotated" in capsys.readouterr().out


def test_fetch_group_composes_each_block(tmp_path):
    """Windows(opr=).fetch_group (a country prefetch's groups) gives each block as compose_opr makes it."""
    paths = _file_over(tmp_path, "grp", "EPSG:2232", 2.5)
    rules = {paths[0]: (1.0, ("cubic",), "s")}
    reader = windows.Windows("Test OPR", opr=rules.get)
    requests = [windows.BlockRequest([("grp", paths[0], 2020)], ZONE, *block_grid(i, 0)) for i in (0, 1)]
    got = reader.fetch_group(requests)
    for (values, tags), r in zip(got, requests):
        expected, expected_tags = compose(paths, r.transform, r.shape, rules)
        assert np.array_equal(values, expected) and tags == expected_tags
    empty = reader.fetch_group([windows.BlockRequest([("grp", paths[0], 2020)], ZONE, *block_grid(40, 40))])
    assert empty == [(None, None)]


def test_remote_faults_are_retried(tmp_path, http_server, monkeypatch):
    """An OPR file read from a server (GDAL's /vsicurl/): a range answer cut short once is asked again and the block
    comes out whole; a server answering 500 fails the block (RuntimeError), never a block of what came."""
    monkeypatch.setattr(windows.net, "_sleep", lambda attempt: None)
    paths = _file_over(tmp_path, "remote", "EPSG:2232", 2.5)
    with open(paths[0], "rb") as f:
        body = f.read()
    http_server.add("/opr/remote.tif", body, "image/tiff")
    url = http_server.url("/opr/remote.tif")
    transform, shape = block_grid(0, 0)
    expected, _ = compose(paths, transform, shape, {paths[0]: (1.0, ("cubic",), "s")})
    # the third range answer cut short (after the header's): asked again, the block whole and equal
    http_server.fault("/opr/remote.tif", "truncate", when=lambda n, r: n == 3)
    files = [("remote", url, 2020)]
    block, tags = windows.compose_opr(files, ZONE, transform, shape, "Test OPR", {url: (1.0, ("cubic",), "s")}.get)
    assert tags["sources"] == "remote" and np.array_equal(block, expected)
    assert len(http_server.requests("/opr/remote.tif")) > 3
    http_server.add("/opr/broken.tif", b"error", "text/plain", status=500)
    broken = http_server.url("/opr/broken.tif")
    with pytest.raises(RuntimeError):
        windows.compose_opr([("broken", broken, 2020)], ZONE, transform, shape, "Test OPR",
                            {broken: (1.0, ("cubic",), "s")}.get)
