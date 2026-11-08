"""Neighbours across borders (Source.neighbours): the gaps on land at a border filled from the
national data of the neighbouring countries or regions before the fallback (sources/filling.py:
border_gaps, neighbour_window, fill_from_neighbours; search.prepare_data)."""

import os

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

import grid as gd
import search
import sources as src

BOX = (49.0, 52.0, 18.0, 20.0)  # (south, north, west, east) around the test grid
FAR = (40.0, 41.0, 0.0, 1.0)


def _tif(path, grid, band):
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=grid.crs, nodata=-9999.0, transform=from_origin(grid.left, grid.top, grid.res, grid.res)) as dst:
        dst.write(np.where(np.isnan(band), -9999.0, band).astype(np.float32), 1)
    return path


class _File(src.FileLayer):
    """A local file that records its credit, as the cached layers do."""

    def used(self, grid, cache_dir):
        return {**super().used(grid, cache_dir), "credit": self.credit.as_dict()}


class _Untouchable(src.Layer):
    """A layer of a neighbour that must not be asked anything."""
    description, folder, credit, native_res = "untouchable", "untouchable", None, 1.0

    def tiles(self, grid):
        raise AssertionError("asked for its tiles")

    def download(self, *args, **kwargs):
        raise AssertionError("downloaded")


def _source(sid, layer, offline=(("pl", BOX),), **kwargs):
    credit = src.Credit(f"{sid} data", f"© {sid}", "CC BY 4.0", "https://example.org")
    return src.Source(id=sid, name=f"{sid} name", description=sid, nmt=layer, credits=(credit,),
                      offline=offline, **kwargs)


@pytest.fixture
def scene(tmp_path):
    """A grid of 100 x 100 px of 10 m whose 40 western columns lie across a border (no data),
    and a 10 x 10 px hole in its data in the east."""
    grid = gd.make_grid((500000, 300000, 501000, 301000), 10, "EPSG:2180")
    elevation = np.full((grid.height, grid.width), 100.0, np.float32)
    elevation[:, :40] = np.nan
    elevation[45:55, 70:80] = np.nan
    path = str(tmp_path / "nmt.npy")
    np.save(path, elevation)
    src.mosaic.used_data.clear()
    yield grid, path, tmp_path
    src.mosaic.used_data.clear()


def _neighbour(tmp_path, grid, sid, columns, value, over_data=None, **kwargs):
    """A neighbour with data value in columns, and over_data over the scene's own data (where
    the surveys overlap), NaN elsewhere."""
    band = np.full((grid.height, grid.width), np.nan, np.float32)
    band[:, columns] = value
    if over_data is not None:
        band[:, 40:] = over_data
    file = _tif(str(tmp_path / f"{sid}.tif"), grid, band)
    return _source(sid, _File(f"{sid} terrain", file), **kwargs)


def test_border_gaps_only_at_the_edge(scene):
    """A gap reaching the edge of the footprint is a border; a hole inside the data is not."""
    grid, path, _ = scene
    gaps = src.filling.border_gaps(path, None, grid)
    assert gaps[:, 10:40].any() and not gaps[45:55, 70:80].any()
    # the corners outside the circle the tiles are picked under are no gap of the search
    assert not gaps[0, 0] and not gaps[99, 0]


def test_neighbours_in_turn_then_the_fallback(scene):
    """The first neighbour fills its part, the second what it left, the fallback the rest (the
    hole inside the data too); each gap shifted to the heights around it."""
    grid, path, tmp = scene
    first = _neighbour(tmp, grid, "first", slice(20, 40), 110.0, over_data=100.25)
    second = _neighbour(tmp, grid, "second", slice(0, 20), 120.0)
    fallback = _neighbour(tmp, grid, "fallback", slice(None), 130.0, over_data=100.0)
    out = str(tmp / "joined.npy")
    joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [first, second], str(tmp / "cache"), out)
    result = np.load(path)
    assert joined_path == out
    assert [(s.id, n > 0) for s, n in counts] == [("first", True), ("second", True)]
    # first: 110 minus the offset of the overlap (its data 0.25 m above ours)
    assert np.allclose(result[50, 20:40], 109.75)
    assert np.allclose(result[50, 5:20], 120.0)  # no overlap to match with: as it is
    assert np.isnan(result[45:55, 70:80]).all()  # the hole is no border: left to the fallback
    joined = np.load(out)
    assert joined[50, 5:40].all() and not joined[:, 40:].any()
    _, filled = src.fill_gaps_chain(path, None, grid, [fallback], str(tmp / "cache"), str(tmp / "filled.npy"))
    result = np.load(path)
    assert np.isfinite(result[45:55, 70:80]).all() and np.isfinite(result[:, :5]).all()
    assert [s.id for s, n in filled] == ["fallback"] and filled[0][1] >= 100
    mask = np.load(str(tmp / "filled.npy"))
    assert mask[45:55, 70:80].all() and not mask[50, 5:40].any()  # the neighbours' pixels are not "filled"


def test_far_neighbour_not_asked(scene):
    """A neighbour whose boxes do not reach a border gap is never asked for its tiles."""
    grid, path, tmp = scene
    far = _source("far", _Untouchable(), offline=(("es", FAR),))
    joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [far], str(tmp / "cache"),
                                                           str(tmp / "joined.npy"))
    assert joined_path is None and counts == []


def test_border_boxes_reach_where_the_offline_boxes_stop(scene):
    """A neighbour whose offline boxes keep off the border (they must not take a neighbour's points)
    fills a border gap through its border boxes; they change nothing for the choice of a source."""
    grid, path, tmp = scene
    short = _neighbour(tmp, grid, "short", slice(0, 40), 120.0, offline=(("es", FAR),))
    assert short.rough_boxes() == [FAR]
    assert src.filling.neighbour_window(short, grid, src.filling.border_gaps(path, None, grid)) is None
    reaching = _neighbour(tmp, grid, "reaching", slice(0, 40), 120.0, offline=(("es", FAR),), border_boxes=(BOX,))
    assert reaching.rough_boxes() == [FAR, BOX]
    assert src.filling.neighbour_window(reaching, grid, src.filling.border_gaps(path, None, grid)) is not None
    _, counts = src.filling.fill_from_neighbours(path, None, grid, [short, reaching], str(tmp / "cache"),
                                                 str(tmp / "joined.npy"))
    assert [(s.id, n > 0) for s, n in counts] == [("reaching", True)]
    assert np.isfinite(np.load(path)[50, 5:40]).all()
    # a bbox counts as before, and a source without any box may fill any border gap
    assert _source("b", _Untouchable(), offline=(), bbox=BOX, border_boxes=(FAR,)).rough_boxes() == [BOX, FAR]
    assert _source("n", _Untouchable(), offline=()).rough_boxes() == []


def test_unavailable_neighbour_skipped(scene, capsys):
    """A neighbour that cannot be used here (no copy of our own tiles) is skipped with a line."""
    grid, path, tmp = scene

    class _NoCopy(_Untouchable):
        def unavailable(self):
            return "no copy of the tiles is set up"

    joined_path, counts = src.filling.fill_from_neighbours(path, None, grid, [_source("nocopy", _NoCopy())],
                                                           str(tmp / "cache"), str(tmp / "joined.npy"))
    assert joined_path is None and counts == []
    assert "not filled from nocopy name: no copy of the tiles is set up" in capsys.readouterr().out


def test_failed_neighbour_leaves_its_gaps(scene, capsys):
    """A neighbour whose download fails leaves its gaps to the next source."""
    grid, path, tmp = scene

    class _Failing(_Untouchable):
        def tiles(self, grid):
            return []

        def download(self, *args, **kwargs):
            raise RuntimeError("service down")

    second = _neighbour(tmp, grid, "second", slice(0, 40), 120.0)
    _, counts = src.filling.fill_from_neighbours(path, None, grid, [_source("failing", _Failing()), second],
                                                 str(tmp / "cache"), str(tmp / "joined.npy"))
    assert [s.id for s, n in counts] == ["second"]
    assert "not filled from failing name: service down" in capsys.readouterr().out
    assert np.allclose(np.load(path)[50, 5:40], 120.0)


def test_credits_only_of_neighbours_that_filled(scene):
    """The data used (and so the credits of the run) holds a neighbour that filled pixels, not
    one whose data lies only where the search has data of its own."""
    grid, path, tmp = scene
    useless = _neighbour(tmp, grid, "useless", slice(40, 100), 100.0)
    useful = _neighbour(tmp, grid, "useful", slice(0, 40), 120.0)
    _, counts = src.filling.fill_from_neighbours(path, None, grid, [useless, useful], str(tmp / "cache"),
                                                 str(tmp / "joined.npy"))
    assert [(s.id, n > 0) for s, n in counts] == [("useless", False), ("useful", True)]
    layers = [entry["layer"] for entry in search._merged_data()]
    assert layers == ["useful terrain"]

    class _Plan:
        area = None

    credits = search._credits(_Plan(), search._dated_data(search._merged_data(), 2026))
    assert [c["attribution"] for c in credits] == ["© useful"]


def test_surface_gaps_from_the_neighbours_surface_only(scene):
    """A neighbour fills the surface gaps from its surface model; one without leaves them."""
    grid, path, tmp = scene
    surface = np.load(path).copy()
    spath = str(tmp / "nmpt.npy")
    np.save(spath, surface)
    terrain_only = _neighbour(tmp, grid, "terrain_only", slice(0, 40), 120.0)
    _, counts = src.filling.fill_from_neighbours(path, spath, grid, [terrain_only], str(tmp / "cache"),
                                                 str(tmp / "joined.npy"))
    assert counts[0][1] > 0 and np.isnan(np.load(spath)[50, 5:40]).all()
    band = np.full((grid.height, grid.width), np.nan, np.float32)
    band[:, :40] = 125.0
    with_surface = _neighbour(tmp, grid, "with_surface", slice(0, 40), 120.0)
    with_surface.nmpt = _File("with_surface surface", _tif(str(tmp / "with_surface_dsm.tif"), grid, band))
    with_surface.nmpt.credit = with_surface.credits[0]
    src.filling.fill_from_neighbours(path, spath, grid, [with_surface], str(tmp / "cache"), str(tmp / "joined2.npy"))
    assert np.allclose(np.load(spath)[50, 5:40], 125.0)


def test_declared_neighbours():
    """Neighbours are other sources of the catalogue, both ways, and one of their offline boxes
    touches one of the other's (they share a border); the order of the fill is the order declared."""
    def boxes(source):  # the offline boxes, or the bbox of a source without (alaska_ifsar)
        return [box for _, box in source.offline] if source.offline else [source.bbox]

    for sid, source in src.SOURCES.items():
        assert sid not in source.neighbours and len(set(source.neighbours)) == len(source.neighbours)
        for other in source.neighbours:
            assert sid in src.SOURCES[other].neighbours, (sid, other)
            assert any(s1 <= n2 and s2 <= n1 and w1 <= e2 and w2 <= e1
                       for s1, n1, w1, e1 in boxes(source) for s2, n2, w2, e2 in boxes(src.SOURCES[other])), \
                (sid, other)
    assert src.SOURCES["geoportal"].neighbours == ("slovakia", "mecklenburg_vorpommern", "czechia", "saxony",
                                                     "brandenburg")
    assert src.SOURCES["austria"].neighbours == ("swisstopo", "south_tyrol", "slovakia", "czechia", "bavaria",
                                                    "slovenia")
    assert src.SOURCES["europe"].neighbours == () and src.SOURCES["usa"].neighbours == ("canada", "british_columbia")
    assert src.SOURCES["nunavut"].neighbours == ("canada",)
    assert src.SOURCES["canada"].neighbours == ("usa", "alaska", "alaska_ifsar", "nunavut")
    assert src.SOURCES["saarland"].neighbours == ("rhineland_palatinate", "france", "luxembourg")
    assert src.SOURCES["british_columbia"].neighbours == ("usa", "alaska", "alaska_ifsar")


def test_border_gaps_once_unless_a_neighbour_wrote(scene, monkeypatch):
    """The border gaps are found once for all neighbours; again only after one wrote pixels into
    the grids (or failed midway), since an attempt that found no data of its own leaves them.
    fill_gaps also tells the pixels written to either grid."""
    grid, path, tmp = scene
    calls = []
    original = src.filling.border_gaps
    monkeypatch.setattr(src.filling, "border_gaps", lambda *a, **k: calls.append(1) or original(*a, **k))
    useless = _neighbour(tmp, grid, "useless", slice(40, 100), 100.0)
    useful = _neighbour(tmp, grid, "useful", slice(0, 40), 120.0)
    _, counts = src.filling.fill_from_neighbours(path, None, grid, [useless, useful, useless], str(tmp / "cache"),
                                                 str(tmp / "joined.npy"))
    assert [n > 0 for _, n in counts] == [False, True]  # the third finds no border gap left
    assert len(calls) == 2  # once at the start, once after the useful one filled the border
    assert src.filling.fill_from_neighbours(path, None, grid, [], str(tmp / "cache"), str(tmp / "none.npy")) == (None, [])
    assert src.filling.fill_gaps(path, None, grid, useless, str(tmp / "cache"), str(tmp / "again.npy"))[1:] == (100, 100)  # the hole: terrain pixels, pixels written


@pytest.mark.parametrize("rows", [None, 30])
def test_border_gaps_only_for_a_neighbour_reaching_the_grid(scene, monkeypatch, rows):
    """A neighbour whose rough boxes reach no pixel of the grid has no border gap inside them
    (neighbour_window gives None for any), so the border gaps are found only for one that reaches the
    grid (a tile at a border without such a neighbour finds none), and the fill is as before."""
    grid, path, tmp = scene
    calls = []
    original = src.filling.border_gaps
    monkeypatch.setattr(src.filling, "border_gaps", lambda *a, **k: calls.append(1) or original(*a, **k))
    far = _source("far", _Untouchable(), offline=(("es", FAR),))
    assert src.filling._box_ranges(far, grid) == []
    joined, counts = src.filling.fill_from_neighbours(path, None, grid, [far], str(tmp / "cache"),
                                                      str(tmp / "far.npy"), rows=rows)
    assert joined is None and counts == [] and not calls
    useful = _neighbour(tmp, grid, "useful", slice(0, 40), 120.0)
    _, counts = src.filling.fill_from_neighbours(path, None, grid, [far, useful, far], str(tmp / "cache"),
                                                 str(tmp / "joined.npy"), rows=rows)
    assert [(s.id, n > 0) for s, n in counts] == [("useful", True)] and len(calls) == 1
    assert np.isfinite(np.load(path)[50, 5:40]).all() and not os.path.exists(tmp / "border.npy")


@pytest.mark.parametrize("rows", [None, 30])
def test_neighbours_resampled_as_set(scene, monkeypatch, rows):
    """How a neighbour's data are reprojected (half a pixel off our grid here, at its resolution):
    by NEIGHBOUR_SAME_RESOLUTION, nearest, which keeps the neighbour's own values (None: bilinear,
    the mosaic's own choice); NEIGHBOUR_RESAMPLING chooses a method for every raster instead; the
    fallbacks keep the mosaic's choice."""
    grid, path, tmp = scene
    start = np.load(path)
    ramp = (500 + np.random.default_rng(4).normal(0, 40, (grid.height, grid.width + 1))).astype(np.float32)
    ramp[:, 39:] = np.nan  # no pixel over our data: no offset to match, its heights as they are
    file = str(tmp / "ramp.tif")
    with rio.open(file, "w", driver="GTiff", width=ramp.shape[1], height=ramp.shape[0], count=1, dtype="float32",
                  crs=grid.crs, nodata=-9999.0,
                  transform=from_origin(grid.left - grid.res / 2, grid.top + grid.res / 2, grid.res, grid.res)) as dst:
        dst.write(np.where(np.isnan(ramp), -9999.0, ramp), 1)
    neighbour = _source("ramp", _File("ramp terrain", file))
    results = {}
    for method in (None, "bilinear", "nearest", "cubic"):
        np.save(path, start)
        monkeypatch.setattr(src.filling, "NEIGHBOUR_RESAMPLING", method)
        _, counts = src.filling.fill_from_neighbours(path, None, grid, [neighbour], str(tmp / "cache"),
                                                     str(tmp / f"joined-{method}.npy"), rows=rows)
        assert counts[0][1] > 0
        results[method] = np.load(path)[30:70, 5:35]
    assert src.filling.NEIGHBOUR_SAME_RESOLUTION == "nearest"
    assert np.array_equal(results[None], results["nearest"])  # the default at the grid's resolution
    assert np.isin(results["nearest"], ramp).all() and np.isin(results["bilinear"], ramp).mean() < 0.01
    assert not np.array_equal(results["cubic"], results["bilinear"])
    # without the rule for the grid's resolution: the mosaic's own choice, bilinear
    np.save(path, start)
    monkeypatch.setattr(src.filling, "NEIGHBOUR_RESAMPLING", None)
    monkeypatch.setattr(src.filling, "NEIGHBOUR_SAME_RESOLUTION", None)
    src.filling.fill_from_neighbours(path, None, grid, [neighbour], str(tmp / "cache"), str(tmp / "joined-own.npy"),
                                     rows=rows)
    assert np.array_equal(np.load(path)[30:70, 5:35], results["bilinear"])
    monkeypatch.setattr(src.filling, "NEIGHBOUR_SAME_RESOLUTION", "nearest")
    # a fallback is reprojected by the mosaic's own choice whatever the neighbours' method
    np.save(path, start)
    monkeypatch.setattr(src.filling, "NEIGHBOUR_RESAMPLING", "nearest")
    src.fill_gaps_chain(path, None, grid, [neighbour], str(tmp / "cache"), str(tmp / "filled.npy"), rows=rows)
    assert np.array_equal(np.load(path)[30:70, 5:35], results["bilinear"])
